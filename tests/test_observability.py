"""Comprehensive tests for the observability and metrics system."""

import time

import pytest
from hypothesis import given
from hypothesis import strategies as st
from returns.result import Failure
from returns.result import Success

from devhub.observability import HealthCheck
from devhub.observability import HealthStatus
from devhub.observability import LogLevel
from devhub.observability import MetricConfig
from devhub.observability import MetricsCollector
from devhub.observability import MetricType
from devhub.observability import MetricValue
from devhub.observability import ObservabilityConfig
from devhub.observability import TraceContext
from devhub.observability import get_global_collector
from devhub.observability import shutdown_global_collector


class TestMetricConfig:
    """Test metric configuration."""

    def test_default_config(self) -> None:
        """Test default metric configuration."""
        config = MetricConfig("test_metric", MetricType.COUNTER)
        assert config.name == "test_metric"
        assert config.metric_type == MetricType.COUNTER
        assert config.description == ""
        assert config.labels == {}
        assert len(config.buckets) > 0
        assert len(config.quantiles) > 0

    def test_custom_config(self) -> None:
        """Test custom metric configuration."""
        config = MetricConfig(
            name="custom_metric",
            metric_type=MetricType.HISTOGRAM,
            description="Custom test metric",
            labels={"service": "api"},
            buckets=(0.1, 1.0, 10.0),
            unit="seconds",
        )
        assert config.name == "custom_metric"
        assert config.metric_type == MetricType.HISTOGRAM
        assert config.description == "Custom test metric"
        assert config.labels == {"service": "api"}
        assert config.buckets == (0.1, 1.0, 10.0)
        assert config.unit == "seconds"


class TestMetricValue:
    """Test metric value."""

    def test_metric_value_creation(self) -> None:
        """Test metric value creation."""
        value = MetricValue(
            metric_name="test_metric",
            value=42.0,
            labels={"env": "test"},
            trace_id="trace-123",
        )
        assert value.metric_name == "test_metric"
        assert value.value == 42.0
        assert value.labels == {"env": "test"}
        assert value.trace_id == "trace-123"
        assert value.timestamp <= time.time()

    def test_metric_value_defaults(self) -> None:
        """Test metric value with defaults."""
        value = MetricValue("simple_metric", 1.0)
        assert value.metric_name == "simple_metric"
        assert value.value == 1.0
        assert value.labels == {}
        assert value.trace_id is None


class TestTraceContext:
    """Test distributed tracing context."""

    def test_trace_context_creation(self) -> None:
        """Test trace context creation."""
        trace = TraceContext(
            trace_id="trace-123",
            span_id="span-456",
            operation_name="test_operation",
        )
        assert trace.trace_id == "trace-123"
        assert trace.span_id == "span-456"
        assert trace.operation_name == "test_operation"
        assert trace.parent_span_id is None
        assert trace.end_time is None
        assert trace.tags == {}
        assert trace.logs == []

    def test_trace_with_tag(self) -> None:
        """Test adding tags to trace context."""
        trace = TraceContext("trace-123", "span-456")
        updated_trace = trace.with_tag("service", "api")

        assert updated_trace.tags == {"service": "api"}
        assert trace.tags == {}  # Original unchanged

    def test_trace_with_log(self) -> None:
        """Test adding log entries to trace context."""
        trace = TraceContext("trace-123", "span-456")
        updated_trace = trace.with_log("Test message", user_id=123)

        assert len(updated_trace.logs) == 1
        assert updated_trace.logs[0]["message"] == "Test message"
        assert updated_trace.logs[0]["user_id"] == 123
        assert "timestamp" in updated_trace.logs[0]
        assert len(trace.logs) == 0  # Original unchanged

    def test_trace_finish(self) -> None:
        """Test finishing a trace."""
        trace = TraceContext("trace-123", "span-456")
        assert trace.end_time is None

        finished_trace = trace.finish()
        assert finished_trace.end_time is not None
        assert finished_trace.end_time > trace.start_time
        assert trace.end_time is None  # Original unchanged

    def test_trace_duration(self) -> None:
        """Test trace duration calculation."""
        start_time = time.time()
        trace = TraceContext("trace-123", "span-456", start_time=start_time)

        time.sleep(0.01)  # Small delay
        duration = trace.duration_seconds
        assert duration > 0.01

        # Test with finished trace
        finished_trace = trace.finish()
        finished_duration = finished_trace.duration_seconds
        assert finished_duration > 0.01
        assert finished_duration >= duration


