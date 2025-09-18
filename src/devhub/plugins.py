"""Plugin architecture for DevHub extensibility.

This module provides a clean, type-safe plugin system that allows extending
DevHub with custom data sources, transformations, and output formatters.
All plugins follow functional programming principles with immutable data.

Classes:
    PluginMetadata: Immutable plugin metadata
    PluginCapability: Plugin capability enumeration
    PluginRegistry: Plugin discovery and management
    Plugin: Base plugin protocol
    DataSourcePlugin: Protocol for data source plugins
    TransformPlugin: Protocol for data transformation plugins
    OutputPlugin: Protocol for output formatting plugins
"""

import importlib.util
import inspect
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from pathlib import Path
from typing import Any
from typing import Protocol
from typing import TypeVar
from typing import runtime_checkable

from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub.main import BundleData
from devhub.sdk import ContextRequest


T = TypeVar("T")


class PluginCapability(Enum):
    """Plugin capability enumeration."""

    DATA_SOURCE = "data_source"
    TRANSFORM = "transform"
    OUTPUT = "output"
    VALIDATION = "validation"
    ENRICHMENT = "enrichment"


@dataclass(frozen=True, slots=True)
class PluginMetadata:
    """Immutable plugin metadata.

    Attributes:
        name: Unique plugin identifier
        version: Plugin version (semantic versioning)
        author: Plugin author name
        description: Human-readable description
        capabilities: Tuple of plugin capabilities
        dependencies: Required dependencies
        config_schema: Configuration schema (optional)
        supported_formats: Supported data formats
        priority: Plugin execution priority (lower = earlier)
    """

    name: str
    version: str
    author: str
    description: str
    capabilities: tuple[PluginCapability, ...]
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    config_schema: dict[str, Any] | None = None
    supported_formats: tuple[str, ...] = field(default_factory=tuple)
    priority: int = 100

    def supports_capability(self, capability: PluginCapability) -> bool:
        """Check if plugin supports given capability."""
        return capability in self.capabilities

    def is_compatible_with(self, required_version: str) -> bool:
        """Check if plugin version is compatible with required version."""
        # Simple version compatibility check (can be enhanced)
        try:
            plugin_parts = [int(x) for x in self.version.split(".")]
            required_parts = [int(x) for x in required_version.split(".")]

            # Major version must match exactly
            if plugin_parts[0] != required_parts[0]:
                return False

            # Minor version must be >= required
            if len(plugin_parts) > 1 and len(required_parts) > 1:
                return plugin_parts[1] >= required_parts[1]

        except (ValueError, IndexError):
            return False
        else:
            return True


@dataclass(frozen=True, slots=True)
class PluginConfig:
    """Immutable plugin configuration.

    Attributes:
        enabled: Whether plugin is enabled
        config: Plugin-specific configuration
        priority_override: Optional priority override
    """

    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    priority_override: int | None = None


