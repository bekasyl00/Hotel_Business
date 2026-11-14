"""Server-only OTP delivery. A timeout is ambiguous and is never automatically retried."""
import httpx
from django.conf import settings
from .errors import Problem


def sms_configured():
    return (getattr(settings, 'GUEST_OTP_PROVIDER', '') == 'smsc'
            and bool(getattr(settings, 'SMSC_API_KEY', ''))
            and bool(getattr(settings, 'SMSC_SENDER', '')))


class SMSCCodeDelivery:
    verifies_phone = True

    def send_code(self, phone, code):
        if not sms_configured():
            raise Problem('Отправка кода временно недоступна.', 503, 'sms_unavailable')
        try:
            response = httpx.post('https://smsc.kz/rest/send/', json={
                'apikey': settings.SMSC_API_KEY, 'phones': phone,
                'mes': f'Тыныс: {code}. Код на 5 минут. Никому не сообщайте.',
                'sender': settings.SMSC_SENDER, 'fmt': 3, 'charset': 'utf-8',
            }, timeout=httpx.Timeout(10, connect=3), follow_redirects=False)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get('error_code') or not data.get('id') or not data.get('cnt'):
                raise ValueError('provider_rejected')
        except (httpx.HTTPError, ValueError, TypeError):
            # Never surface request/response/phone/code/API key in logs or API errors.
            raise Problem('Не удалось подтвердить отправку кода. Повторите позже.', 503, 'sms_delivery_unconfirmed') from None
        return {'mode': 'sms'}