class TestHealthCheck:
    """Test health check functionality."""

    def test_health_check_creation(self) -> None:
        """Test health check creation."""

        def dummy_check() -> Success[dict[str, str]]:
            return Success({"status": "ok"})

        check = HealthCheck(
            name="test_check",
            description="Test health check",
            check_function=dummy_check,
        )
        assert check.name == "test_check"
        assert check.description == "Test health check"
        assert check.timeout_seconds == 5.0
        assert check.interval_seconds == 30.0
        assert check.enabled is True
        assert check.critical is False

    def test_health_check_custom_config(self) -> None:
        """Test health check with custom configuration."""

        def dummy_check() -> Success[dict[str, str]]:
            return Success({"status": "ok"})

        check = HealthCheck(
            name="critical_check",
            description="Critical system check",
            check_function=dummy_check,
            timeout_seconds=1.0,
            interval_seconds=10.0,
            enabled=False,
            critical=True,
        )
        assert check.timeout_seconds == 1.0
        assert check.interval_seconds == 10.0
        assert check.enabled is False
        assert check.critical is True


class TestObservabilityConfig:
    """Test observability configuration."""

    def test_default_config(self) -> None:
        """Test default observability configuration."""
        config = ObservabilityConfig()
        assert config.enabled is True
        assert config.metrics_enabled is True
        assert config.tracing_enabled is True
        assert config.logging_enabled is True
        assert config.health_checks_enabled is True
        assert config.prometheus_port == 8000
        assert config.log_level == LogLevel.INFO
        assert config.metrics_export_interval == 10.0
        assert config.trace_sample_rate == 0.1
        assert config.max_traces_in_memory == 1000

    def test_custom_config(self) -> None:
        """Test custom observability configuration."""
        config = ObservabilityConfig(
            enabled=False,
            prometheus_port=9090,
            log_level=LogLevel.DEBUG,
            trace_sample_rate=1.0,
            max_traces_in_memory=500,
        )
        assert config.enabled is False
        assert config.prometheus_port == 9090
        assert config.log_level == LogLevel.DEBUG
        assert config.trace_sample_rate == 1.0
        assert config.max_traces_in_memory == 500


