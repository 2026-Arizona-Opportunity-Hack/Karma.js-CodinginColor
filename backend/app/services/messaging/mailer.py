"""Email through Resend over HTTP (MSG-5, MSG-6). The key comes only from the environment.

Nothing here logs or returns the message text or the key. Errors are short fixed sentences.
In dry_run mode this module is never called, so no network request can happen.
"""

from dataclasses import dataclass, field

import httpx

RESEND_URL = "https://api.resend.com/emails"


@dataclass(frozen=True)
class MailConfig:
    mode: str  # "dry_run" or "live"
    api_key: str = field(default="", repr=False)
    mail_from: str = ""

    @property
    def live_ready(self) -> bool:
        return bool(self.api_key and self.mail_from)


class MailError(Exception):
    """The provider did not take the message. The text is safe to store and show."""


def send_email(client: httpx.Client, cfg: MailConfig, *, to: str, subject: str, body: str) -> str:
    """Returns the provider's message id. Raises MailError; never retries."""
    try:
        r = client.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={"from": cfg.mail_from, "to": [to], "subject": subject, "text": body},
            timeout=10.0,
        )
    except httpx.HTTPError:  # the exception text can echo the URL or headers: not kept
        raise MailError("Could not reach the mail provider.") from None
    if r.status_code // 100 != 2:
        raise MailError(f"The mail provider refused the message (HTTP {r.status_code}).")
    try:
        ref = str(r.json().get("id") or "")
    except ValueError:
        ref = ""
    return ref or "unknown"
