"""Resilience patterns for DevHub including retry and circuit breaker.

This module provides functional implementations of resilience patterns
using immutable data structures and pure functions. All operations
follow functional programming principles with explicit error handling.

Classes:
    RetryPolicy: Immutable retry configuration
    RetryState: Immutable retry execution state
    CircuitBreakerPolicy: Immutable circuit breaker configuration
    CircuitBreakerState: Immutable circuit breaker state
    CircuitBreaker: Thread-safe circuit breaker implementation
"""

import asyncio
import secrets
import time
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from enum import Enum
from threading import Lock
from typing import TypeVar

from returns.result import Failure
from returns.result import Result
from returns.result import Success


T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker state enumeration."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Immutable retry policy configuration.

    Attributes:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to delays
        retryable_exceptions: Tuple of exceptions to retry on
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number with exponential backoff.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds for this attempt
        """
        if attempt <= 0:
            return 0

        delay = min(
            self.base_delay * (self.exponential_base ** (attempt - 1)),
            self.max_delay,
        )

        if self.jitter:
            # Add random jitter between 0 and 25% of delay
            jitter_amount = delay * 0.25 * (secrets.randbelow(1000) / 1000)
            delay += jitter_amount

        return delay

    def should_retry(self, exception: Exception) -> bool:
        """Check if exception is retryable according to policy.

        Args:
            exception: Exception that occurred

        Returns:
            True if should retry, False otherwise
        """
        return isinstance(exception, self.retryable_exceptions)


@dataclass(frozen=True, slots=True)
class RetryState:
    """Immutable state for retry execution.

    Attributes:
        attempt: Current attempt number (0-based)
        total_delay: Total delay accumulated so far
        last_exception: Last exception encountered
    """

    attempt: int = 0
    total_delay: float = 0.0
    last_exception: Exception | None = None

    def next_attempt(self, delay: float, exception: Exception | None = None) -> "RetryState":
        """Create new state for next retry attempt.

        Args:
            delay: Delay before this attempt
            exception: Exception from this attempt if failed

        Returns:
            New RetryState with updated values
        """
        return replace(
            self,
            attempt=self.attempt + 1,
            total_delay=self.total_delay + delay,
            last_exception=exception,
        )


def _handle_exception_retry(
    exception: Exception,
    attempt: int,
    policy: RetryPolicy,
    _state: RetryState,
) -> Result[None, str] | None:
    """Handle exception during retry - returns Result if terminal, None if should continue."""
    if not policy.should_retry(exception):
        return Failure(f"Non-retryable exception: {exception}")

    if attempt >= policy.max_attempts - 1:
        return Failure(f"Max retry attempts ({policy.max_attempts}) exceeded. Last error: {exception}")

    return None  # Continue retrying


def _handle_result_retry[T](
    result: Result[T, str],
    attempt: int,
    max_attempts: int,
) -> Result[T, str] | None:
    """Handle operation result - returns Result if terminal, None if should continue."""
    if isinstance(result, Success):
        return result

    # Operation returned Failure, check if we should retry
    if attempt < max_attempts - 1:
        return None  # Continue retrying

    return result  # Final failure


def with_retry[T](
    operation: Callable[[], Result[T, str]],
    policy: RetryPolicy | None = None,
) -> Result[T, str]:
    """Execute operation with retry logic using exponential backoff.

    Pure function that wraps an operation with retry logic. The operation
    itself should be a pure function returning a Result type.

    Args:
        operation: Function to execute that returns Result
        policy: Optional retry policy, uses defaults if None

    Returns:
        Success with operation result or Failure with error message

    Example:
        >>> def fetch_data() -> Result[str, str]:
        ...     # Simulated operation that might fail
        ...     return Success("data")
        >>> result = with_retry(fetch_data, RetryPolicy(max_attempts=3))
        >>> match result:
        ...     case Success(data):
        ...         print(f"Got: {data}")
        ...     case Failure(error):
        ...         print(f"Failed: {error}")
    """
    policy = policy or RetryPolicy()
    state = RetryState()

    for attempt in range(policy.max_attempts):
        if attempt > 0:
            delay = policy.calculate_delay(attempt)
            time.sleep(delay)
            state = state.next_attempt(delay)

        try:
            result = operation()
            handled_result = _handle_result_retry(result, attempt, policy.max_attempts)
            if handled_result is not None:
                return handled_result

        except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as e:
            state = state.next_attempt(0, e)

            exception_result = _handle_exception_retry(e, attempt, policy, state)
            if exception_result is not None:
                return exception_result  # type: ignore[return-value]

    return Failure(f"Retry failed after {state.attempt} attempts")


async def async_with_retry[T](
    operation: Callable[[], Awaitable[Result[T, str]]],
    policy: RetryPolicy | None = None,
) -> Result[T, str]:
    """Async version of with_retry for async operations.

    Args:
        operation: Async function to execute that returns Result
        policy: Optional retry policy, uses defaults if None

    Returns:
        Success with operation result or Failure with error message

    Example:
        >>> async def fetch_data_async() -> Result[str, str]:
        ...     # Simulated async operation
        ...     return Success("data")
        >>> result = await async_with_retry(fetch_data_async)
    """
    policy = policy or RetryPolicy()
    state = RetryState()

    for attempt in range(policy.max_attempts):
        if attempt > 0:
            delay = policy.calculate_delay(attempt)
            await asyncio.sleep(delay)
            state = state.next_attempt(delay)

        try:
            result = await operation()
            handled_result = _handle_result_retry(result, attempt, policy.max_attempts)
            if handled_result is not None:
                return handled_result

        except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as e:
            state = state.next_attempt(0, e)

            exception_result = _handle_exception_retry(e, attempt, policy, state)
            if exception_result is not None:
                return exception_result  # type: ignore[return-value]

    return Failure(f"Retry failed after {state.attempt} attempts")


@dataclass(frozen=True, slots=True)
class CircuitBreakerPolicy:
    """Immutable circuit breaker configuration.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        success_threshold: Number of successes in half-open before closing
        timeout_seconds: Time to wait before transitioning from open to half-open
        expected_exception_types: Exceptions that count as failures
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    expected_exception_types: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )

    def is_expected_exception(self, exception: Exception) -> bool:
        """Check if exception should trigger circuit breaker.

        Args:
            exception: Exception to check

        Returns:
            True if exception should count as circuit failure
        """
        return isinstance(exception, self.expected_exception_types)


