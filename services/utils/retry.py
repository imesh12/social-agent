import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class RetryError(RuntimeError):
    """Raised when retry attempts are exhausted."""


def retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_multiplier: float = 3.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    delays: tuple[float, ...] | None = None,
    logger: logging.Logger | None = None,
    sleeper: Callable[[float], None] | None = None,
    async_sleeper: Callable[[float], Awaitable[None]] | None = None,
) -> Callable[[F], F]:
    """Retry a sync or async callable with exponential or explicit delays."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    retry_logger = logger or logging.getLogger(__name__)

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                started_at = time.perf_counter()
                last_exc: BaseException | None = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        delay = _delay_for_attempt(attempt, initial_delay, backoff_multiplier, delays)
                        retry_logger.warning(
                            "Retry attempt=%s/%s delay=%.3fs exception=%s elapsed=%.3fs",
                            attempt,
                            max_attempts,
                            delay,
                            exc,
                            time.perf_counter() - started_at,
                        )
                        if attempt >= max_attempts:
                            retry_logger.exception(
                                "Retry attempts exhausted attempts=%s elapsed=%.3fs",
                                max_attempts,
                                time.perf_counter() - started_at,
                            )
                            raise RetryError(f"Retry attempts exhausted for {func.__name__}") from exc
                        if async_sleeper is not None:
                            await async_sleeper(delay)
                        else:
                            await asyncio.sleep(delay)
                raise RetryError(f"Retry attempts exhausted for {func.__name__}") from last_exc

            return cast(F, async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            started_at = time.perf_counter()
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    delay = _delay_for_attempt(attempt, initial_delay, backoff_multiplier, delays)
                    retry_logger.warning(
                        "Retry attempt=%s/%s delay=%.3fs exception=%s elapsed=%.3fs",
                        attempt,
                        max_attempts,
                        delay,
                        exc,
                        time.perf_counter() - started_at,
                    )
                    if attempt >= max_attempts:
                        retry_logger.exception(
                            "Retry attempts exhausted attempts=%s elapsed=%.3fs",
                            max_attempts,
                            time.perf_counter() - started_at,
                        )
                        raise RetryError(f"Retry attempts exhausted for {func.__name__}") from exc
                    if sleeper is not None:
                        sleeper(delay)
                    else:
                        time.sleep(delay)
            raise RetryError(f"Retry attempts exhausted for {func.__name__}") from last_exc

        return cast(F, sync_wrapper)

    return decorator


def _delay_for_attempt(
    attempt: int,
    initial_delay: float,
    backoff_multiplier: float,
    delays: tuple[float, ...] | None,
) -> float:
    if delays:
        return delays[min(attempt - 1, len(delays) - 1)]
    return initial_delay * (backoff_multiplier ** (attempt - 1))
