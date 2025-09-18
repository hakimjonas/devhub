"""Tests for the plugin architecture system.

This module tests the plugin system including discovery, registration,
execution, and the built-in plugin implementations.
"""

import tempfile
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from returns.result import Failure
from returns.result import Success

from devhub.main import BundleData
from devhub.main import Repository
from devhub.plugins import PluginCapability
from devhub.plugins import PluginConfig
from devhub.plugins import PluginMetadata
from devhub.plugins import PluginRegistry
from devhub.plugins import PluginResult
from devhub.plugins import get_global_registry
from devhub.plugins import shutdown_global_registry
from devhub.plugins_builtin import EnrichmentTransformPlugin
from devhub.plugins_builtin import GitLabDataSourcePlugin
from devhub.plugins_builtin import HTMLOutputPlugin
from devhub.plugins_builtin import JSONOutputPlugin
from devhub.plugins_builtin import LinearDataSourcePlugin
from devhub.sdk import ContextRequest


class TestPluginMetadata:
    """Test PluginMetadata dataclass."""

    def test_plugin_metadata_creation(self) -> None:
        """Test creating plugin metadata."""
        metadata = PluginMetadata(
            name="test_plugin",
            version="1.0.0",
            author="Test Author",
            description="Test plugin description",
            capabilities=(PluginCapability.DATA_SOURCE, PluginCapability.OUTPUT),
            dependencies=("requests", "pydantic"),
            priority=50,
        )

        assert metadata.name == "test_plugin"
        assert metadata.version == "1.0.0"
        assert metadata.capabilities == (PluginCapability.DATA_SOURCE, PluginCapability.OUTPUT)
        assert metadata.dependencies == ("requests", "pydantic")
        assert metadata.priority == 50

    def test_supports_capability(self) -> None:
        """Test capability checking."""
        metadata = PluginMetadata(
            name="multi_plugin",
            version="1.0.0",
            author="Author",
            description="Multi-capability plugin",
            capabilities=(PluginCapability.DATA_SOURCE, PluginCapability.TRANSFORM),
        )

        assert metadata.supports_capability(PluginCapability.DATA_SOURCE)
        assert metadata.supports_capability(PluginCapability.TRANSFORM)
        assert not metadata.supports_capability(PluginCapability.OUTPUT)

    def test_version_compatibility(self) -> None:
        """Test version compatibility checking."""
        metadata = PluginMetadata(
            name="versioned_plugin",
            version="1.2.3",
            author="Author",
            description="Version test plugin",
            capabilities=(PluginCapability.OUTPUT,),
        )

        # Same major version, higher minor
        assert metadata.is_compatible_with("1.1.0")
        assert metadata.is_compatible_with("1.2.0")

        # Same version
        assert metadata.is_compatible_with("1.2.3")

        # Different major version
        assert not metadata.is_compatible_with("2.0.0")
        assert not metadata.is_compatible_with("0.9.0")

        # Lower minor version
        assert not metadata.is_compatible_with("1.3.0")

    def test_plugin_metadata_immutability(self) -> None:
        """Test that plugin metadata is immutable."""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            author="Author",
            description="Test",
            capabilities=(PluginCapability.OUTPUT,),
        )

        with pytest.raises(AttributeError):
            metadata.name = "modified"  # type: ignore[misc]


class TestPluginConfig:
    """Test PluginConfig dataclass."""

    def test_plugin_config_defaults(self) -> None:
        """Test default plugin configuration."""
        config = PluginConfig()

        assert config.enabled is True
        assert config.config == {}
        assert config.priority_override is None

    def test_plugin_config_custom(self) -> None:
        """Test custom plugin configuration."""
        config = PluginConfig(
            enabled=False,
            config={"api_key": "secret", "timeout": 30},
            priority_override=10,
        )

        assert config.enabled is False
        assert config.config == {"api_key": "secret", "timeout": 30}
        assert config.priority_override == 10

    def test_plugin_config_immutability(self) -> None:
        """Test that plugin config is immutable."""
        config = PluginConfig()
        with pytest.raises(AttributeError):
            config.enabled = False  # type: ignore[misc]


class TestPluginResult:
    """Test PluginResult dataclass."""

    def test_success_result_creation(self) -> None:
        """Test creating successful plugin result."""
        data = {"key": "value"}
        result = PluginResult.success_result(
            "test_plugin",
            data,
            execution_time=123.45,
            metadata={"extra": "info"},
        )

        assert result.plugin_name == "test_plugin"
        assert result.success is True
        assert result.data == data
        assert result.error is None
        assert result.execution_time_ms == 123.45
        assert result.metadata == {"extra": "info"}

    def test_failure_result_creation(self) -> None:
        """Test creating failed plugin result."""
        result: PluginResult[None] = PluginResult.failure_result(
            "failing_plugin",
            "Something went wrong",
            execution_time=67.89,
        )

        assert result.plugin_name == "failing_plugin"
        assert result.success is False
        assert result.data is None
        assert result.error == "Something went wrong"
        assert result.execution_time_ms == 67.89

    def test_plugin_result_immutability(self) -> None:
        """Test that plugin result is immutable."""
        result = PluginResult.success_result("test", {"data": "value"})
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


