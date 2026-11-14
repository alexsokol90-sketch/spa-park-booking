"""Защита: подпись сессий веб-чата, ограничение частоты, заголовки, проверка ключа в окне записи."""
from app import security


def test_web_session_signature():
    uid, sig = security.new_web_session()
    assert uid < 0 and security.verify(uid, sig)
    assert not security.verify(uid, "0" * 32)
    assert not security.verify(uid - 1, sig)          # чужой идентификатор с моей подписью не пройдёт
    assert not security.verify(-uid, security.sign(-uid))  # положительные id (MAX) веб-сессией не подделать


def test_rate_limiter_blocks_after_limit():
    limiter = security.RateLimiter(limit=3, window=60)
    assert [limiter.allow("ip") for _ in range(4)] == [True, True, True, False]
    assert limiter.blocked("ip")
    assert limiter.allow("other-ip")


def test_security_headers_embed_only_root():
    root = security.security_headers("/")
    admin = security.security_headers("/admin")
    assert "spapark86.ru" in root["Content-Security-Policy"]
    assert "spapark86.ru" not in admin["Content-Security-Policy"]
    assert "script-src 'self'" in admin["Content-Security-Policy"]
    assert root["X-Content-Type-Options"] == "nosniff"
