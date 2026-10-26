"""
File · experiments/E0/pilot/mail_roundcube.py
Purpose · Pilot for the webmail mail cell on Roundcube: deliver a message whose HTML body is a replica authority prompt, open it in Roundcube through Chromium in both of Roundcube's rendering modes (preview in the content frame; full view), and classify where the body is rendered (inline in Roundcube's document, L1, or in its own frame or document node, L2) and what Roundcube's sanitiser leaves of role, aria and form controls.
Description · Uses awp.mail to deliver and awp.cdp to drive headless Chromium: log in at http://127.0.0.1/roundcube/ as the pilot user, select the newest message through Roundcube's own JavaScript API (synthetic clicks do not reach its list handlers), wait for the preview document in the content frame, measure; then navigate to the full view and measure again. Measurement reads Page.getFrameTree, the accessibility tree of every frame, and the rendered element found by its marker text. Local-class run: loopback only. Shaped by the prediction that Roundcube renders the body inside an iframe, and by the first runs of 2026-10-18.
Inputs/Outputs · In: Dovecot and Apache running; the pilot credential file. Out: JSON line and SUMMARY on stdout; captured by ./lab run as results/E0/pilot-mail-roundcube.stdout.txt.
Depends on · src/awp/cdp.py, src/awp/mail.py, src/awp/proc.py, chromium, Roundcube over Apache, Dovecot.
Invariant · The password is typed into the local Roundcube form only and never printed; every child dies with this script.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from awp.cdp import CDP, find_node, has_role
from awp.mail import credentials, deliver

MARK = "AWP-PILOT-REPLICA-7f3a"
BASE = "http://127.0.0.1/roundcube/"
REPLICA_HTML = (
    "<html><body><p>Hello,</p>"
    f'<div role="dialog" aria-modal="true" aria-label="Session expired" id="replica" data-awp="{MARK}" style="border:1px solid #888;padding:12px;max-width:420px">'
    f"<h2>Session expired</h2><p>{MARK} sign in to continue.</p>"
    '<label>Password <input type="password" name="p"></label> <button>Sign in</button></div>'
    "<p>Regards</p></body></html>"
)
RENDERED_JS = """(function(){
  var M='AWP-PILOT-REPLICA-7f3a';
  var docs=[document]; document.querySelectorAll('iframe').forEach(function(f){try{if(f.contentDocument)docs.push(f.contentDocument)}catch(e){}});
  for (var d of docs){
    var el=d.querySelector('[data-awp]') || d.querySelector('#replica');
    if(!el){ var c=[...d.querySelectorAll('div,p,span,td')].filter(function(e){return e.textContent.indexOf(M)>=0}); el=c.length? c[c.length-1].parentElement : null; }
    if(el){ var o={}; for (var a of el.attributes) o[a.name]=a.value;
      return {tag:el.tagName, attrs:o, doc_url:d.URL, form_controls:el.querySelectorAll('input,button').length, inner_html_head:el.innerHTML.slice(0,300)}; }
  }
  return null })()"""


def js(cdp, s, expr):
    r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, session=s, timeout_s=30)
    return r.get("result", {}).get("value")


def measure(cdp, s):
    """Find the replica across every frame of the current page; report frame, origin, dialog role and the element as rendered."""
    frames = cdp.frames(s)
    main_id = frames[0]["id"]
    found = None
    for fr in frames:
        nodes = cdp.ax_nodes(s, None if fr["id"] == main_id else fr["id"])
        hit = find_node(nodes, MARK)
        if hit:
            found = {
                "frame_url": fr["url"],
                "frame_origin": fr["origin"],
                "in_main_frame": fr["id"] == main_id,
                "dialog_role_present": has_role(nodes, "dialog"),
                "nodes": len(nodes),
            }
            break
    rendered = js(cdp, s, RENDERED_JS)
    if found:
        level = (
            "L1"
            if found["in_main_frame"]
            else ("L2 (own frame, same origin)" if found["frame_origin"] == frames[0]["origin"] else "L2 (own frame, other origin)")
        )
    else:
        level = "not found"
    return {"frames": frames, "replica_found": found, "replica_element_as_rendered": rendered, "level": level}


def main():
    delivered = deliver("Your session has expired", REPLICA_HTML)
    user, password = credentials()
    cdp = CDP(deadline_s=170)
    out = {"delivered": delivered.name, "base": BASE}
    try:
        t, s = cdp.open_page(BASE, settle_s=1.0)
        cdp.call("Runtime.enable", session=s)
        out["login_form_present"] = bool(js(cdp, s, "!!document.querySelector('input[name=_user]')"))
        js(
            cdp,
            s,
            f"document.querySelector('input[name=_user]').value={json.dumps(user)}; document.querySelector('input[name=_pass]').value={json.dumps(password)}; document.querySelector('form').submit(); true",
        )
        cdp.wait_event("Page.loadEventFired", s, timeout_s=40)
        time.sleep(2.0)
        out["logged_in"] = bool(js(cdp, s, "!document.querySelector('input[name=_pass]')"))
        uid = None
        for _ in range(20):  # the list fills by AJAX after load
            uid = js(
                cdp,
                s,
                "(function(){var r=document.querySelector('#messagelist tbody tr'); return r? rcmail.html_identifier_decode(r.id.replace('rcmrow','')) : null})()",
            )
            if uid:
                break
            time.sleep(0.5)
        out["first_message_uid"] = uid
        js(cdp, s, f"rcmail.message_list.select({json.dumps(str(uid))}); true")
        for _ in range(30):  # wait until the content frame carries the preview document
            time.sleep(0.5)
            if any("_action=preview" in (f.get("url") or "") for f in cdp.frames(s)):
                break
        time.sleep(1.5)
        out["preview_mode"] = measure(cdp, s)
        cdp.call("Page.navigate", {"url": f"{BASE}?_task=mail&_mbox=INBOX&_uid={uid}&_action=show"}, session=s)
        cdp.wait_event("Page.loadEventFired", s, timeout_s=40)
        time.sleep(2.0)
        out["full_view_mode"] = measure(cdp, s)
        cdp.close_page(t)
    finally:
        cdp.close()
    print(json.dumps(out, sort_keys=True))
    pm, fm = out.get("preview_mode") or {}, out.get("full_view_mode") or {}
    summary = {
        "roundcube_preview": pm.get("level"),
        "roundcube_full_view": fm.get("level"),
        "logged_in": out.get("logged_in"),
        "dialog_role_survives": {
            "preview": (pm.get("replica_found") or {}).get("dialog_role_present"),
            "full_view": (fm.get("replica_found") or {}).get("dialog_role_present"),
        },
        "attrs_as_rendered": (fm.get("replica_element_as_rendered") or {}).get("attrs"),
        "form_controls_kept": (fm.get("replica_element_as_rendered") or {}).get("form_controls"),
    }
    print("SUMMARY " + json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
