from hermes_harness.observability import sanitize


def test_harness_sanitizer_redacts_secrets_and_personal_data():
    result = sanitize(
        "contact=a@example.com token=abc123 password: hidden "
        "card=4111 1111 1111 1111 phone=+34 600 123 456 "
        "https://example.test/path?email=a@example.com&token=abc123"
    )
    assert "a@example.com" not in result
    assert "token=abc123" not in result
    assert "password: hidden" not in result
    assert "4111 1111 1111 1111" not in result
    assert "+34 600 123 456" not in result
    assert "?email=" not in result
    assert "[REDACTED]" in result
