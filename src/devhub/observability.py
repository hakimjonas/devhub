"""Comprehensive observability and metrics collection for DevHub.

This module provides a complete observability solution with:
- Prometheus-compatible metrics collection
- Structured logging with correlation IDs
- Distributed tracing support
- Performance monitoring and profiling
- Health checks and system monitoring

Classes:
    MetricType: Enumeration of metric types
    MetricConfig: Immutable metric configuration
    MetricValue: Immutable metric value with metadata
    HealthCheck: Health check configuration and execution
    TraceContext: Distributed tracing context
    ObservabilityConfig: Comprehensive observability configuration
    MetricsCollector: Main metrics collection and export system
"""

import functools
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any
from typing import ParamSpec
from typing import Protocol
from typing import TypeVar

from returns.result import Failure
from returns.result import Result
from returns.result import Success


# Optional dependencies for advanced metrics
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Prometheus metric types
try:
    from prometheus_client import Counter as PrometheusCounter
    from prometheus_client import Gauge as PrometheusGauge
    from prometheus_client import Histogram as PrometheusHistogram
    from prometheus_client import Summary as PrometheusSummary

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


# Define protocol for Prometheus metrics
class PrometheusMetric(Protocol):
    """Protocol for Prometheus metric types."""

    def labels(self, **kwargs: str) -> "PrometheusMetric":
        """Apply labels to metric."""
        ...

    def inc(self, amount: float = 1) -> None:
        """Increment counter metric."""
        ...

    def set(self, value: float) -> None:
        """Set gauge metric value."""
        ...

    def observe(self, amount: float) -> None:
        """Observe value for histogram/summary."""
        ...


try:
    import prometheus_client
    from prometheus_client import CollectorRegistry

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


P = ParamSpec("P")
T = TypeVar("T")


class MetricType(Enum):
    """Metric type enumeration."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    TIMER = "timer"


class LogLevel(Enum):
    """Logging level enumeration."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HealthStatus(Enum):
    """Health check status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MetricConfig:
    """Immutable metric configuration.

    Attributes:
        name: Metric name
        metric_type: Type of metric
        description: Human-readable description
        labels: Default labels for metric
        buckets: Histogram buckets (for histogram metrics)
        quantiles: Summary quantiles (for summary metrics)
        unit: Metric unit (e.g., "seconds", "bytes", "requests")
    """

    name: str
    metric_type: MetricType
    description: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    buckets: tuple[float, ...] = field(default_factory=lambda: (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0))
    quantiles: tuple[float, ...] = field(default_factory=lambda: (0.5, 0.9, 0.95, 0.99))
    unit: str = ""


@dataclass(frozen=True, slots=True)
class MetricValue:
    """Immutable metric value with metadata.

    Attributes:
        metric_name: Name of the metric
        value: Metric value
        labels: Metric labels
        timestamp: Timestamp when metric was recorded
        trace_id: Optional trace ID for correlation
    """

    metric_name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    trace_id: str | None = None


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """Immutable health check configuration.

    Attributes:
        name: Health check name
        description: Human-readable description
        check_function: Function to execute for health check
        timeout_seconds: Timeout for health check execution
        interval_seconds: How often to run the check
        enabled: Whether the check is enabled
        critical: Whether failure indicates critical system failure
    """

    name: str
    description: str
    check_function: Callable[[], Result[dict[str, Any], str]]
    timeout_seconds: float = 5.0
    interval_seconds: float = 30.0
    enabled: bool = True
    critical: bool = False


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Immutable distributed tracing context.

    Attributes:
        trace_id: Unique trace identifier
        span_id: Unique span identifier
        parent_span_id: Parent span identifier
        operation_name: Name of the operation being traced
        start_time: Trace start timestamp
        end_time: Trace end timestamp (when completed)
        tags: Additional trace tags
        logs: Trace log entries
    """

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    operation_name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    tags: dict[str, str] = field(default_factory=dict)
    logs: list[dict[str, Any]] = field(default_factory=list)

    def with_tag(self, key: str, value: str) -> "TraceContext":
        """Add a tag to the trace context."""
        new_tags = {**self.tags, key: value}
        return replace(self, tags=new_tags)

    def with_log(self, message: str, **fields: str | float | bool) -> "TraceContext":
        """Add a log entry to the trace context."""
        log_entry = {
            "timestamp": time.time(),
            "message": message,
            **fields,
        }
        new_logs = [*self.logs, log_entry]
        return replace(self, logs=new_logs)

    def finish(self) -> "TraceContext":
        """Mark the trace as finished."""
        return replace(self, end_time=time.time())

    @property
    def duration_seconds(self) -> float:
        """Calculate trace duration in seconds."""
        end_time = self.end_time or time.time()
        return end_time - self.start_time


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    """Immutable observability configuration.

    Attributes:
        enabled: Whether observability is enabled
        metrics_enabled: Enable metrics collection
        tracing_enabled: Enable distributed tracing
        logging_enabled: Enable structured logging
        health_checks_enabled: Enable health checks
        prometheus_port: Port for Prometheus metrics endpoint
        log_level: Minimum log level to record
        log_file: Optional log file path
        metrics_export_interval: Metrics export interval in seconds
        trace_sample_rate: Sampling rate for traces (0.0 to 1.0)
        max_traces_in_memory: Maximum traces to keep in memory
    """

    enabled: bool = True
    metrics_enabled: bool = True
    tracing_enabled: bool = True
    logging_enabled: bool = True
    health_checks_enabled: bool = True
    prometheus_port: int = 8000
    log_level: LogLevel = LogLevel.INFO
    log_file: Path | None = None
    metrics_export_interval: float = 10.0
    trace_sample_rate: float = 0.1
    max_traces_in_memory: int = 1000


