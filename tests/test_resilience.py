"""Tests for resilience patterns including retry and circuit breaker.

This module tests the retry mechanism with exponential backoff and
the circuit breaker pattern implementation.
"""

import time
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub.resilience import CircuitBreaker
from devhub.resilience import CircuitBreakerPolicy
from devhub.resilience import CircuitBreakerState
from devhub.resilience import CircuitState
from devhub.resilience import RetryPolicy
from devhub.resilience import RetryState
from devhub.resilience import async_with_retry
from devhub.resilience import with_circuit_breaker
from devhub.resilience import with_retry


class TestRetryPolicy:
    """Test RetryPolicy configuration."""

    def test_retry_policy_defaults(self) -> None:
        """Test default retry policy configuration."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.exponential_base == 2.0
        assert policy.jitter is True

    def test_retry_policy_immutability(self) -> None:
        """Test that retry policy is immutable."""
        policy = RetryPolicy()
        with pytest.raises(AttributeError):
            policy.max_attempts = 5  # type: ignore[misc]

    def test_calculate_delay_exponential(self) -> None:
        """Test exponential backoff calculation without jitter."""
        policy = RetryPolicy(base_delay=1.0, exponential_base=2.0, jitter=False)

        assert policy.calculate_delay(0) == 0
        assert policy.calculate_delay(1) == 1.0
        assert policy.calculate_delay(2) == 2.0
        assert policy.calculate_delay(3) == 4.0
        assert policy.calculate_delay(4) == 8.0

    def test_calculate_delay_with_max(self) -> None:
        """Test that delay is capped at max_delay."""
        policy = RetryPolicy(
            base_delay=10.0,
            exponential_base=10.0,
            max_delay=50.0,
            jitter=False,
        )

        assert policy.calculate_delay(1) == 10.0
        assert policy.calculate_delay(2) == 50.0  # Would be 100 but capped
        assert policy.calculate_delay(3) == 50.0  # Would be 1000 but capped

    def test_calculate_delay_with_jitter(self) -> None:
        """Test that jitter adds randomness to delay."""
        policy = RetryPolicy(base_delay=10.0, jitter=True)

        delays = [policy.calculate_delay(2) for _ in range(10)]
        # With jitter, delays should vary
        assert len(set(delays)) > 1
        # But should be within expected range (20 + up to 25% jitter)
        assert all(20.0 <= d <= 25.0 for d in delays)

    def test_should_retry_exception_types(self) -> None:
        """Test exception type checking for retry."""
        policy = RetryPolicy(
            retryable_exceptions=(ConnectionError, TimeoutError),
        )

        assert policy.should_retry(ConnectionError("test"))
        assert policy.should_retry(TimeoutError("test"))
        assert not policy.should_retry(ValueError("test"))
        assert not policy.should_retry(KeyError("test"))


class TestRetryState:
    """Test RetryState tracking."""

    def test_retry_state_initial(self) -> None:
        """Test initial retry state."""
        state = RetryState()
        assert state.attempt == 0
        assert state.total_delay == 0.0
        assert state.last_exception is None

    def test_retry_state_immutability(self) -> None:
        """Test that retry state is immutable."""
        state = RetryState()
        with pytest.raises(AttributeError):
            state.attempt = 1  # type: ignore[misc]

    def test_next_attempt_updates(self) -> None:
        """Test creating new state for next attempt."""
        initial = RetryState()
        exception = ValueError("test error")

        next_state = initial.next_attempt(2.5, exception)

        assert next_state.attempt == 1
        assert next_state.total_delay == 2.5
        assert next_state.last_exception == exception
        # Original unchanged
        assert initial.attempt == 0
        assert initial.total_delay == 0.0


class TestWithRetry:
    """Test with_retry function."""

    def test_with_retry_success_first_attempt(self) -> None:
        """Test successful operation on first attempt."""
        operation = Mock(return_value=Success("result"))

        result = with_retry(operation, RetryPolicy(max_attempts=3))

        assert isinstance(result, Success)
        assert result.unwrap() == "result"
        assert operation.call_count == 1

    def test_with_retry_success_after_failures(self) -> None:
        """Test operation succeeds after initial failures."""
        operation = Mock(
            side_effect=[
                Failure("error 1"),
                Failure("error 2"),
                Success("result"),
            ]
        )

        with patch("time.sleep"):  # Speed up test
            result = with_retry(operation, RetryPolicy(max_attempts=3))

        assert isinstance(result, Success)
        assert result.unwrap() == "result"
        assert operation.call_count == 3

    def test_with_retry_max_attempts_exceeded(self) -> None:
        """Test failure when max attempts exceeded."""
        operation = Mock(return_value=Failure("persistent error"))

        with patch("time.sleep"):
            result = with_retry(operation, RetryPolicy(max_attempts=3))

        assert isinstance(result, Failure)
        assert "persistent error" in str(result)
        assert operation.call_count == 3

    def test_with_retry_non_retryable_exception(self) -> None:
        """Test non-retryable exception stops retry immediately."""
        operation = Mock(side_effect=ValueError("bad value"))

        policy = RetryPolicy(
            max_attempts=3,
            retryable_exceptions=(ConnectionError, TimeoutError),
        )

        result = with_retry(operation, policy)

        assert isinstance(result, Failure)
        assert "Non-retryable exception" in str(result)
        assert operation.call_count == 1

    def test_with_retry_retryable_exception(self) -> None:
        """Test retryable exception triggers retry."""
        operation = Mock(
            side_effect=[
                ConnectionError("network error"),
                ConnectionError("network error"),
                Success("result"),
            ]
        )

        with patch("time.sleep"):
            result = with_retry(operation, RetryPolicy(max_attempts=3))

        assert isinstance(result, Success)
        assert result.unwrap() == "result"
        assert operation.call_count == 3

    def test_with_retry_delays(self) -> None:
        """Test that delays are applied between retries."""
        operation = Mock(
            side_effect=[
                Failure("error"),
                Failure("error"),
                Success("result"),
            ]
        )

        with patch("time.sleep") as mock_sleep:
            result = with_retry(
                operation,
                RetryPolicy(
                    max_attempts=3,
                    base_delay=0.1,
                    jitter=False,
                ),
            )

        assert isinstance(result, Success)
        # Check delays: 0 for first attempt, 0.1 for second, 0.2 for third
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)


class TestAsyncWithRetry:
    """Test async_with_retry function."""

    @pytest.mark.asyncio
    async def test_async_with_retry_success(self) -> None:
        """Test async retry with successful operation."""

        async def operation() -> Result[str, str]:
            return Success("async result")

        result = await async_with_retry(operation, RetryPolicy(max_attempts=3))

        assert isinstance(result, Success)
        assert result.unwrap() == "async result"

    @pytest.mark.asyncio
    async def test_async_with_retry_after_failures(self) -> None:
        """Test async operation succeeds after failures."""
        attempt_count = 0

        async def operation() -> Result[str, str]:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                return Failure(f"error {attempt_count}")
            return Success("async result")

        with patch("asyncio.sleep"):
            result = await async_with_retry(
                operation,
                RetryPolicy(max_attempts=3),
            )

        assert isinstance(result, Success)
        assert result.unwrap() == "async result"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_async_with_retry_exception(self) -> None:
        """Test async retry with exceptions."""

        async def operation() -> Result[str, str]:
            msg = "async network error"
            raise ConnectionError(msg)

        with patch("asyncio.sleep"):
            result = await async_with_retry(
                operation,
                RetryPolicy(max_attempts=2),
            )

        assert isinstance(result, Failure)
        assert "Max retry attempts" in str(result)


class TestCircuitBreakerPolicy:
    """Test CircuitBreakerPolicy configuration."""

    def test_circuit_breaker_policy_defaults(self) -> None:
        """Test default circuit breaker policy."""
        policy = CircuitBreakerPolicy()
        assert policy.failure_threshold == 5
        assert policy.success_threshold == 2
        assert policy.timeout_seconds == 60.0

    def test_circuit_breaker_policy_immutability(self) -> None:
        """Test that circuit breaker policy is immutable."""
        policy = CircuitBreakerPolicy()
        with pytest.raises(AttributeError):
            policy.failure_threshold = 10  # type: ignore[misc]

    def test_is_expected_exception(self) -> None:
        """Test exception type checking."""
        policy = CircuitBreakerPolicy(
            expected_exception_types=(ConnectionError, TimeoutError),
        )

        assert policy.is_expected_exception(ConnectionError("test"))
        assert policy.is_expected_exception(TimeoutError("test"))
        assert not policy.is_expected_exception(ValueError("test"))


class TestCircuitBreakerState:
    """Test CircuitBreakerState transitions."""

    def test_circuit_breaker_state_initial(self) -> None:
        """Test initial circuit breaker state."""
        state = CircuitBreakerState()
        assert state.state == CircuitState.CLOSED
        assert state.failure_count == 0
        assert state.success_count == 0

    def test_circuit_breaker_state_immutability(self) -> None:
        """Test that circuit breaker state is immutable."""
        state = CircuitBreakerState()
        with pytest.raises(AttributeError):
            state.failure_count = 1  # type: ignore[misc]

    def test_with_success_in_half_open(self) -> None:
        """Test success tracking in half-open state."""
        initial = CircuitBreakerState(
            state=CircuitState.HALF_OPEN,
            failure_count=2,
        )

        after_success = initial.with_success()

        assert after_success.success_count == 1
        assert after_success.failure_count == 0
        assert initial.success_count == 0  # Original unchanged

    def test_with_failure_updates(self) -> None:
        """Test failure tracking."""
        initial = CircuitBreakerState()

        after_failure = initial.with_failure()

        assert after_failure.failure_count == 1
        assert after_failure.success_count == 0
        assert after_failure.last_failure_time > 0

    def test_transition_to_new_state(self) -> None:
        """Test state transitions."""
        initial = CircuitBreakerState(
            state=CircuitState.CLOSED,
            failure_count=5,
            success_count=2,
        )

        after_transition = initial.transition_to(CircuitState.OPEN)

        assert after_transition.state == CircuitState.OPEN
        assert after_transition.failure_count == 0
        assert after_transition.success_count == 0
        assert after_transition.last_state_change > initial.last_state_change

    def test_should_transition_to_half_open(self) -> None:
        """Test half-open transition logic."""
        # Not in open state - should not transition
        closed_state = CircuitBreakerState(state=CircuitState.CLOSED)
        assert not closed_state.should_transition_to_half_open(60.0)

        # In open state but not enough time passed
        recent_open = CircuitBreakerState(
            state=CircuitState.OPEN,
            last_failure_time=time.time() - 30,
        )
        assert not recent_open.should_transition_to_half_open(60.0)

        # In open state and enough time passed
        old_open = CircuitBreakerState(
            state=CircuitState.OPEN,
            last_failure_time=time.time() - 120,
        )
        assert old_open.should_transition_to_half_open(60.0)


class TestCircuitBreaker:
    """Test CircuitBreaker implementation."""

    def test_circuit_breaker_closed_success(self) -> None:
        """Test successful operation with closed circuit."""
        breaker = CircuitBreaker()
        operation = Mock(return_value=Success("result"))

        result = breaker.call(operation)

        assert isinstance(result, Success)
        assert result.unwrap() == "result"
        assert operation.call_count == 1

    def test_circuit_breaker_opens_on_failures(self) -> None:
        """Test circuit opens after threshold failures."""
        breaker = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=3))
        failing_op = Mock(return_value=Failure("error"))

        # First 3 failures open the circuit
        for _i in range(3):
            result = breaker.call(failing_op)
            assert isinstance(result, Failure)

        # Circuit should now be open
        state = breaker.get_state()
        assert state.state == CircuitState.OPEN

        # Further calls should be blocked
        result = breaker.call(failing_op)
        assert isinstance(result, Failure)
        assert "Circuit breaker is open" in str(result)
        # Operation not called when circuit is open
        assert failing_op.call_count == 3

    def test_circuit_breaker_half_open_recovery(self) -> None:
        """Test circuit recovery through half-open state."""
        breaker = CircuitBreaker(
            CircuitBreakerPolicy(
                failure_threshold=2,
                success_threshold=2,
                timeout_seconds=0.1,
            )
        )

        # Open the circuit
        failing_op = Mock(return_value=Failure("error"))
        for _ in range(2):
            breaker.call(failing_op)

        assert breaker.get_state().state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.2)

        # Circuit should transition to half-open and allow request
        success_op = Mock(return_value=Success("recovery"))
        result = breaker.call(success_op)
        assert isinstance(result, Success)
        assert breaker.get_state().state == CircuitState.HALF_OPEN

        # One more success should close circuit
        result = breaker.call(success_op)
        assert isinstance(result, Success)
        assert breaker.get_state().state == CircuitState.CLOSED

    def test_circuit_breaker_half_open_failure(self) -> None:
        """Test circuit reopens on failure in half-open state."""
        breaker = CircuitBreaker(
            CircuitBreakerPolicy(
                failure_threshold=2,
                timeout_seconds=0.1,
            )
        )

        # Open the circuit
        failing_op = Mock(return_value=Failure("error"))
        for _ in range(2):
            breaker.call(failing_op)

        # Wait for timeout
        time.sleep(0.2)

        # First call in half-open fails
        result = breaker.call(failing_op)
        assert isinstance(result, Failure)

        # Circuit should be open again
        assert breaker.get_state().state == CircuitState.OPEN

    def test_circuit_breaker_exception_handling(self) -> None:
        """Test circuit breaker handles exceptions."""
        breaker = CircuitBreaker(
            CircuitBreakerPolicy(
                failure_threshold=2,
                expected_exception_types=(ConnectionError,),
            )
        )

        def failing_op() -> Result[str, str]:
            msg = "network error"
            raise ConnectionError(msg)

        # First failure
        result = breaker.call(failing_op)
        assert isinstance(result, Failure)
        assert "network error" in str(result)

        # Second failure opens circuit
        result = breaker.call(failing_op)
        assert isinstance(result, Failure)
        assert breaker.get_state().state == CircuitState.OPEN

    def test_circuit_breaker_reset(self) -> None:
        """Test resetting circuit breaker."""
        breaker = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=1))

        # Open the circuit
        breaker.call(Mock(return_value=Failure("error")))
        assert breaker.get_state().state == CircuitState.OPEN

        # Reset circuit
        breaker.reset()
        assert breaker.get_state().state == CircuitState.CLOSED
        assert breaker.get_state().failure_count == 0

    def test_circuit_breaker_thread_safety(self) -> None:
        """Test circuit breaker thread safety."""
        from concurrent.futures import ThreadPoolExecutor

        breaker = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=10))

        def operation() -> Result[str, str]:
            import random

            if random.random() > 0.5:  # noqa: S311
                return Success("ok")
            return Failure("error")

        def run_operations() -> None:
            for _ in range(10):
                breaker.call(operation)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_operations) for _ in range(5)]
            for future in futures:
                future.result()

        # Circuit breaker should have handled concurrent access safely
        state = breaker.get_state()
        assert state.state in [CircuitState.CLOSED, CircuitState.OPEN]


class TestWithCircuitBreaker:
    """Test with_circuit_breaker convenience function."""

    def test_with_circuit_breaker_success(self) -> None:
        """Test successful operation through circuit breaker."""
        breaker = CircuitBreaker()
        operation = Mock(return_value=Success("result"))

        result = with_circuit_breaker(operation, breaker)

        assert isinstance(result, Success)
        assert result.unwrap() == "result"

    def test_with_circuit_breaker_blocked(self) -> None:
        """Test blocked operation when circuit is open."""
        breaker = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=1))

        # Open circuit
        breaker.call(Mock(return_value=Failure("error")))

        # Should be blocked
        result = with_circuit_breaker(
            Mock(return_value=Success("should not run")),
            breaker,
        )

        assert isinstance(result, Failure)
        assert "Circuit breaker is open" in str(result)
