import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('preflight', Path(__file__).parents[1] / 'scripts/production-preflight.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ProductionPreflightTests(unittest.TestCase):
    def test_missing_configuration_fails_closed(self):
        errors = module.failures({})
        self.assertTrue(any('DEBUG' in value for value in errors))
        self.assertTrue(any('DATABASE_URL' in value for value in errors))

    def test_no_secret_values_in_diagnostics(self):
        secret = 'never-print-this-password'
        errors = module.failures({'DATABASE_URL': f'https://user:{secret}@host',
                                  'PAYMENTS_PUBLIC_API_ORIGIN': f'https://user:{secret}@host',
                                  'DEBUG': 'true'})
        self.assertNotIn(secret, '\n'.join(errors))
        self.assertTrue(any('PAYMENTS_PUBLIC_API_ORIGIN' in value for value in errors))

    def test_unsafe_registration_and_payment_modes_are_rejected(self):
        errors = module.failures({'GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION': 'true',
                                  'PAYMENT_PROVIDER': 'simulator', 'ALLOWED_HOSTS': '*'})
        for field in ('GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION', 'PAYMENT_PROVIDER', 'ALLOWED_HOSTS'):
            self.assertTrue(any(field in value for value in errors))

if __name__ == '__main__':
    unittest.main()
