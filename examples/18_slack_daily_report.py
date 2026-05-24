"""End-to-end workflow: pull Slack messages → summarise → render PDF → email.

This is a self-contained pipeline that ties together five AutoControl
features into something an operations team would actually run on a
schedule:

1. **Scheduler** — fires the pipeline once per day at 18:00.
2. **Slack pull** — hits Slack's Web API via the standard ``requests``
   library; falls back to a stub message list when run without
   credentials (so the demo always completes).
3. **Anthropic summarisation** — uses the existing ``plan_actions`` /
   ``run_from_description`` plumbing's underlying client, called
   directly with a system prompt + the message list. Falls back to a
   deterministic mock summary if ``ANTHROPIC_API_KEY`` is unset.
4. **HTML → PDF** — generates an HTML report with AutoControl's
   built-in templater, then renders it to PDF using ``weasyprint``
   when installed; otherwise prints the HTML path.
5. **Email** — sends the PDF as an attachment via stdlib ``smtplib``.

Environment variables (all optional — pipeline degrades gracefully):

    SLACK_BOT_TOKEN       Bot token with ``channels:history``
    SLACK_CHANNEL_ID      Channel to summarise (default: #general)
    ANTHROPIC_API_KEY     Enables real summarisation
    SMTP_HOST             Mail server host
    SMTP_PORT             Mail server port (default 587)
    SMTP_USER / SMTP_PASS Login credentials
    SMTP_FROM / SMTP_TO   Sender + recipient addresses

The script is meant as a starting point: every step is a clearly-named
function so you can replace pieces (e.g. swap Slack for Discord) by
editing one block.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional, Sequence

import je_auto_control as ac


# --- data classes ---------------------------------------------------

@dataclass(frozen=True)
class SlackMessage:
    """One Slack message stripped to the fields the summariser needs."""
    user: str
    timestamp: float
    text: str


# --- pipeline steps -------------------------------------------------

def fetch_slack_messages(channel_id: str, *,
                         since_hours: int = 24,
                         token: Optional[str] = None,
                         ) -> List[SlackMessage]:
    """Pull Slack ``conversations.history`` over the last N hours.

    Returns a deterministic stub message list when no token is set so
    the rest of the pipeline still runs.
    """
    if not token:
        print("  (no SLACK_BOT_TOKEN — using stub messages)")
        return _stub_messages()
    oldest = (
        datetime.now(tz=timezone.utc) - timedelta(hours=since_hours)
    ).timestamp()
    params = urllib.parse.urlencode({
        "channel": channel_id,
        "oldest": f"{oldest:.6f}",
        "limit": 200,
    })
    request = urllib.request.Request(
        f"https://slack.com/api/conversations.history?{params}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as error:
        print(f"  warning: Slack call failed ({error}); using stub")
        return _stub_messages()
    if not body.get("ok"):
        print(f"  warning: Slack API error: {body.get('error')}; using stub")
        return _stub_messages()
    return [
        SlackMessage(
            user=str(msg.get("user") or "<unknown>"),
            timestamp=float(msg.get("ts") or 0.0),
            text=str(msg.get("text") or ""),
        )
        for msg in body.get("messages", [])
        if msg.get("text")
    ]


def _stub_messages() -> List[SlackMessage]:
    now = datetime.now(tz=timezone.utc).timestamp()
    return [
        SlackMessage(user="alice", timestamp=now - 3600,
                      text="The deployment to staging is green."),
        SlackMessage(user="bob", timestamp=now - 1800,
                      text="I'll start the migration at 22:00 UTC."),
        SlackMessage(user="charlie", timestamp=now - 600,
                      text="Logs look quiet — no errors in the last hour."),
    ]


def summarise(messages: Sequence[SlackMessage]) -> str:
    """Hand the message list to Anthropic; fall back to a stitched recap."""
    bullet_lines = "\n".join(
        f"- {msg.user}: {msg.text}" for msg in messages
    )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  (no ANTHROPIC_API_KEY — stitching messages directly)")
        return "Today's digest:\n" + bullet_lines
    try:
        import anthropic  # noqa: F401  # nosemgrep: codacy.python.openai.import-without-guardrails  # reason: see anthropic.py backend rationale
        client = __import__("anthropic").Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": (
                    "Summarise these Slack messages in three short "
                    "bullet points suitable for an end-of-day email:\n\n"
                    + bullet_lines
                ),
            }],
        )
        return response.content[0].text  # type: ignore[union-attr]
    except (ImportError, RuntimeError, OSError) as error:
        print(f"  warning: Anthropic call failed ({error}); stitching")
        return "Today's digest:\n" + bullet_lines


def render_report(summary: str, raw_messages: Sequence[SlackMessage],
                   output_dir: Path) -> Path:
    """Render an HTML report + (if weasyprint is available) a PDF.

    Returns the path to the artefact that should be emailed — the PDF
    when WeasyPrint is installed, otherwise the HTML file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(tz=timezone.utc).date().isoformat()
    rows = "".join(
        f"<li><strong>{m.user}</strong>: {m.text}</li>"
        for m in raw_messages
    )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Daily Slack digest — {today}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2em; }}
  h1 {{ border-bottom: 2px solid #444; padding-bottom: .3em; }}
  pre {{ background: #f5f5f5; padding: 1em; border-radius: 4px; }}
  ul {{ line-height: 1.5em; }}
</style></head>
<body>
<h1>Daily Slack digest — {today}</h1>
<h2>Summary</h2>
<pre>{summary}</pre>
<h2>Raw messages ({len(raw_messages)})</h2>
<ul>{rows}</ul>
</body></html>
"""
    # Anchor the filename inside output_dir's resolved path so a
    # malicious ``today`` (e.g. ``../etc/passwd``) can't escape — even
    # though ``today`` is internally generated, validating here keeps
    # Sonar's S2083 happy and protects future callers.
    safe_name = os.path.basename(f"digest-{today}.html")
    safe_root = output_dir.resolve()
    html_path = (safe_root / safe_name).resolve()
    if safe_root not in html_path.parents:
        raise ValueError(f"refusing path-traversal name: {today!r}")
    html_path.write_text(html, encoding="utf-8")
    try:
        from weasyprint import HTML
    except ImportError:
        print("  (no weasyprint — sending the HTML instead)")
        return html_path
    pdf_path = output_dir / f"digest-{today}.pdf"
    HTML(string=html).write_pdf(str(pdf_path))
    return pdf_path


def email_report(artefact: Path, *,
                  subject: str,
                  sender: str, recipient: str,
                  smtp_host: str, smtp_port: int = 587,
                  smtp_user: Optional[str] = None,
                  smtp_pass: Optional[str] = None) -> None:
    """Send ``artefact`` as an attachment via STARTTLS-SMTP."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"Daily Slack digest attached.\n\nGenerated: {datetime.now().isoformat()}",
    )
    mime_type = (
        "application/pdf" if artefact.suffix == ".pdf"
        else "text/html"
    )
    maintype, subtype = mime_type.split("/", 1)
    message.add_attachment(
        artefact.read_bytes(), maintype=maintype, subtype=subtype,
        filename=artefact.name,
    )
    context = ssl.create_default_context()
    # Pin the minimum to TLS 1.2 even on older Pythons whose defaults
    # may still allow TLS 1.0/1.1 (S4423). Python 3.10+ already does
    # this by default; the explicit assignment is a belt-and-braces.
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30.0) as server:
        server.starttls(context=context)
        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)
        server.send_message(message)


# --- AutoControl wiring --------------------------------------------

def run_pipeline_once() -> int:
    """Execute one pass of the pipeline; return 0 on success, 1 on error."""
    print("Slack daily digest pipeline starting…")
    channel = os.environ.get("SLACK_CHANNEL_ID", "C0000000000")
    messages = fetch_slack_messages(
        channel,
        since_hours=24,
        token=os.environ.get("SLACK_BOT_TOKEN"),
    )
    print(f"  pulled {len(messages)} messages from {channel}")

    summary = summarise(messages)
    print(f"  summary ready ({len(summary)} chars)")

    output_dir = Path("./slack_digests")
    artefact = render_report(summary, messages, output_dir)
    print(f"  artefact: {artefact}")

    smtp_host = os.environ.get("SMTP_HOST")
    sender = os.environ.get("SMTP_FROM")
    recipient = os.environ.get("SMTP_TO")
    if not (smtp_host and sender and recipient):
        print("  (SMTP_* unset — skipping email step; artefact saved locally)")
        return 0
    try:
        email_report(
            artefact,
            subject=f"Slack daily digest — {datetime.now().date()}",
            sender=sender, recipient=recipient,
            smtp_host=smtp_host,
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_user=os.environ.get("SMTP_USER"),
            smtp_pass=os.environ.get("SMTP_PASS"),
        )
    except (OSError, smtplib.SMTPException) as error:
        print(f"  email failed: {error}")
        return 1
    print(f"  emailed {artefact.name} to {recipient}")
    return 0


def schedule_daily(hour: int = 18, minute: int = 0) -> None:
    """Register the pipeline with the AutoControl scheduler.

    Uses a cron expression so the firing time survives process restarts.
    """
    bridge_script = Path(__file__).with_name("18_slack_pipeline_bridge.json")
    bridge_script.write_text(
        json.dumps([
            ["AC_shell_command", {
                "command": f"{sys.executable} {Path(__file__).resolve()} --run",
            }],
        ]),
        encoding="utf-8",
    )
    ac.default_scheduler.add_cron_job(
        script_path=str(bridge_script),
        cron_expression=f"{minute} {hour} * * *",
        job_id="slack-daily-digest",
    )
    ac.default_scheduler.start()
    print(f"scheduled at {hour:02d}:{minute:02d} UTC daily — Ctrl-C to stop.")


def main() -> int:
    if "--run" in sys.argv[1:]:
        return run_pipeline_once()
    if "--schedule" in sys.argv[1:]:
        schedule_daily()
        import time
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            ac.default_scheduler.stop()
            return 0
    # Default: run once and exit.
    return run_pipeline_once()


if __name__ == "__main__":
    sys.exit(main())
