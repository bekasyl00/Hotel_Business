from unittest.mock import patch
import httpx
from django.test import TestCase, SimpleTestCase, override_settings
from rest_framework.test import APIClient
from .models import GuestAccount
from .otp_delivery import SMSCCodeDelivery
from .errors import Problem


@override_settings(DEBUG=True, GUEST_AUTH_DEMO_OTP=True, GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION=False)
class NativeChallengeTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def post(self, action, data):
        return self.client.post('/api/v1/mobile-auth/' + action, data, format='json')

    def challenge(self, purpose='register'):
        response = self.post('challenges', {'phone': '+77010000333', 'purpose': purpose})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_register_scope_replay_and_reset_revoke(self):
        c = self.challenge()
        data = {'challengeId': c['challengeId'], 'scopeToken': c['scopeToken'], 'code': c['demoCode'],
                'name': 'Test Guest', 'password': 'password123', 'deviceName': 'Test device'}
        wrong = self.post('register', {**data, 'scopeToken': 'tampered'})
        self.assertEqual(wrong.status_code, 422)
        registered = self.post('register', data)
        self.assertEqual(registered.status_code, 201, registered.data)
        self.assertNotIn('sessionid', registered.cookies)
        self.assertFalse(GuestAccount.objects.get().phone_verified_at)
        self.assertEqual(self.post('register', data).status_code, 422)
        reset = self.challenge('reset')
        result = self.post('reset', {'challengeId':reset['challengeId'], 'scopeToken':reset['scopeToken'],
                                   'code':reset['demoCode'], 'password':'newpassword123'})
        self.assertEqual(result.status_code, 200, result.data)
        token = registered.data['accessToken']
        response = self.client.get('/api/v1/guest-auth/session', HTTP_AUTHORIZATION='Bearer '+token)
        self.assertEqual(response.status_code, 401)

    def test_wrong_code_is_not_accepted(self):
        c = self.challenge()
        data = {'challengeId':c['challengeId'], 'scopeToken':c['scopeToken'], 'code':'invalid',
                'name':'Test', 'password':'password123', 'deviceName':'Test'}
        for _ in range(5):
            self.assertEqual(self.post('register',data).status_code,422)
        self.assertEqual(self.post('register',{**data,'code':c['demoCode']}).status_code,422)
        self.assertFalse(GuestAccount.objects.exists())


@override_settings(GUEST_OTP_PROVIDER='smsc', SMSC_API_KEY='secret-test-key', SMSC_SENDER='TEST')
class SMSCTransportTests(SimpleTestCase):
    @patch('booking.otp_delivery.httpx.post')
    def test_accepted_send_never_exposes_code(self, post):
        post.return_value = httpx.Response(200,json={'id':12,'cnt':1},request=httpx.Request('POST','https://smsc.kz/rest/send/'))
        self.assertEqual(SMSCCodeDelivery().send_code('+77010000000','123456'), {'mode':'sms'})
        self.assertEqual(post.call_count,1)
        self.assertFalse(post.call_args.kwargs['follow_redirects'])

    @patch('booking.otp_delivery.httpx.post',side_effect=httpx.ReadTimeout('secret provider detail'))
    def test_timeout_never_retries_or_leaks(self, post):
        with self.assertRaises(Problem) as error:
            SMSCCodeDelivery().send_code('+77010000000','123456')
        self.assertEqual(post.call_count,1)
        self.assertNotIn('secret',str(error.exception))

    @patch('booking.otp_delivery.httpx.post')
    def test_provider_rejection_is_sanitized(self, post):
        post.return_value = httpx.Response(200, json={'error_code': 1, 'error': 'private detail'},
                                          request=httpx.Request('POST', 'https://smsc.kz/rest/send/'))
        with self.assertRaises(Problem) as error:
            SMSCCodeDelivery().send_code('+77010000000', '123456')
        self.assertNotIn('private detail', str(error.exception))
        self.assertEqual(post.call_count, 1)