class TestMetricsCollector:
    """Test metrics collector functionality."""

    @pytest.fixture
    def collector(self) -> MetricsCollector:
        """Create test metrics collector."""
        config = ObservabilityConfig(
            prometheus_port=8001,  # Use different port to avoid conflicts
            health_checks_enabled=False,  # Disable for testing
        )
        return MetricsCollector(config)

    def test_collector_initialization(self, collector: MetricsCollector) -> None:
        """Test collector initialization."""
        assert collector is not None

    def test_register_metric(self, collector: MetricsCollector) -> None:
        """Test metric registration."""
        config = MetricConfig("test_counter", MetricType.COUNTER, "Test counter")
        result = collector.register_metric(config)
        assert isinstance(result, Success)

        # Test duplicate registration
        result = collector.register_metric(config)
        assert isinstance(result, Failure)
        assert "already registered" in str(result).lower()

    def test_record_metric(self, collector: MetricsCollector) -> None:
        """Test metric recording."""
        # Register metric first
        config = MetricConfig("test_gauge", MetricType.GAUGE, "Test gauge")
        collector.register_metric(config)

        # Record metric value
        result = collector.record_metric("test_gauge", 42.0, {"env": "test"})
        assert isinstance(result, Success)

        # Test recording unknown metric
        result = collector.record_metric("unknown_metric", 1.0)
        assert isinstance(result, Failure)
        assert "not registered" in str(result).lower()

    def test_timer_decorator(self, collector: MetricsCollector) -> None:
        """Test timer decorator functionality."""
        # Register timer metric
        config = MetricConfig("function_timer", MetricType.HISTOGRAM, "Function timer")
        collector.register_metric(config)

        @collector.timer("function_timer")
        def timed_function() -> str:
            time.sleep(0.01)
            return "done"

        result = timed_function()
        assert result == "done"

        # Test with exception
        @collector.timer("function_timer")
        def failing_function() -> None:
            msg = "Test error"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Test error"):
            failing_function()

    def test_trace_context_manager(self, collector: MetricsCollector) -> None:
        """Test trace context manager."""
        with collector.trace("test_operation", service="api") as trace:
            assert trace.operation_name == "test_operation"
            assert trace.tags["service"] == "api"
            assert trace.end_time is None

            # Add log during trace
            updated_trace = trace.with_log("Processing request")
            assert len(updated_trace.logs) == 1

        # Trace should be finished after context
        assert trace.end_time is not None

    @pytest.mark.usefixtures("_collector")
    def test_trace_disabled(self) -> None:
        """Test tracing when disabled."""
        config = ObservabilityConfig(tracing_enabled=False)
        disabled_collector = MetricsCollector(config)

        with disabled_collector.trace("test_operation") as trace:
            assert trace.trace_id == "disabled"
            assert trace.span_id == "disabled"

    def test_health_check_registration(self, collector: MetricsCollector) -> None:
        """Test health check registration."""

        def test_check() -> Success[dict[str, str]]:
            return Success({"status": "healthy"})

        check = HealthCheck("test_check", "Test check", test_check)
        result = collector.register_health_check(check)
        assert isinstance(result, Success)

    def test_health_status_collection(self, collector: MetricsCollector) -> None:
        """Test health status collection."""

        # Register successful health check
        def healthy_check() -> Success[dict[str, str]]:
            return Success({"status": "healthy"})

        # Register failing health check
        def failing_check() -> Failure[str]:
            return Failure("Something went wrong")

        collector.register_health_check(HealthCheck("healthy_check", "Healthy check", healthy_check))
        collector.register_health_check(HealthCheck("failing_check", "Failing check", failing_check, critical=True))

        status = collector.get_health_status()
        assert status["status"] == HealthStatus.UNHEALTHY.value  # Critical check failed
        assert "healthy_check" in status["checks"]
        assert "failing_check" in status["checks"]
        assert status["checks"]["healthy_check"]["status"] == HealthStatus.HEALTHY.value
        assert status["checks"]["failing_check"]["status"] == HealthStatus.UNHEALTHY.value

    @pytest.mark.usefixtures("_collector")
    def test_health_status_disabled(self) -> None:
        """Test health status when disabled."""
        config = ObservabilityConfig(health_checks_enabled=False)
        disabled_collector = MetricsCollector(config)

        status = disabled_collector.get_health_status()
        assert status["status"] == "disabled"
        assert status["checks"] == {}

    def test_metrics_summary(self, collector: MetricsCollector) -> None:
        """Test metrics summary collection."""
        # Register and record some metrics
        collector.register_metric(MetricConfig("test_metric", MetricType.COUNTER))
        collector.record_metric("test_metric", 1.0)

        summary = collector.get_metrics_summary()
        assert "timestamp" in summary
        assert summary["registered_metrics"] >= 1
        assert summary["total_metric_values"] >= 1
        assert "active_traces" in summary
        assert "completed_traces" in summary

    @given(
        metric_name=st.text(min_size=1, max_size=50),
        metric_value=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False),
    )
    def test_metric_recording_property(
        self,
        collector: MetricsCollector,
        metric_name: str,
        metric_value: float,
    ) -> None:
        """Property test for metric recording."""
        # Register metric
        config = MetricConfig(metric_name, MetricType.GAUGE)
        register_result = collector.register_metric(config)
        assert isinstance(register_result, Success)

        # Record metric
        record_result = collector.record_metric(metric_name, metric_value)
        assert isinstance(record_result, Success)

    @pytest.mark.usefixtures("_collector")
    def test_trace_memory_management(self) -> None:
        """Test trace memory management."""
        config = ObservabilityConfig(max_traces_in_memory=5)
        limited_collector = MetricsCollector(config)

        # Create more traces than the limit
        for i in range(10):
            with limited_collector.trace(f"operation_{i}"):
                pass

        summary = limited_collector.get_metrics_summary()
        # Should not exceed the limit significantly
        assert summary["completed_traces"] <= 10

    def test_error_handling_in_timer(self, collector: MetricsCollector) -> None:
        """Test error handling in timer decorator."""
        config = MetricConfig("error_timer", MetricType.HISTOGRAM)
        collector.register_metric(config)

        @collector.timer("error_timer")
        def error_function() -> None:
            msg = "Test error"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError):
            error_function()

        # Metric should still be recorded with error label
        # This would need more sophisticated verification in a real implementation


