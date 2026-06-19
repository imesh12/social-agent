import pytest

from services.utils.retry import RetryError, retry


def test_retry_succeeds_after_temporary_failure() -> None:
    calls = 0
    delays: list[float] = []

    @retry(max_attempts=3, initial_delay=1, backoff_multiplier=3, sleeper=delays.append)
    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ValueError("temporary")
        return "ok"

    assert flaky() == "ok"
    assert calls == 2
    assert delays == [1]


def test_retry_raises_when_max_attempts_exceeded() -> None:
    calls = 0
    delays: list[float] = []

    @retry(max_attempts=3, initial_delay=1, backoff_multiplier=3, sleeper=delays.append)
    def always_fails() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("still down")

    with pytest.raises(RetryError):
        always_fails()

    assert calls == 3
    assert delays == [1, 3]


def test_retry_allows_caller_fallback_behavior() -> None:
    @retry(max_attempts=2, initial_delay=1, backoff_multiplier=3, sleeper=lambda delay: None)
    def unavailable() -> str:
        raise RuntimeError("service unavailable")

    def call_with_fallback() -> str:
        try:
            return unavailable()
        except RetryError:
            return "fallback"

    assert call_with_fallback() == "fallback"
