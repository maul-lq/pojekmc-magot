from backend.auth import LoginRateLimiter, hash_password, hash_session_token, verify_password


def test_password_hash_round_trip() -> None:
    encoded = hash_password("password-yang-kuat")

    assert encoded.startswith("scrypt$")
    assert verify_password("password-yang-kuat", encoded)
    assert not verify_password("password-salah", encoded)


def test_session_hash_uses_pepper() -> None:
    token = "session-token"

    assert hash_session_token(token, "pepper-a") != hash_session_token(token, "pepper-b")


def test_login_rate_limiter_blocks_after_five_failures() -> None:
    limiter = LoginRateLimiter()

    for _ in range(5):
        limiter.add_failure("ip:admin")

    assert limiter.is_blocked("ip:admin")
    limiter.clear("ip:admin")
    assert not limiter.is_blocked("ip:admin")
