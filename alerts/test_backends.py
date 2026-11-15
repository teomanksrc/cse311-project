from django.core.mail.backends.base import BaseEmailBackend


class Broken(BaseEmailBackend):
    """A mail server that is down: every send raises OSError."""

    def send_messages(self, email_messages):
        raise OSError("mail server unreachable")