@dataclass(frozen=True, slots=True)
class PluginResult[T]:
    """Immutable plugin execution result.

    Attributes:
        plugin_name: Name of plugin that produced result
        success: Whether execution was successful
        data: Result data (if successful)
        error: Error message (if failed)
        metadata: Additional metadata
        execution_time_ms: Execution time in milliseconds
    """

    plugin_name: str
    success: bool
    data: T | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0

    @classmethod
    def success_result(
        cls,
        plugin_name: str,
        data: T,
        execution_time: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> "PluginResult[T]":
        """Create successful plugin result."""
        return cls(
            plugin_name=plugin_name,
            success=True,
            data=data,
            execution_time_ms=execution_time,
            metadata=metadata or {},
        )

    @classmethod
    def failure_result(
        cls,
        plugin_name: str,
        error: str,
        execution_time: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> "PluginResult[T]":
        """Create failed plugin result."""
        return cls(
            plugin_name=plugin_name,
            success=False,
            error=error,
            execution_time_ms=execution_time,
            metadata=metadata or {},
        )


@runtime_checkable
class Plugin(Protocol):
    """Base plugin protocol.

    All plugins must implement this protocol to be registered
    and managed by the plugin system.
    """

    metadata: PluginMetadata

    async def initialize(self, config: PluginConfig) -> Result[None, str]:
        """Initialize plugin with configuration.

        Args:
            config: Plugin configuration

        Returns:
            Success if initialized, Failure with error message
        """
        ...

    async def shutdown(self) -> Result[None, str]:
        """Shutdown plugin and cleanup resources.

        Returns:
            Success if shutdown cleanly, Failure with error message
        """
        ...

    def validate_config(self, config: dict[str, Any]) -> Result[None, str]:
        """Validate plugin configuration.

        Args:
            config: Configuration to validate

        Returns:
            Success if valid, Failure with validation error
        """
        ...


@runtime_checkable
class DataSourcePlugin(Plugin, Protocol):
    """Protocol for data source plugins.

    Data source plugins can fetch data from external sources
    and integrate it into the DevHub bundle process.
    """

    async def fetch_data(
        self,
        request: ContextRequest,
        context: dict[str, Any],
    ) -> Result[dict[str, Any], str]:
        """Fetch data from external source.

        Args:
            request: Context request with parameters
            context: Current bundle context

        Returns:
            Success with fetched data, Failure with error
        """
        ...

    def get_supported_sources(self) -> tuple[str, ...]:
        """Get list of supported data sources.

        Returns:
            Tuple of supported source identifiers
        """
        ...


@runtime_checkable
class TransformPlugin(Plugin, Protocol):
    """Protocol for data transformation plugins.

    Transform plugins can modify or enrich bundle data
    as it flows through the processing pipeline.
    """

    async def transform_bundle(
        self,
        bundle: BundleData,
        config: dict[str, Any],
    ) -> Result[BundleData, str]:
        """Transform bundle data.

        Args:
            bundle: Original bundle data
            config: Transformation configuration

        Returns:
            Success with transformed bundle, Failure with error
        """
        ...

    def get_supported_transforms(self) -> tuple[str, ...]:
        """Get list of supported transformations.

        Returns:
            Tuple of supported transformation identifiers
        """
        ...


@runtime_checkable
class OutputPlugin(Plugin, Protocol):
    """Protocol for output formatting plugins.

    Output plugins can generate custom formats for bundle data
    beyond the default markdown and JSON outputs.
    """

    async def format_output(
        self,
        bundle: BundleData,
        format_options: dict[str, Any],
    ) -> Result[str | bytes, str]:
        """Format bundle data for output.

        Args:
            bundle: Bundle data to format
            format_options: Format-specific options

        Returns:
            Success with formatted output, Failure with error
        """
        ...

    def get_supported_formats(self) -> tuple[str, ...]:
        """Get list of supported output formats.

        Returns:
            Tuple of supported format identifiers
        """
        ...

    def get_file_extension(self, format_name: str) -> str:
        """Get file extension for format.

        Args:
            format_name: Name of the format

        Returns:
            File extension (including dot)
        """
        ...


class PluginRegistry:
    """Plugin discovery and management system.

    Provides centralized plugin registration, discovery, and execution
    with proper error handling and dependency management.

    Example:
        >>> registry = PluginRegistry()
        >>> await registry.discover_plugins("plugins/")
        >>> plugins = registry.get_plugins_by_capability(PluginCapability.DATA_SOURCE)
        >>> for plugin in plugins:
        ...     result = await plugin.fetch_data(request, context)
    """

    def __init__(self) -> None:
        """Initialize plugin registry."""
        self._plugins: dict[str, Plugin] = {}
        self._plugin_configs: dict[str, PluginConfig] = {}
        self._initialized_plugins: set[str] = set()

    def _validate_plugin_prerequisites(self, plugin: Plugin) -> Result[str, str]:
        """Validate plugin protocol and metadata."""
        if not hasattr(plugin, "metadata") or not hasattr(plugin, "initialize"):
            return Failure("Object does not implement Plugin protocol")

        plugin_name = plugin.metadata.name
        if not plugin_name:
            return Failure("Plugin name cannot be empty")
        if plugin_name in self._plugins:
            return Failure(f"Plugin '{plugin_name}' already registered")

        return Success(plugin_name)

    async def register_plugin(
        self,
        plugin: Plugin,
        config: PluginConfig | None = None,
    ) -> Result[None, str]:
        """Register a plugin instance.

        Args:
            plugin: Plugin instance to register
            config: Optional plugin configuration

        Returns:
            Success if registered, Failure with error
        """
        # Validate prerequisites
        name_result = self._validate_plugin_prerequisites(plugin)
        if isinstance(name_result, Failure):
            return name_result
        plugin_name = name_result.unwrap()

        # Validate configuration
        plugin_config = config or PluginConfig()
        if plugin_config.config:
            validation_result = plugin.validate_config(plugin_config.config)
            if isinstance(validation_result, Failure):
                return validation_result

        # Register plugin
        self._plugins[plugin_name] = plugin
        self._plugin_configs[plugin_name] = plugin_config
        return Success(None)

    async def discover_plugins(self, search_path: Path | str) -> Result[int, str]:
        """Discover and load plugins from directory.

        Args:
            search_path: Directory to search for plugins

        Returns:
            Success with number of plugins discovered, Failure with error
        """
        search_dir = Path(search_path)
        if not search_dir.exists() or not search_dir.is_dir():
            return Failure(f"Plugin directory not found: {search_path}")

        discovered_count = 0

        try:
            for plugin_file in search_dir.glob("*.py"):
                if plugin_file.name.startswith("_"):
                    continue  # Skip private modules

                result = await self._load_plugin_from_file(plugin_file)
                if isinstance(result, Success):
                    discovered_count += 1

            return Success(discovered_count)

        except (OSError, ImportError, ValueError) as e:
            return Failure(f"Plugin discovery failed: {e}")

    async def _load_plugin_from_file(self, plugin_file: Path) -> Result[Plugin, str]:
        """Load plugin from Python file.

        Args:
            plugin_file: Path to plugin file

        Returns:
            Success with plugin instance, Failure with error
        """
        try:
            # Load module dynamically
            spec = importlib.util.spec_from_file_location(
                plugin_file.stem,
                plugin_file,
            )
            if spec is None or spec.loader is None:
                return Failure(f"Could not load spec for {plugin_file}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find plugin classes in module
            for _name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and hasattr(obj, "metadata") and hasattr(obj, "initialize"):
                    # Instantiate plugin
                    plugin_instance = obj()
                    register_result = await self.register_plugin(plugin_instance)
                    if isinstance(register_result, Success):
                        return Success(plugin_instance)

            return Failure(f"No valid plugin class found in {plugin_file}")

        except (OSError, ImportError, ValueError, AttributeError) as e:
            return Failure(f"Failed to load plugin from {plugin_file}: {e}")

    async def initialize_plugins(self) -> Result[int, str]:
        """Initialize all registered plugins.

        Returns:
            Success with number of initialized plugins, Failure with error
        """
        initialized_count = 0
        failed_plugins = []

        for plugin_name, plugin in self._plugins.items():
            if plugin_name in self._initialized_plugins:
                continue

            config = self._plugin_configs.get(plugin_name, PluginConfig())
            if not config.enabled:
                continue

            try:
                init_result = await plugin.initialize(config)
                if isinstance(init_result, Success):
                    self._initialized_plugins.add(plugin_name)
                    initialized_count += 1
                else:
                    failed_plugins.append(f"{plugin_name}: {init_result}")
            except (RuntimeError, ValueError, TypeError) as e:
                failed_plugins.append(f"{plugin_name}: {e}")

        if failed_plugins:
            return Failure(f"Plugin initialization failures: {'; '.join(failed_plugins)}")

        return Success(initialized_count)

    async def shutdown_plugins(self) -> Result[None, str]:
        """Shutdown all initialized plugins.

        Returns:
            Success if all shut down cleanly, Failure with errors
        """
        shutdown_errors = []

        for plugin_name in list(self._initialized_plugins):
            plugin = self._plugins.get(plugin_name)
            if plugin:
                try:
                    shutdown_result = await plugin.shutdown()
                    if isinstance(shutdown_result, Failure):
                        shutdown_errors.append(f"{plugin_name}: {shutdown_result}")
                except (RuntimeError, ValueError) as e:
                    shutdown_errors.append(f"{plugin_name}: {e}")

            self._initialized_plugins.discard(plugin_name)

        if shutdown_errors:
            return Failure(f"Plugin shutdown errors: {'; '.join(shutdown_errors)}")

        return Success(None)

    def get_plugin(self, name: str) -> Plugin | None:
        """Get plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance if found, None otherwise
        """
        return self._plugins.get(name)

    def get_plugins_by_capability(
        self,
        capability: PluginCapability,
    ) -> tuple[Plugin, ...]:
        """Get plugins that support specific capability.

        Args:
            capability: Required capability

        Returns:
            Tuple of plugins supporting the capability, sorted by priority
        """
        matching_plugins = []

        for plugin_name, plugin in self._plugins.items():
            if plugin_name in self._initialized_plugins and plugin.metadata.supports_capability(capability):
                config = self._plugin_configs.get(plugin_name, PluginConfig())
                if config.enabled:
                    priority = config.priority_override or plugin.metadata.priority
                    matching_plugins.append((priority, plugin))

        # Sort by priority (lower = higher priority)
        matching_plugins.sort(key=lambda x: x[0])
        return tuple(plugin for _, plugin in matching_plugins)

    def list_plugins(self) -> tuple[PluginMetadata, ...]:
        """List all registered plugins.

        Returns:
            Tuple of plugin metadata
        """
        return tuple(plugin.metadata for plugin in self._plugins.values())

    async def execute_data_source_plugins(
        self,
        request: ContextRequest,
        context: dict[str, Any],
    ) -> AsyncIterator[PluginResult[dict[str, Any]]]:
        """Execute all data source plugins.

        Args:
            request: Context request
            context: Bundle context

        Yields:
            PluginResult for each executed plugin
        """
        plugins = self.get_plugins_by_capability(PluginCapability.DATA_SOURCE)

        for plugin in plugins:
            if not isinstance(plugin, DataSourcePlugin):
                continue

            start_time = time.time()

            try:
                result = await plugin.fetch_data(request, context)
                execution_time = (time.time() - start_time) * 1000

                if isinstance(result, Success):
                    yield PluginResult.success_result(
                        plugin.metadata.name,
                        result.unwrap(),
                        execution_time,
                    )
                else:
                    yield PluginResult.failure_result(
                        plugin.metadata.name,
                        str(result),
                        execution_time,
                    )

            except (RuntimeError, ValueError, TypeError) as e:
                execution_time = (time.time() - start_time) * 1000
                yield PluginResult.failure_result(
                    plugin.metadata.name,
                    f"Plugin execution error: {e}",
                    execution_time,
                )

    async def execute_transform_plugins(
        self,
        bundle: BundleData,
        config: dict[str, Any] | None = None,
    ) -> Result[BundleData, str]:
        """Execute transform plugins in sequence.

        Args:
            bundle: Original bundle data
            config: Optional transformation configuration

        Returns:
            Success with transformed bundle, Failure with error
        """
        current_bundle = bundle
        transform_config = config or {}
        plugins = self.get_plugins_by_capability(PluginCapability.TRANSFORM)

        for plugin in plugins:
            if not isinstance(plugin, TransformPlugin):
                continue

            try:
                result = await plugin.transform_bundle(current_bundle, transform_config)
                if isinstance(result, Success):
                    current_bundle = result.unwrap()
                else:
                    return Failure(f"Transform plugin '{plugin.metadata.name}' failed: {result}")
            except (RuntimeError, ValueError, TypeError) as e:
                return Failure(f"Transform plugin '{plugin.metadata.name}' error: {e}")

        return Success(current_bundle)


# Global plugin registry instance
_global_registry: PluginRegistry | None = None


def get_global_registry() -> PluginRegistry:
    """Get the global plugin registry instance.

    Returns:
        Global PluginRegistry instance
    """
    if _global_registry is None:
        globals()["_global_registry"] = PluginRegistry()
    return _global_registry


async def shutdown_global_registry() -> None:
    """Shutdown the global plugin registry."""
    # Use module-level access instead of global statement
    if _global_registry:
        await _global_registry.shutdown_plugins()
        globals()["_global_registry"] = None