@override_settings(DEBUG=False, GUEST_AUTH_DEMO_OTP=False,
                   GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION=False,
                   GUEST_OTP_PROVIDER='smsc', SMSC_API_KEY='test-only', SMSC_SENDER='TEST',
                   GUEST_OTP_DAILY_LIMIT=2)
class ProductionChallengeTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def post(self, action, data):
        return self.client.post('/api/v1/mobile-auth/' + action, data, format='json')

    @patch('booking.otp_delivery.httpx.post', side_effect=httpx.ReadTimeout('private'))
    def test_ambiguous_send_keeps_cooldown_and_consumes_global_budget(self, post):
        from .models import GuestChallenge
        data = {'phone': '+77010000444', 'purpose': 'register'}
        self.assertEqual(self.post('challenges', data).status_code, 503)
        self.assertEqual(GuestChallenge.objects.count(), 1)
        self.assertEqual(self.post('challenges', data).status_code, 429)
        self.assertEqual(self.post('challenges', {**data, 'phone': '+77010000555'}).status_code, 429)
        self.assertEqual(post.call_count, 1)

    @patch('booking.guest_auth.secrets.randbelow', return_value=123456)
    @patch('booking.otp_delivery.httpx.post')
    def test_real_challenge_verifies_phone_without_returning_code(self, post, random):
        post.return_value = httpx.Response(200, json={'id': 1, 'cnt': 1},
                                          request=httpx.Request('POST', 'https://smsc.kz/rest/send/'))
        response = self.post('challenges', {'phone': '+77010000444', 'purpose': 'register'})
        self.assertEqual(response.status_code, 200, response.data)
        c = response.data
        self.assertNotIn('demoCode', c)
        registered = self.post('register', {'challengeId': c['challengeId'], 'scopeToken': c['scopeToken'],
                                           'code': '123456', 'name': 'Guest', 'password': 'password123',
                                           'deviceName': 'Android'})
        self.assertEqual(registered.status_code, 201, registered.data)
        self.assertIsNotNone(GuestAccount.objects.get().phone_verified_at)

    def test_old_demo_challenge_cannot_be_used_after_production_switch(self):
        with override_settings(DEBUG=True, GUEST_AUTH_DEMO_OTP=True, GUEST_OTP_PROVIDER='disabled'):
            response = self.post('challenges', {'phone': '+77010000444', 'purpose': 'register'})
        c = response.data
        result = self.post('register', {'challengeId': c['challengeId'], 'scopeToken': c['scopeToken'],
                                      'code': c['demoCode'], 'name': 'Guest', 'password': 'password123',
                                      'deviceName': 'iPhone'})
        self.assertEqual(result.status_code, 422)
        self.assertFalse(GuestAccount.objects.exists())


@override_settings(DEBUG=False, GUEST_AUTH_DEMO_OTP=False, GUEST_OTP_PROVIDER='disabled',
                   GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION=True)
class TemporaryNativeSignupTests(TestCase):
    def test_explicit_temporary_mode_works_without_claiming_phone_ownership(self):
        client = APIClient(enforce_csrf_checks=True)
        configuration = client.get('/api/v1/mobile-auth/configuration')
        self.assertEqual(configuration.data['registrationMode'], 'password')
        self.assertFalse(configuration.data['passwordResetAvailable'])
        data = {'phone': '+77010000666', 'name': 'Temporary Guest', 'password': 'testpass123', 'deviceName': 'Android'}
        response = client.post('/api/v1/mobile-auth/register', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn('sessionid', response.cookies)
        self.assertFalse(response.data['account']['phoneVerified'])
        self.assertIsNone(GuestAccount.objects.get().phone_verified_at)
        profile = client.get('/api/v1/profile', HTTP_AUTHORIZATION='Bearer ' + response.data['accessToken'])
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(client.post('/api/v1/mobile-auth/register', data, format='json').status_code, 409)
        with override_settings(GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION=False):
            disabled = client.post('/api/v1/mobile-auth/register', {**data, 'phone': '+77010000777'}, format='json')
            self.assertEqual(disabled.status_code, 503)