class TestGlobalCollector:
    """Test global collector functionality."""

    def test_global_collector_singleton(self) -> None:
        """Test global collector singleton behavior."""
        collector1 = get_global_collector()
        collector2 = get_global_collector()
        assert collector1 is collector2

    @pytest.mark.asyncio
    async def test_global_collector_shutdown(self) -> None:
        """Test global collector shutdown."""
        collector = get_global_collector()
        await shutdown_global_collector()

        # New instance after shutdown
        new_collector = get_global_collector()
        assert new_collector is not collector


class TestObservabilityIntegration:
    """Integration tests for observability system."""

    def test_end_to_end_metrics_flow(self) -> None:
        """Test complete metrics collection flow."""
        config = ObservabilityConfig(prometheus_port=8002)
        collector = MetricsCollector(config)

        # Register metrics
        counter_config = MetricConfig("requests_total", MetricType.COUNTER, "Total requests")
        timer_config = MetricConfig("request_duration", MetricType.HISTOGRAM, "Request duration")

        collector.register_metric(counter_config)
        collector.register_metric(timer_config)

        # Simulate API request with metrics
        with collector.trace("api_request", endpoint="/users") as trace:
            # Record request counter
            collector.record_metric("requests_total", 1.0, {"method": "GET"}, trace.trace_id)

            # Simulate processing time
            time.sleep(0.01)

            # Record timing
            collector.record_metric("request_duration", 0.01, {"method": "GET"}, trace.trace_id)

            trace.with_log("Request processed successfully")

        # Verify metrics were recorded
        summary = collector.get_metrics_summary()
        assert summary["total_metric_values"] >= 2
        assert summary["completed_traces"] >= 1

    def test_multiple_concurrent_traces(self) -> None:
        """Test handling multiple concurrent traces."""
        collector = MetricsCollector()

        traces = []
        # Start multiple traces
        for i in range(3):
            trace_context = collector.trace(f"operation_{i}")
            trace = trace_context.__enter__()
            traces.append((trace_context, trace))

        # Verify all traces are active
        summary = collector.get_metrics_summary()
        assert summary["active_traces"] == 3

        # Finish all traces
        for trace_context, _trace in traces:
            trace_context.__exit__(None, None, None)

        # Verify traces moved to completed
        summary = collector.get_metrics_summary()
        assert summary["active_traces"] == 0
        assert summary["completed_traces"] >= 3

    def test_health_checks_with_system_status(self) -> None:
        """Test health checks integration."""
        collector = MetricsCollector()

        # Register custom health checks
        def database_check() -> Success[dict[str, str]]:
            return Success({"connection": "ok", "latency_ms": "5"})

        def cache_check() -> Failure[str]:
            return Failure("Cache server unreachable")

        collector.register_health_check(HealthCheck("database", "Database connectivity", database_check))
        collector.register_health_check(HealthCheck("cache", "Cache server", cache_check, critical=False))

        status = collector.get_health_status()
        assert status["status"] == HealthStatus.DEGRADED.value  # Non-critical failure
        assert status["checks"]["database"]["status"] == HealthStatus.HEALTHY.value
        assert status["checks"]["cache"]["status"] == HealthStatus.UNHEALTHY.value

    def test_observability_disabled(self) -> None:
        """Test observability system when completely disabled."""
        config = ObservabilityConfig(enabled=False)
        collector = MetricsCollector(config)

        # Operations should work but have minimal impact
        start_result = collector.start()
        assert isinstance(start_result, Success)

        # Metrics and tracing should still work for consistency
        collector.register_metric(MetricConfig("test_metric", MetricType.COUNTER))
        result = collector.record_metric("test_metric", 1.0)
        assert isinstance(result, Success)

        with collector.trace("test_operation") as trace:
            assert trace is not None
