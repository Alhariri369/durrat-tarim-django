import json
from unittest.mock import MagicMock, patch

from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from .email_backend import ResendEmailBackend


@override_settings(RESEND_API_KEY="re_test", RESEND_TIMEOUT=10)
class ResendEmailBackendTests(SimpleTestCase):
    @patch("durrat_tarim.email_backend.urllib.request.urlopen")
    def test_send_includes_required_headers_and_payload(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"id":"email-id"}'
        urlopen.return_value = response
        backend = ResendEmailBackend()
        message = EmailMessage(
            subject="Verify your email",
            body="Verification message",
            from_email="Durrat Tarim <noreply@example.com>",
            to=["user@example.com"],
        )

        sent = backend.send_messages([message])

        self.assertEqual(sent, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer re_test")
        self.assertEqual(request.get_header("User-agent"), "durrat-tarim-django/1.0")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(
            json.loads(request.data),
            {
                "from": "Durrat Tarim <noreply@example.com>",
                "to": ["user@example.com"],
                "subject": "Verify your email",
                "text": "Verification message",
            },
        )
        urlopen.assert_called_once_with(request, timeout=10)

    @override_settings(RESEND_API_KEY="")
    def test_send_requires_api_key(self):
        backend = ResendEmailBackend()
        message = EmailMessage(
            subject="Test",
            body="Test",
            from_email="noreply@example.com",
            to=["user@example.com"],
        )

        try:
            backend.send_messages([message])
        except ValueError as exc:
            self.assertEqual(str(exc), "RESEND_API_KEY is not configured")
        else:
            self.fail("Sending without RESEND_API_KEY did not raise ValueError")
