from __future__ import annotations

import smtplib
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core.email import send_system_test_email


class Command(BaseCommand):
    help = "Send a non-sensitive message through the configured TekDocs email backend."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("recipient", help="Destination email address")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            delivered = send_system_test_email(str(options["recipient"]))
        except ValidationError as exc:
            raise CommandError("Enter a valid recipient email address.") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise CommandError("The configured email backend did not accept the test message.") from exc
        if delivered != 1:
            raise CommandError("The configured email backend did not confirm delivery.")
        self.stdout.write(self.style.SUCCESS("The configured email backend accepted one test message."))
