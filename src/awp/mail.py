"""
File · src/awp/mail.py
Purpose · The one way the pilot and E0 deliver a message into the lab's own Maildir and read the pilot mail credential (the method, one of everything).
Description · Builds an RFC 822 message with an HTML body and writes it with Maildir semantics (tmp, then rename into new) under the pilot user's home created by the maintainer (/srv/awp-mail/awp). Reads the credential from the file the maintainer generated outside the tree; the credential never enters a log, an artifact or the tree. Shaped by 2026-10-18: Dovecot 2.4 serves the pilot user from a passwd-file with Maildir storage (experiments/E0/pilot/dovecot/99-awp-pilot.conf).
Inputs/Outputs · In: subject, HTML body, optional sender. Out: the path of the delivered file; (user, password) from the credential file.
Depends on · python3 standard library; /srv/awp-mail/awp owned by the invoking user.
Invariant · Delivery is atomic (rename); the password is returned to the caller only, never printed.
"""

from __future__ import annotations

import os
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

MAIL_HOME = Path("/srv/awp-mail/awp")
CREDENTIALS = MAIL_HOME / ".pilot-credentials"
IMAP_HOST, IMAP_PORT = "127.0.0.1", 143


def credentials():
    user, _, password = CREDENTIALS.read_text(encoding="utf-8").strip().partition(":")
    return user, password


def deliver(subject, html, sender="lab-sender@lab.invalid", recipient="awp@lab.invalid", text_alt=None):
    # WHY, Measured: Dovecot 2.4 with a blank mail_inbox_path keeps INBOX in Maildir/.INBOX, not at the Maildir root; deliver where it looks
    root = MAIL_HOME / "Maildir"
    maildir = root / ".INBOX" if (root / ".INBOX").is_dir() else root
    for d in ("tmp", "new", "cur"):
        (maildir / d).mkdir(parents=True, exist_ok=True)
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, recipient, subject
    msg["Date"], msg["Message-ID"] = formatdate(localtime=True), make_msgid(domain="lab.invalid")
    msg.set_content(text_alt or "This message is best viewed in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")
    name = f"{int(time.time())}.P{os.getpid()}Q{time.monotonic_ns()}.awp"  # a fixed token, never the hostname: the filename ends up in artifacts
    tmp, new = maildir / "tmp" / name, maildir / "new" / name
    tmp.write_bytes(msg.as_bytes())
    os.rename(tmp, new)
    return new