class MockDataSourcePlugin:
    """Mock data source plugin for testing."""

    metadata = PluginMetadata(
        name="mock_datasource",
        version="1.0.0",
        author="Test",
        description="Mock data source",
        capabilities=(PluginCapability.DATA_SOURCE,),
    )

    def __init__(self) -> None:
        """Initialize mock plugin."""
        self.initialized = False

    async def initialize(self, _config: PluginConfig) -> Success[None] | Failure[str]:
        """Initialize mock plugin."""
        self.initialized = True
        return Success(None)

    async def shutdown(self) -> Success[None] | Failure[str]:
        """Shutdown mock plugin."""
        self.initialized = False
        return Success(None)

    def validate_config(self, _config: dict[str, Any]) -> Success[None] | Failure[str]:
        """Validate mock plugin configuration."""
        return Success(None)

    async def fetch_data(
        self,
        request: ContextRequest,
        _context: dict[str, Any],
    ) -> Success[dict[str, Any]] | Failure[str]:
        """Fetch mock data."""
        return Success({"mock": "data", "request_id": str(id(request))})

    def get_supported_sources(self) -> tuple[str, ...]:
        """Get supported sources."""
        return ("mock_api",)


class MockTransformPlugin:
    """Mock transform plugin for testing."""

    metadata = PluginMetadata(
        name="mock_transform",
        version="1.0.0",
        author="Test",
        description="Mock transform",
        capabilities=(PluginCapability.TRANSFORM,),
        priority=10,
    )

    async def initialize(self, _config: PluginConfig) -> Success[None] | Failure[str]:
        """Initialize mock plugin."""
        return Success(None)

    async def shutdown(self) -> Success[None] | Failure[str]:
        """Shutdown mock plugin."""
        return Success(None)

    def validate_config(self, _config: dict[str, Any]) -> Success[None] | Failure[str]:
        """Validate mock plugin configuration."""
        return Success(None)

    async def transform_bundle(
        self,
        bundle: BundleData,
        _config: dict[str, Any],
    ) -> Success[BundleData] | Failure[str]:
        """Transform mock bundle."""
        # Return the same bundle (no actual transformation)
        return Success(bundle)

    def get_supported_transforms(self) -> tuple[str, ...]:
        """Get supported transforms."""
        return ("mock_transform",)


