"""Email template functions — text and substitution testing."""
from app.services import email_templates


class TestErasureConfirmed:
    def test_it_has_all_three_languages(self):
        for lang in ("en", "pt-BR", "es"):
            subject, body = email_templates.erasure_confirmed(lang, protocol="DSR-2026-000123", when="2026-09-22 10:00")
            assert subject
            assert "DSR-2026-000123" in body

    def test_it_falls_back_to_a_known_language_for_an_unknown_one(self):
        subject, body = email_templates.erasure_confirmed("xx-XX", protocol="DSR-2026-000123", when="now")
        assert subject