@dataclass(frozen=True, slots=True)
class CircuitBreakerState:
    """Immutable circuit breaker state.

    Attributes:
        state: Current circuit state
        failure_count: Number of consecutive failures
        success_count: Number of consecutive successes (in half-open)
        last_failure_time: Timestamp of last failure
        last_state_change: Timestamp of last state transition
    """

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = field(default_factory=time.time)

    def with_success(self) -> "CircuitBreakerState":
        """Create new state after successful operation.

        Returns:
            New state with updated success count
        """
        if self.state == CircuitState.HALF_OPEN:
            return replace(
                self,
                success_count=self.success_count + 1,
                failure_count=0,
            )
        return replace(self, failure_count=0, success_count=0)

    def with_failure(self) -> "CircuitBreakerState":
        """Create new state after failed operation.

        Returns:
            New state with updated failure count
        """
        return replace(
            self,
            failure_count=self.failure_count + 1,
            success_count=0,
            last_failure_time=time.time(),
        )

    def transition_to(self, new_state: CircuitState) -> "CircuitBreakerState":
        """Create new state with state transition.

        Args:
            new_state: New circuit state to transition to

        Returns:
            New state with updated circuit state
        """
        return replace(
            self,
            state=new_state,
            failure_count=0,
            success_count=0,
            last_state_change=time.time(),
        )

    def should_transition_to_half_open(self, timeout_seconds: float) -> bool:
        """Check if circuit should transition from open to half-open.

        Args:
            timeout_seconds: Timeout period for open state

        Returns:
            True if should transition to half-open
        """
        if self.state != CircuitState.OPEN:
            return False
        return time.time() - self.last_failure_time >= timeout_seconds


