"""Offline readiness report. Never prints secrets or calls the provider."""

from django.conf import settings
from django.core.management.base import BaseCommand

from commerce.provider_config import XPaymentConfig
from commerce.providers.base import ProviderError


class Command(BaseCommand):
    help = "Check XPayment server configuration offline, without exposing credentials."

    def handle(self, *args, **options):
        self.stdout.write("Provider selected: " + str(settings.PAYMENT_PROVIDER == "xpayment"))
        try:
            XPaymentConfig.from_settings(require_gate=False)
            self.stdout.write("Configuration: valid format (not provider verification)")
        except ProviderError as exc:
            self.stdout.write("Configuration: " + exc.code)
        self.stdout.write("New payment gate: " + str(settings.XPAYMENT_ENABLED))
        self.stdout.write("Acceptance recorded: " + str(settings.XPAYMENT_PROTOCOL_VERIFIED))
        self.stdout.write(
            "Next steps: docs/xpayment-integration.md; no network requests performed."
        )
