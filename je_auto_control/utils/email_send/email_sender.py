"""Send email via SMTP for the ``AC_send_email`` action step.

Dependency-free (stdlib ``smtplib`` + ``email``). Parameters are grouped
into two dicts so the action stays JSON-friendly and within the project's
argument-count limit:

* ``message`` — ``{sender, to, subject, body, cc?, html?, attachments?}``
* ``smtp``    — ``{host, port?, username?, password?, use_tls?, use_ssl?,
  timeout?}``

Security: TLS is on by default (STARTTLS on 587, or implicit SSL when
``use_ssl`` is set), the connection uses a verified default SSL context,
every call has an explicit timeout, and credentials are never logged.
Imports no ``PySide6`` so it stays fully headless.
"""
import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Dict, List, Mapping, Optional


def _as_list(value: Any) -> List[str]:
    """Normalise a string / iterable of addresses into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _attach_files(mime: EmailMessage, attachments: Any) -> None:
    """Attach each file path in ``attachments`` to ``mime``."""
    for raw in attachments or []:
        path = os.path.realpath(str(raw))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"attachment not found: {raw}")
        ctype, _ = mimetypes.guess_type(path)
        maintype, subtype = (
            ctype.split("/", 1) if ctype else ("application", "octet-stream"))
        with open(path, "rb") as handle:
            mime.add_attachment(handle.read(), maintype=maintype,
                                subtype=subtype, filename=os.path.basename(path))


def _build_message(message: Mapping[str, Any]) -> EmailMessage:
    """Assemble an :class:`EmailMessage` from the ``message`` spec."""
    sender = message.get("sender") or message.get("from")
    recipients = _as_list(message.get("to"))
    if not sender or not recipients:
        raise ValueError("email requires 'sender' and at least one 'to'")
    mime = EmailMessage()
    mime["From"] = str(sender)
    mime["To"] = ", ".join(recipients)
    cc = _as_list(message.get("cc"))
    if cc:
        mime["Cc"] = ", ".join(cc)
    mime["Subject"] = str(message.get("subject", ""))
    body = str(message.get("body", ""))
    mime.set_content(body, subtype="html" if message.get("html") else "plain")
    _attach_files(mime, message.get("attachments"))
    return mime


def _login_send(server: smtplib.SMTP, username: Optional[str],
                password: Optional[str], mime: EmailMessage) -> None:
    """Authenticate (when credentials are given) and send the message."""
    if username and password:
        server.login(username, password)
    server.send_message(mime)


def _tls_context() -> ssl.SSLContext:
    """Return a hardened TLS context: verified certs over TLS 1.2 or newer."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _deliver(mime: EmailMessage, smtp: Mapping[str, Any]) -> None:
    """Open an SMTP(S) connection per ``smtp`` config and send ``mime``."""
    host = smtp.get("host")
    if not host:
        raise ValueError("smtp 'host' is required")
    port = int(smtp.get("port", 587))
    timeout = float(smtp.get("timeout", 30.0))
    username, password = smtp.get("username"), smtp.get("password")
    if bool(smtp.get("use_ssl", False)):
        with smtplib.SMTP_SSL(str(host), port, timeout=timeout,
                              context=_tls_context()) as server:
            _login_send(server, username, password, mime)
        return
    with smtplib.SMTP(str(host), port, timeout=timeout) as server:
        if bool(smtp.get("use_tls", True)):
            server.starttls(context=_tls_context())
        _login_send(server, username, password, mime)


def send_email(message: Mapping[str, Any],
               smtp: Mapping[str, Any]) -> Dict[str, Any]:
    """Send an email and return a small result dict.

    :param message: ``{sender, to, subject, body, cc?, html?, attachments?}``.
    :param smtp: ``{host, port?, username?, password?, use_tls?, use_ssl?,
        timeout?}``; TLS is enabled by default.
    """
    mime = _build_message(message)
    _deliver(mime, smtp)
    return {"sent": True, "to": mime["To"], "subject": mime["Subject"]}
