"""Route by frozen provider and merchant, never by today's checkout selection."""

from django.conf import settings
from django.db.models import Q

from .provider_config import HalykConfig, XPaymentConfig
from .providers.base import ProviderError

PROVIDERS = {
    "halyk_epay": ("sandbox", HalykConfig),
    "xpayment": ("production", XPaymentConfig),
}


def configuration(provider=None, *, require_gate=True):
    name = provider or settings.PAYMENT_PROVIDER
    if name not in PROVIDERS:
        raise ProviderError("bank_payments_disabled")
    return PROVIDERS[name][1].from_settings(require_gate=require_gate)


def provider_for(payment, *, creating=False):
    config = configuration(payment.provider, require_gate=creating)
    environment = PROVIDERS[payment.provider][0]
    if payment.environment != environment or payment.merchant_scope != config.merchant_scope:
        raise ProviderError("payment_merchant_configuration_changed")
    if payment.provider == "halyk_epay":
        from .providers.halyk_epay import HalykProvider

        if payment.shop_id != config.shop_id or payment.terminal_id != config.terminal_id:
            raise ProviderError("payment_merchant_configuration_changed")
        return HalykProvider(config)
    from .providers.xpayment import XPaymentProvider

    return XPaymentProvider(config)


def processable_jobs():
    """Missing credentials preserve jobs; a closed creation gate still allows settlement."""
    query = Q(pk__in=[])
    for name, (environment, _) in PROVIDERS.items():
        try:
            config = configuration(name, require_gate=False)
        except ProviderError:
            continue
        scope = Q(
            payment__provider=name,
            payment__environment=environment,
            payment__merchant_scope=config.merchant_scope,
        )
        try:
            configuration(name)
        except ProviderError:
            scope &= ~Q(kind="create") | Q(payment__creation_started_at__isnull=False)
        query |= scope
    return query
