"""HR API keys at rest: Fernet round trip, no plain text in the ciphertext, and the
missing / short / changed server key cases. Uses throwaway server keys only."""

from django.test import SimpleTestCase, override_settings

from apps.integrations import secrets
from core.errors import ServiceError

TEST_KEY = 'CHANGE_ME-credential-key-0123456789abcdef'  # 32+ characters, never a real one
OTHER_KEY = 'another-CHANGE_ME-credential-key-9876543210'
HOSTS = ("api.breathehr.com", "api.sandbox.breathehr.info")


def hr(key: str) -> dict:
    return {"CREDENTIAL_KEY": key, "ALLOWED_HOSTS": HOSTS}


class SecretsTest(SimpleTestCase):
    @override_settings(HR_INTEGRATION=hr(TEST_KEY))
    def test_round_trip(self):
        self.assertTrue(secrets.is_configured())
        plain = "breathe-api-key-for-tests-only"
        token = secrets.encrypt(plain)
        self.assertNotIn(plain, token)
        self.assertNotEqual(token, secrets.encrypt(plain))  # a fresh IV every time
        self.assertEqual(secrets.decrypt(token), plain)

    def test_missing_or_short_server_key(self):
        for key in ("", "too-short"):
            with self.subTest(key=key), override_settings(HR_INTEGRATION=hr(key)):
                self.assertFalse(secrets.is_configured())
                with self.assertRaises(ServiceError) as ctx:
                    secrets.encrypt("anything")
                self.assertEqual((ctx.exception.code, ctx.exception.status), ("not_configured", 503))
                with self.assertRaises(ServiceError) as ctx:
                    secrets.decrypt("gAAAAAsomething")
                self.assertEqual(ctx.exception.code, "not_configured")

    @override_settings(HR_INTEGRATION=hr(TEST_KEY))
    def test_empty_ciphertext_means_no_key(self):
        with self.assertRaises(ServiceError) as ctx:
            secrets.decrypt("")
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("no_key", 409))

    def test_a_changed_server_key_cannot_read_old_keys(self):
        with override_settings(HR_INTEGRATION=hr(TEST_KEY)):
            token = secrets.encrypt("breathe-api-key-for-tests-only")
        with override_settings(HR_INTEGRATION=hr(OTHER_KEY)), self.assertRaises(ServiceError) as ctx:
            secrets.decrypt(token)
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("key_unreadable", 409))
        self.assertNotIn("breathe-api-key", ctx.exception.message)

    @override_settings(HR_INTEGRATION=hr(TEST_KEY))
    def test_tampered_ciphertext_is_refused(self):
        token = secrets.encrypt("breathe-api-key-for-tests-only")
        tampered = token[:-6] + ("A" if token[-6] != "A" else "B") + token[-5:]
        with self.assertRaises(ServiceError) as ctx:
            secrets.decrypt(tampered)
        self.assertEqual(ctx.exception.code, "key_unreadable")