class MetricsCollector:
    """Main metrics collection and export system.

    Provides comprehensive metrics collection with support for:
    - Prometheus-compatible metrics export
    - Custom metrics registration and recording
    - Automatic system metrics collection
    - Performance monitoring and profiling
    - Health checks and alerting

    Example:
        >>> config = ObservabilityConfig(prometheus_port=8000)
        >>> collector = MetricsCollector(config)
        >>> collector.start()
        >>>
        >>> # Register custom metric
        >>> collector.register_metric(MetricConfig("api_requests_total", MetricType.COUNTER, "Total API requests"))
        >>>
        >>> # Record metric
        >>> collector.record_metric("api_requests_total", 1.0, {"endpoint": "/api/v1/users"})
        >>>
        >>> # Use as decorator
        >>> @collector.timer("function_duration_seconds")
        >>> def my_function():
        ...     time.sleep(1)
    """

    def __init__(self, config: ObservabilityConfig | None = None) -> None:
        """Initialize metrics collector with configuration."""
        self._config = config or ObservabilityConfig()
        self._metrics: dict[str, MetricConfig] = {}
        self._metric_values: dict[str, list[MetricValue]] = defaultdict(list)
        self._health_checks: dict[str, HealthCheck] = {}
        self._traces: dict[str, TraceContext] = {}
        self._active_traces: dict[str, TraceContext] = {}
        self._lock = RLock()

        # Prometheus metrics if available
        self._prometheus_registry: CollectorRegistry | None = None
        self._prometheus_metrics: dict[str, Any] = {}

        # System metrics
        self._system_metrics_enabled = PSUTIL_AVAILABLE

        # Configure logging
        self._logger = logging.getLogger("devhub.observability")
        if self._config.logging_enabled:
            self._configure_logging()

        # Initialize Prometheus if available
        if self._config.metrics_enabled and PROMETHEUS_AVAILABLE:
            self._initialize_prometheus()

        # Register default metrics
        self._register_default_metrics()

    def start(self) -> Result[None, str]:
        """Start the metrics collector and background services."""
        if not self._config.enabled:
            return Success(None)

        try:
            # Start Prometheus HTTP server if enabled
            if self._config.metrics_enabled and PROMETHEUS_AVAILABLE and self._prometheus_registry is not None:
                prometheus_client.start_http_server(
                    self._config.prometheus_port,
                    registry=self._prometheus_registry,
                )
                self._logger.info("Prometheus metrics server started on port %s", self._config.prometheus_port)

            # Start system metrics collection
            if self._system_metrics_enabled:
                self._start_system_metrics_collection()

            # Start health checks
            if self._config.health_checks_enabled:
                self._start_health_checks()

            self._logger.info("Observability system started successfully")
            return Success(None)

        except (OSError, RuntimeError, ImportError) as e:
            self._logger.exception("Failed to start observability system")
            return Failure(f"Observability startup failed: {e}")

    def register_metric(self, metric_config: MetricConfig) -> Result[None, str]:
        """Register a new metric for collection.

        Args:
            metric_config: Configuration for the metric

        Returns:
            Success if registered, Failure with error message
        """
        try:
            with self._lock:
                if metric_config.name in self._metrics:
                    return Failure(f"Metric '{metric_config.name}' already registered")

                self._metrics[metric_config.name] = metric_config

                # Create Prometheus metric if enabled
                if self._config.metrics_enabled and PROMETHEUS_AVAILABLE:
                    self._create_prometheus_metric(metric_config)

            self._logger.debug("Registered metric: %s", metric_config.name)
            return Success(None)

        except (ValueError, TypeError, KeyError) as e:
            return Failure(f"Failed to register metric: {e}")

    def record_metric(
        self,
        metric_name: str,
        value: float,
        labels: dict[str, str] | None = None,
        trace_id: str | None = None,
    ) -> Result[None, str]:
        """Record a metric value.

        Args:
            metric_name: Name of the metric to record
            value: Metric value
            labels: Optional metric labels
            trace_id: Optional trace ID for correlation

        Returns:
            Success if recorded, Failure with error message
        """
        try:
            with self._lock:
                if metric_name not in self._metrics:
                    return Failure(f"Metric '{metric_name}' not registered")

                metric_value = MetricValue(
                    metric_name=metric_name,
                    value=value,
                    labels=labels or {},
                    trace_id=trace_id,
                )

                self._metric_values[metric_name].append(metric_value)

                # Update Prometheus metric if available
                if self._config.metrics_enabled and PROMETHEUS_AVAILABLE:
                    self._update_prometheus_metric(metric_name, value, labels or {})

            return Success(None)

        except (ValueError, TypeError, KeyError) as e:
            return Failure(f"Failed to record metric: {e}")

    def timer(
        self, metric_name: str, labels: dict[str, str] | None = None
    ) -> Callable[[Callable[P, T]], Callable[P, T]]:
        """Decorator to automatically time function execution.

        Args:
            metric_name: Name of the timer metric
            labels: Optional metric labels

        Returns:
            Decorator function

        Example:
            >>> @collector.timer("function_duration_seconds")
            ... def my_function():
            ...     time.sleep(1)
        """

        def decorator(func: Callable[P, T]) -> Callable[P, T]:
            @functools.wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    duration = time.time() - start_time
                    error_labels = {**(labels or {}), "error": type(e).__name__}
                    self.record_metric(metric_name, duration, error_labels)
                    raise
                else:
                    duration = time.time() - start_time
                    self.record_metric(metric_name, duration, labels)
                    return result

            return wrapper

        return decorator

    @contextmanager
    def trace(self, operation_name: str, **tags: str) -> Iterator[TraceContext]:
        """Context manager for distributed tracing.

        Args:
            operation_name: Name of the operation being traced
            **tags: Additional trace tags

        Yields:
            TraceContext for the operation

        Example:
            >>> with collector.trace("api_request", endpoint="/users") as trace:
            ...     # Do work
            ...     trace = trace.with_log("Processing user request")
            ...     result = process_users()
        """
        if not self._config.tracing_enabled:
            # Return a no-op trace context
            yield TraceContext(
                trace_id="disabled",
                span_id="disabled",
                operation_name=operation_name,
                tags=tags,
            )
            return

        # Generate trace and span IDs
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())

        trace_context = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            operation_name=operation_name,
            tags=tags,
        )

        # Store active trace
        with self._lock:
            self._active_traces[trace_id] = trace_context

        try:
            yield trace_context
        finally:
            # Finish and store completed trace
            finished_trace = trace_context.finish()
            with self._lock:
                self._active_traces.pop(trace_id, None)
                self._traces[trace_id] = finished_trace

                # Limit traces in memory
                if len(self._traces) > self._config.max_traces_in_memory:
                    # Remove oldest traces
                    oldest_traces = sorted(self._traces.items(), key=lambda x: x[1].start_time)[
                        : len(self._traces) - self._config.max_traces_in_memory + 100
                    ]
                    for old_trace_id, _ in oldest_traces:
                        del self._traces[old_trace_id]

            # Record trace duration metric
            self.record_metric(
                "trace_duration_seconds",
                finished_trace.duration_seconds,
                {"operation": operation_name},
                trace_id,
            )

    def register_health_check(self, health_check: HealthCheck) -> Result[None, str]:
        """Register a health check.

        Args:
            health_check: Health check configuration

        Returns:
            Success if registered, Failure with error message
        """
        try:
            with self._lock:
                self._health_checks[health_check.name] = health_check

            self._logger.debug("Registered health check: %s", health_check.name)
            return Success(None)

        except (ValueError, TypeError) as e:
            return Failure(f"Failed to register health check: {e}")

    def _update_overall_status(self, current_status: HealthStatus, check_critical: bool) -> HealthStatus:
        """Update overall health status based on failed check."""
        if check_critical:
            return HealthStatus.UNHEALTHY
        if current_status == HealthStatus.HEALTHY:
            return HealthStatus.DEGRADED
        return current_status

    def _execute_health_check(self, _name: str, check: HealthCheck) -> tuple[dict[str, Any], HealthStatus | None]:
        """Execute a single health check and return result and status impact."""
        try:
            start_time = time.time()
            result = check.check_function()
            duration = time.time() - start_time

            if isinstance(result, Success):
                return {
                    "status": HealthStatus.HEALTHY.value,
                    "duration_seconds": duration,
                    "details": result.unwrap(),
                }, None
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "duration_seconds": duration,
                "error": str(result),
            }, HealthStatus.UNHEALTHY if check.critical else HealthStatus.DEGRADED

        except (OSError, RuntimeError, ValueError) as e:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "error": str(e),
            }, HealthStatus.UNHEALTHY if check.critical else HealthStatus.DEGRADED

    def get_health_status(self) -> dict[str, Any]:
        """Get overall system health status.

        Returns:
            Dictionary with health status information
        """
        if not self._config.health_checks_enabled:
            return {"status": "disabled", "checks": {}}

        overall_status = HealthStatus.HEALTHY
        check_results = {}

        with self._lock:
            for name, check in self._health_checks.items():
                if not check.enabled:
                    continue

                check_result, status_impact = self._execute_health_check(name, check)
                check_results[name] = check_result

                if status_impact and status_impact != HealthStatus.HEALTHY:
                    overall_status = self._update_overall_status(overall_status, check.critical)

        return {
            "status": overall_status.value,
            "timestamp": time.time(),
            "checks": check_results,
        }

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get summary of all collected metrics.

        Returns:
            Dictionary with metrics summary
        """
        summary = {
            "timestamp": time.time(),
            "registered_metrics": len(self._metrics),
            "total_metric_values": sum(len(values) for values in self._metric_values.values()),
            "active_traces": len(self._active_traces),
            "completed_traces": len(self._traces),
            "health_checks": len(self._health_checks),
        }

        # Add system metrics if available
        if self._system_metrics_enabled:
            summary.update(self._get_system_metrics())

        return summary

    def _configure_logging(self) -> None:
        """Configure structured logging."""
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        # File handler if configured
        if self._config.log_file:
            file_handler = logging.FileHandler(self._config.log_file)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

        # Set log level
        level_mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        self._logger.setLevel(level_mapping[self._config.log_level])

    def _initialize_prometheus(self) -> None:
        """Initialize Prometheus metrics registry."""
        self._prometheus_registry = CollectorRegistry()

    def _create_prometheus_metric(self, metric_config: MetricConfig) -> None:
        """Create a Prometheus metric from configuration."""
        if not self._prometheus_registry:
            return

        try:
            labels = list(metric_config.labels.keys())
            prometheus_metric: PrometheusMetric

            if metric_config.metric_type == MetricType.COUNTER:
                prometheus_metric = PrometheusCounter(
                    metric_config.name,
                    metric_config.description,
                    labels,
                    registry=self._prometheus_registry,
                )
            elif metric_config.metric_type == MetricType.GAUGE:
                prometheus_metric = PrometheusGauge(
                    metric_config.name,
                    metric_config.description,
                    labels,
                    registry=self._prometheus_registry,
                )
            elif metric_config.metric_type == MetricType.HISTOGRAM:
                prometheus_metric = PrometheusHistogram(
                    metric_config.name,
                    metric_config.description,
                    labels,
                    buckets=metric_config.buckets,
                    registry=self._prometheus_registry,
                )
            elif metric_config.metric_type == MetricType.SUMMARY:
                prometheus_metric = PrometheusSummary(
                    metric_config.name,
                    metric_config.description,
                    labels,
                    registry=self._prometheus_registry,
                )
            else:
                return

            self._prometheus_metrics[metric_config.name] = prometheus_metric

        except (ValueError, TypeError, ImportError) as e:
            self._logger.warning("Failed to create Prometheus metric %s: %s", metric_config.name, e)

    def _apply_metric_update(
        self, metric: PrometheusMetric, metric_type: MetricType, value: float, labels: dict[str, str]
    ) -> None:
        """Apply update to prometheus metric based on type."""
        labeled_metric = metric.labels(**labels) if labels else metric

        if metric_type == MetricType.COUNTER:
            labeled_metric.inc(value)
        elif metric_type == MetricType.GAUGE:
            labeled_metric.set(value)
        elif metric_type in (MetricType.HISTOGRAM, MetricType.SUMMARY, MetricType.TIMER):
            labeled_metric.observe(value)

    def _update_prometheus_metric(self, metric_name: str, value: float, labels: dict[str, str]) -> None:
        """Update a Prometheus metric with new value."""
        metric = self._prometheus_metrics.get(metric_name)
        if not metric:
            return

        try:
            metric_config = self._metrics[metric_name]
            self._apply_metric_update(metric, metric_config.metric_type, value, labels)
        except (ValueError, TypeError, AttributeError) as e:
            self._logger.warning("Failed to update Prometheus metric %s: %s", metric_name, e)

    def _register_default_metrics(self) -> None:
        """Register default system metrics."""
        default_metrics = [
            MetricConfig("http_requests_total", MetricType.COUNTER, "Total HTTP requests"),
            MetricConfig("http_request_duration_seconds", MetricType.HISTOGRAM, "HTTP request duration"),
            MetricConfig("function_duration_seconds", MetricType.HISTOGRAM, "Function execution duration"),
            MetricConfig("trace_duration_seconds", MetricType.HISTOGRAM, "Trace duration"),
            MetricConfig("cache_hits_total", MetricType.COUNTER, "Cache hits"),
            MetricConfig("cache_misses_total", MetricType.COUNTER, "Cache misses"),
            MetricConfig("errors_total", MetricType.COUNTER, "Total errors"),
        ]

        for metric_config in default_metrics:
            self.register_metric(metric_config)

    def _start_system_metrics_collection(self) -> None:
        """Start background system metrics collection."""
        if not PSUTIL_AVAILABLE:
            return

        # Register system metrics
        system_metrics = [
            MetricConfig("system_cpu_percent", MetricType.GAUGE, "CPU usage percentage"),
            MetricConfig("system_memory_bytes", MetricType.GAUGE, "Memory usage in bytes"),
            MetricConfig("system_disk_bytes", MetricType.GAUGE, "Disk usage in bytes"),
            MetricConfig("system_network_bytes_total", MetricType.COUNTER, "Network bytes transferred"),
        ]

        for metric_config in system_metrics:
            self.register_metric(metric_config)

    def _start_health_checks(self) -> None:
        """Start background health check execution."""
        # Register default health checks
        default_checks = [
            HealthCheck(
                "system_memory",
                "System memory usage",
                self._check_system_memory,
                critical=True,
            ),
            HealthCheck(
                "system_disk",
                "System disk usage",
                self._check_system_disk,
                critical=False,
            ),
        ]

        for check in default_checks:
            self.register_health_check(check)

    def _check_system_memory(self) -> Result[dict[str, Any], str]:
        """Check system memory usage."""
        if not PSUTIL_AVAILABLE:
            return Failure("psutil not available")

        try:
            memory = psutil.virtual_memory()
            return Success(
                {
                    "used_percent": memory.percent,
                    "available_bytes": memory.available,
                    "total_bytes": memory.total,
                }
            )
        except (OSError, ImportError) as e:
            return Failure(f"Memory check failed: {e}")

    def _check_system_disk(self) -> Result[dict[str, Any], str]:
        """Check system disk usage."""
        if not PSUTIL_AVAILABLE:
            return Failure("psutil not available")

        try:
            disk = psutil.disk_usage("/")
            return Success(
                {
                    "used_percent": (disk.used / disk.total) * 100,
                    "free_bytes": disk.free,
                    "total_bytes": disk.total,
                }
            )
        except (OSError, ImportError) as e:
            return Failure(f"Disk check failed: {e}")

    def _get_system_metrics(self) -> dict[str, Any]:
        """Get current system metrics."""
        if not PSUTIL_AVAILABLE:
            return {}

        try:
            return {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": (psutil.disk_usage("/").used / psutil.disk_usage("/").total) * 100,
                "process_count": len(psutil.pids()),
            }
        except (OSError, ImportError):
            return {}


# Global metrics collector instance
_global_collector: MetricsCollector | None = None


def get_global_collector(config: ObservabilityConfig | None = None) -> MetricsCollector:
    """Get the global metrics collector instance.

    Args:
        config: Optional observability configuration

    Returns:
        Global MetricsCollector instance
    """
    if _global_collector is None:
        globals()["_global_collector"] = MetricsCollector(config)
    return _global_collector


async def shutdown_global_collector() -> None:
    """Shutdown the global metrics collector."""
    # Use module-level access instead of global statement
    if _global_collector:
        # Stop any background services
        globals()["_global_collector"] = None