class TestPluginRegistry:
    """Test PluginRegistry functionality."""

    @pytest.mark.asyncio
    async def test_register_plugin_success(self) -> None:
        """Test successful plugin registration."""
        registry = PluginRegistry()
        plugin = MockDataSourcePlugin()

        result = await registry.register_plugin(plugin)
        assert isinstance(result, Success)

        # Verify plugin is registered
        registered_plugin = registry.get_plugin("mock_datasource")
        assert registered_plugin is plugin

    @pytest.mark.asyncio
    async def test_register_plugin_duplicate_name(self) -> None:
        """Test registering plugin with duplicate name."""
        registry = PluginRegistry()
        plugin1 = MockDataSourcePlugin()
        plugin2 = MockDataSourcePlugin()

        # Register first plugin
        result1 = await registry.register_plugin(plugin1)
        assert isinstance(result1, Success)

        # Try to register second plugin with same name
        result2 = await registry.register_plugin(plugin2)
        assert isinstance(result2, Failure)
        assert "already registered" in str(result2)

    @pytest.mark.asyncio
    async def test_register_plugin_with_config(self) -> None:
        """Test registering plugin with configuration."""
        registry = PluginRegistry()
        plugin = MockDataSourcePlugin()
        config = PluginConfig(
            enabled=True,
            config={"test_param": "test_value"},
        )

        result = await registry.register_plugin(plugin, config)
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_initialize_plugins(self) -> None:
        """Test initializing all registered plugins."""
        registry = PluginRegistry()
        plugin = MockDataSourcePlugin()

        await registry.register_plugin(plugin)
        assert not plugin.initialized

        result = await registry.initialize_plugins()
        assert isinstance(result, Success)
        assert result.unwrap() == 1  # One plugin initialized
        assert plugin.initialized

    @pytest.mark.asyncio
    async def test_shutdown_plugins(self) -> None:
        """Test shutting down all plugins."""
        registry = PluginRegistry()
        plugin = MockDataSourcePlugin()

        await registry.register_plugin(plugin)
        await registry.initialize_plugins()
        assert plugin.initialized

        result = await registry.shutdown_plugins()
        assert isinstance(result, Success)
        assert not plugin.initialized

    @pytest.mark.asyncio
    async def test_get_plugins_by_capability(self) -> None:
        """Test getting plugins by capability."""
        registry = PluginRegistry()
        datasource_plugin = MockDataSourcePlugin()
        transform_plugin = MockTransformPlugin()

        await registry.register_plugin(datasource_plugin)
        await registry.register_plugin(transform_plugin)
        await registry.initialize_plugins()

        # Get data source plugins
        data_plugins = registry.get_plugins_by_capability(PluginCapability.DATA_SOURCE)
        assert len(data_plugins) == 1
        assert data_plugins[0] is datasource_plugin

        # Get transform plugins
        transform_plugins = registry.get_plugins_by_capability(PluginCapability.TRANSFORM)
        assert len(transform_plugins) == 1
        assert transform_plugins[0] is transform_plugin

        # Get output plugins (none registered)
        output_plugins = registry.get_plugins_by_capability(PluginCapability.OUTPUT)
        assert len(output_plugins) == 0

    @pytest.mark.asyncio
    async def test_execute_data_source_plugins(self) -> None:
        """Test executing data source plugins."""
        registry = PluginRegistry()
        plugin = MockDataSourcePlugin()

        await registry.register_plugin(plugin)
        await registry.initialize_plugins()

        request = ContextRequest()
        context = {"test": "context"}

        results = [result async for result in registry.execute_data_source_plugins(request, context)]

        assert len(results) == 1
        result = results[0]
        assert result.plugin_name == "mock_datasource"
        assert result.success is True
        assert result.data == {"mock": "data", "request_id": str(id(request))}

    @pytest.mark.asyncio
    async def test_execute_transform_plugins(self) -> None:
        """Test executing transform plugins."""
        registry = PluginRegistry()
        plugin = MockTransformPlugin()

        await registry.register_plugin(plugin)
        await registry.initialize_plugins()

        bundle = BundleData(
            repository=Repository(owner="test", name="repo"),
            branch="main",
        )

        result = await registry.execute_transform_plugins(bundle)
        assert isinstance(result, Success)
        assert result.unwrap() is bundle  # Same bundle returned

    def test_list_plugins(self) -> None:
        """Test listing all registered plugins."""
        registry = PluginRegistry()

        # Empty registry
        plugins = registry.list_plugins()
        assert len(plugins) == 0

    @pytest.mark.asyncio
    async def test_discover_plugins_nonexistent_path(self) -> None:
        """Test plugin discovery with non-existent path."""
        registry = PluginRegistry()

        result = await registry.discover_plugins("/nonexistent/path")
        assert isinstance(result, Failure)
        assert "not found" in str(result)

    @pytest.mark.asyncio
    async def test_discover_plugins_empty_directory(self) -> None:
        """Test plugin discovery in empty directory."""
        registry = PluginRegistry()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = await registry.discover_plugins(temp_dir)
            assert isinstance(result, Success)
            assert result.unwrap() == 0  # No plugins found


class TestGlobalRegistry:
    """Test global registry functions."""

    def test_get_global_registry(self) -> None:
        """Test getting global registry instance."""
        registry1 = get_global_registry()
        registry2 = get_global_registry()

        # Should return same instance
        assert registry1 is registry2

    @pytest.mark.asyncio
    async def test_shutdown_global_registry(self) -> None:
        """Test shutting down global registry."""
        registry = get_global_registry()

        # Add a plugin to verify cleanup
        plugin = MockDataSourcePlugin()
        await registry.register_plugin(plugin)
        await registry.initialize_plugins()

        await shutdown_global_registry()

        # Getting registry again should create new instance
        new_registry = get_global_registry()
        assert new_registry is not registry