class CircuitBreaker:
    """Thread-safe circuit breaker implementation.

    Protects operations from cascading failures by tracking failure rates
    and temporarily blocking operations when threshold is exceeded.

    Example:
        >>> breaker = CircuitBreaker(CircuitBreakerPolicy())
        >>> def risky_operation() -> Result[str, str]:
        ...     # Operation that might fail
        ...     return Success("data")
        >>> result = breaker.call(risky_operation)
    """

    def __init__(self, policy: CircuitBreakerPolicy | None = None) -> None:
        """Initialize circuit breaker with policy."""
        self._policy = policy or CircuitBreakerPolicy()
        self._state = CircuitBreakerState()
        self._lock = Lock()

    def call[T](
        self,
        operation: Callable[[], Result[T, str]],
    ) -> Result[T, str]:
        """Execute operation through circuit breaker.

        Args:
            operation: Function to execute that returns Result

        Returns:
            Success with operation result, Failure if circuit open or operation fails

        Example:
            >>> breaker = CircuitBreaker()
            >>> result = breaker.call(lambda: Success("data"))
        """
        with self._lock:
            # Check if we should transition to half-open
            if self._state.should_transition_to_half_open(self._policy.timeout_seconds):
                self._state = self._state.transition_to(CircuitState.HALF_OPEN)

            # Block if circuit is open
            if self._state.state == CircuitState.OPEN:
                return Failure("Circuit breaker is open")

            # Allow limited requests in half-open state
            if self._state.state == CircuitState.HALF_OPEN and self._state.failure_count > 0:
                self._state = self._state.transition_to(CircuitState.OPEN)
                return Failure("Circuit breaker reopened due to failure in half-open state")

        # Execute operation outside lock to prevent blocking
        try:
            result = operation()
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as e:
            with self._lock:
                if self._policy.is_expected_exception(e):
                    self._handle_failure()

            return Failure(f"Operation failed with exception: {e}")
        else:
            with self._lock:
                if isinstance(result, Success):
                    self._handle_success()
                else:
                    self._handle_failure()

            return result

    def _handle_success(self) -> None:
        """Handle successful operation (must be called under lock)."""
        self._state = self._state.with_success()

        # Check if we should close circuit from half-open
        if self._state.state == CircuitState.HALF_OPEN and self._state.success_count >= self._policy.success_threshold:
            self._state = self._state.transition_to(CircuitState.CLOSED)

    def _handle_failure(self) -> None:
        """Handle failed operation (must be called under lock)."""
        self._state = self._state.with_failure()

        # Check if we should open circuit
        if self._state.state == CircuitState.CLOSED and self._state.failure_count >= self._policy.failure_threshold:
            self._state = self._state.transition_to(CircuitState.OPEN)
        elif self._state.state == CircuitState.HALF_OPEN:
            # Single failure in half-open reopens circuit
            self._state = self._state.transition_to(CircuitState.OPEN)

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state.

        Returns:
            Immutable snapshot of current state
        """
        with self._lock:
            return self._state

    def reset(self) -> None:
        """Reset circuit breaker to initial closed state."""
        with self._lock:
            self._state = CircuitBreakerState()


def with_circuit_breaker[T](
    operation: Callable[[], Result[T, str]],
    breaker: CircuitBreaker,
) -> Result[T, str]:
    """Execute operation through circuit breaker.

    Convenience function for using circuit breaker in functional style.

    Args:
        operation: Function to execute that returns Result
        breaker: Circuit breaker instance to use

    Returns:
        Success with operation result or Failure with error

    Example:
        >>> breaker = CircuitBreaker()
        >>> result = with_circuit_breaker(lambda: Success("data"), breaker)
    """
    return breaker.call(operation)
