import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import sanitize_address


class ResendEmailBackend(BaseEmailBackend):
    """Django email backend that sends via the Resend HTTP API."""

    API_URL = "https://api.resend.com/emails"

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = settings.RESEND_API_KEY
        self.timeout = settings.RESEND_TIMEOUT

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if not self.fail_silently:
                raise ValueError("RESEND_API_KEY is not configured")
            return 0

        sent = 0
        for message in email_messages:
            try:
                self._send(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent

    def _send(self, message):
        payload = {
            "from": sanitize_address(message.from_email, message.encoding),
            "to": [
                sanitize_address(addr, message.encoding)
                for addr in message.recipients()
            ],
            "subject": message.subject,
        }

        if message.content_subtype == "html":
            payload["html"] = message.body
        else:
            payload["text"] = message.body

        if hasattr(message, "alternatives"):
            for alt_content, alt_type in message.alternatives:
                if alt_type == "text/html":
                    payload["html"] = alt_content
                    break

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.API_URL,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "durrat-tarim-django/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Resend HTTP {exc.code}: {body}") from exc
        except OSError as exc:
            raise RuntimeError(f"Resend network error: {exc}") from exc
