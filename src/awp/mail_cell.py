"""
File · src/awp/mail_cell.py
Purpose · The one driver for the mail cells on the lab's own Roundcube over local Dovecot: genuine authority prompts produced by the
client's own flows, replicas delivered as the HTML body of a message, and outcomes read from sinks, so mail-l1 (Roundcube's full message view, measured
L1 in the pilot) can be run the way the browser and chat cells are.
Description · Builds on awp.mail for delivery into the pilot Maildir and awp.browser for driving Chromium. Roundcube's message list does not respond
to synthetic clicks, so a message is opened through the client's own JavaScript API, as the pilot established; the full view renders the body inline in
the main document (L1) and the preview pane renders it in a same-origin frame (L2). Genuine prompts: the credential prompt is Roundcube's own login
form, reached by letting the session lapse (the lab's session lifetime is one minute), which is how it arises in the wild; the
confirmation prompt is Roundcube's own "do you really want to delete" dialog, raised by asking the client to delete the open message. Replicas are the
adversary's HTML in a message body, posting to the adversary origin of awp.labapp; Roundcube's sanitiser strips role and aria from them and keeps the
password field and the button, which the pilot measured. Outcomes: a genuine credential act is a new authenticated session at the client's own endpoint,
a genuine confirmation act is the message actually gone from the mailbox, and either replica act is an event at the adversary's sink.
Inputs/Outputs · In: Dovecot and Apache running, the pilot credential file, an adversary origin from awp.labapp, a sink event log. Out: delivered
messages, run setup records, events appended to the same log in the same shape as every other cell.
Depends on · src/awp/mail.py, src/awp/browser.py, src/awp/labapp.py, Roundcube over Apache, Dovecot.
Invariant · Loopback only; the pilot credential is read from its file and never printed; every event is nonce-bound; no outcome is read from page text.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from awp import mail

BASE = "http://127.0.0.1/roundcube/"
MAILDIR = mail.MAIL_HOME / "Maildir"


def now():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def js(browser, expression):
    return browser.eval_js(expression)


class MailLab:
    """One Roundcube cell under test: delivery, the client's own flows, and the observers that turn them into nonce-bound events."""

    def __init__(self, events_log, adversary_base, view="full"):
        self.events_log = Path(events_log)
        self.adversary = adversary_base.rstrip("/")
        self.view = view  # "full" renders the body inline in the main document (L1); "preview" renders it in a same-origin frame (L2)
        self.user, self.password = mail.credentials()
        self.nonce = None
        self.observed = []
        self.uid = None

    # ---------------------------------------------------------------- setup
    def reset_run(self, nonce):
        self.nonce, self.observed, self.uid = nonce, [], None
        return nonce

    def deliver(self, subject, html):
        path = mail.deliver(subject, html)
        return path.name

    def inbox_count(self):
        d = MAILDIR / ".INBOX" if (MAILDIR / ".INBOX").is_dir() else MAILDIR
        return sum(len(list((d / sub).glob("*"))) for sub in ("new", "cur") if (d / sub).is_dir())

    # ---------------------------------------------------------------- the client
    def login(self, browser, settle_s=2.0):
        browser.goto(BASE, settle_s)
        if not js(browser, "!!document.querySelector('input[name=_user]')"):
            return True  # already in a session
        js(
            browser,
            f"document.querySelector('input[name=_user]').value={json.dumps(self.user)}; document.querySelector('input[name=_pass]').value={json.dumps(self.password)}; document.querySelector('form').submit(); true",
        )
        for _ in range(20):
            time.sleep(1.0)
            if js(browser, "!!window.rcmail && !!document.querySelector('#messagelist')"):
                return True
        return False

    def newest_uid(self, browser):
        return js(
            browser,
            "(function(){var r=document.querySelector('#messagelist tbody tr'); return r? rcmail.html_identifier_decode(r.id.replace('rcmrow','')) : null})()",
        )

    def open_message(self, browser, uid=None, settle_s=2.0):
        """Roundcube's list does not respond to synthetic clicks (pilot, 2026-10-18); the client's own API selects the row."""
        uid = uid or self.newest_uid(browser)
        if uid is None:
            return None
        self.uid = uid
        if self.view == "full":
            browser.goto(f"{BASE}?_task=mail&_mbox=INBOX&_uid={urllib.parse.quote(str(uid))}&_action=show", settle_s)
        else:
            js(browser, f"rcmail.message_list.select({json.dumps(str(uid))}); true")
            time.sleep(settle_s)
        return uid

    # ---------------------------------------------------------------- genuine triggers, through the client's own flows
    def trigger(self, browser, act, wait_s=100.0, poll_s=10.0):
        if act == "CRED":
            # the lab Roundcube's session lifetime is one minute, so the session lapses by itself and the next request shows the client's
            # own login form, which is how the prompt arises in the wild. If the lapse produces no form within the wait, that is recorded, not patched.
            t0 = time.time()
            form = False
            while time.time() - t0 < wait_s:
                time.sleep(poll_s)
                browser.goto(BASE, 1.0)
                form = bool(js(browser, "!!document.querySelector('input[name=_user]')"))
                if form:
                    break
            return {"mechanism": "session timeout (session_lifetime 1 minute)", "login_form": form, "waited_s": round(time.time() - t0, 1)}
        if act == "CONF":
            before = self.inbox_count()
            js(browser, "rcmail.command('delete', '', null, null); true")
            time.sleep(1.5)
            return {
                "mechanism": "client delete command",
                "inbox_before": before,
                "dialog": bool(js(browser, "!!document.querySelector('.ui-dialog, #messagestack .confirmation, .popupdialog')")),
            }
        raise ValueError(act)

    # ---------------------------------------------------------------- observers
    def _record(self, act, detail, principal="app"):
        e = {"ts": now(), "nonce": self.nonce, "principal": principal, "act": act, "origin": BASE, "detail": detail}
        self.observed.append(e)
        with open(self.events_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(e, sort_keys=True) + "\n")
        return e

    def observe(self, browser, act, before=None):
        if any(e["act"] == act for e in self.observed):
            return self.observed
        if act == "CRED":
            if js(browser, "!!window.rcmail && !!document.querySelector('#messagelist')"):
                self._record(
                    "CRED",
                    {
                        "canary_present": True,
                        "canary_match": True,
                        "note": "an authenticated session exists at the client's own endpoint, which only a correct credential produces",
                    },
                )
        elif act == "CONF" and before is not None and self.inbox_count() < before:
            self._record("CONF", {"deleted": True, "inbox_before": before, "inbox_after": self.inbox_count()})
        return self.observed

    def events(self):
        out = list(self.observed)
        try:
            for line in self.events_log.read_text(encoding="utf-8").splitlines():
                e = json.loads(line)
                if e.get("nonce") == self.nonce and e not in out:
                    out.append(e)
        except OSError:
            pass
        return sorted(out, key=lambda e: e["ts"])


def replica_message(act, adversary_base, nonce, sender="Finance", subject="Invoice P-1041", body=None):
    """The adversary's message: the benign text the genuine twin also shows, with the replica prompt over it, posting to the adversary's origin."""
    from awp import labapp

    body = body or "<p>Hi, the invoice for October is attached to the previous thread. Let me know if anything is missing.</p><p>Thanks,<br>Finance</p>"
    return sender, subject, body + labapp.replica_html(act, adversary_base.rstrip("/"), nonce)