class TestBuiltinPlugins:
    """Test built-in plugin implementations."""

    @pytest.mark.asyncio
    async def test_gitlab_datasource_plugin(self) -> None:
        """Test GitLab data source plugin."""
        plugin = GitLabDataSourcePlugin()

        # Test configuration validation
        valid_config = {"token": "gitlab_token", "url": "https://gitlab.example.com"}
        result = plugin.validate_config(valid_config)
        assert isinstance(result, Success)

        invalid_config: dict[str, Any] = {}  # Missing token
        result = plugin.validate_config(invalid_config)
        assert isinstance(result, Failure)

        # Test initialization
        config = PluginConfig(config=valid_config)
        result = await plugin.initialize(config)
        assert isinstance(result, Success)

        # Test data fetching
        request = ContextRequest()
        context = {"gitlab_project_id": "123", "gitlab_mr_number": "456"}
        fetch_result = await plugin.fetch_data(request, context)
        assert isinstance(fetch_result, Success)
        data = fetch_result.unwrap()
        assert "merge_request" in data
        assert data["merge_request"]["id"] == "456"

        # Test shutdown
        result = await plugin.shutdown()
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_linear_datasource_plugin(self) -> None:
        """Test Linear data source plugin."""
        plugin = LinearDataSourcePlugin()

        # Test configuration validation
        valid_config = {"token": "linear_token"}
        result = plugin.validate_config(valid_config)
        assert isinstance(result, Success)

        # Test initialization
        config = PluginConfig(config=valid_config)
        result = await plugin.initialize(config)
        assert isinstance(result, Success)

        # Test data fetching
        request = ContextRequest()
        context = {"linear_issue_id": "DEV-123"}
        fetch_result = await plugin.fetch_data(request, context)
        assert isinstance(fetch_result, Success)
        data = fetch_result.unwrap()
        assert "issue" in data
        assert data["issue"]["id"] == "DEV-123"

        # Test supported sources
        sources = plugin.get_supported_sources()
        assert "issues" in sources

    @pytest.mark.asyncio
    async def test_enrichment_transform_plugin(self) -> None:
        """Test enrichment transform plugin."""
        plugin = EnrichmentTransformPlugin()

        # Test initialization
        config = PluginConfig()
        result = await plugin.initialize(config)
        assert isinstance(result, Success)

        # Test transformation
        bundle = BundleData(
            repository=Repository(owner="test", name="repo"),
            branch="main",
            pr_diff="line1\nline2\nline3",
            comments=tuple(),
        )

        transform_result = await plugin.transform_bundle(bundle, {})
        assert isinstance(transform_result, Success)
        transformed_bundle = transform_result.unwrap()
        # Bundle should be returned (actual enrichment would modify it)
        assert transformed_bundle is bundle

        # Test supported transforms
        transforms = plugin.get_supported_transforms()
        assert "complexity" in transforms
        assert "sentiment" in transforms

    @pytest.mark.asyncio
    async def test_html_output_plugin(self) -> None:
        """Test HTML output plugin."""
        plugin = HTMLOutputPlugin()

        # Test initialization
        config = PluginConfig()
        result = await plugin.initialize(config)
        assert isinstance(result, Success)

        # Test output formatting
        bundle = BundleData(
            repository=Repository(owner="test", name="repo"),
            branch="main",
        )

        format_options = {"theme": "default", "include_css": True}
        format_result = await plugin.format_output(bundle, format_options)
        assert isinstance(format_result, Success)
        html_output = format_result.unwrap()
        assert isinstance(html_output, str)
        assert "<!DOCTYPE html>" in html_output
        assert "test/repo" in html_output

        # Test supported formats
        formats = plugin.get_supported_formats()
        assert "html" in formats

        # Test file extension
        ext = plugin.get_file_extension("html")
        assert ext == ".html"

    @pytest.mark.asyncio
    async def test_json_output_plugin(self) -> None:
        """Test JSON output plugin."""
        plugin = JSONOutputPlugin()

        # Test initialization
        config = PluginConfig()
        result = await plugin.initialize(config)
        assert isinstance(result, Success)

        # Test output formatting
        bundle = BundleData(
            repository=Repository(owner="test", name="repo"),
            branch="main",
        )

        format_options = {"pretty": True, "include_metadata": True}
        format_result = await plugin.format_output(bundle, format_options)
        assert isinstance(format_result, Success)
        json_output = format_result.unwrap()
        assert isinstance(json_output, str)

        # Parse JSON to verify it's valid
        import json

        parsed = json.loads(json_output)
        assert "_meta" in parsed
        assert "format_version" in parsed["_meta"]

        # Test file extension
        ext = plugin.get_file_extension("json")
        assert ext == ".json"


class TestPropertyBased:
    """Property-based tests for plugin system."""

    @given(st.text(min_size=1, max_size=50))
    def test_plugin_metadata_name_property(self, name: str) -> None:
        """Test plugin metadata with various names."""
        metadata = PluginMetadata(
            name=name,
            version="1.0.0",
            author="Test Author",
            description="Test description",
            capabilities=(PluginCapability.OUTPUT,),
        )

        assert metadata.name == name
        assert len(metadata.capabilities) > 0

    @given(
        st.integers(min_value=0, max_value=1000),
        st.integers(min_value=0, max_value=1000),
    )
    def test_plugin_result_execution_time(
        self,
        execution_time: int,
        data_size: int,
    ) -> None:
        """Test plugin result with various execution times."""
        data = {"items": list(range(data_size))}
        result = PluginResult.success_result(
            "test_plugin",
            data,
            execution_time=float(execution_time),
        )

        assert result.execution_time_ms == execution_time
        assert result.data is not None
        assert len(result.data["items"]) == data_size
        assert result.success is True
