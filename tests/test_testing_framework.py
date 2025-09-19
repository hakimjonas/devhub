"""Comprehensive tests for the advanced testing framework."""

import tempfile
import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st
from returns.result import Failure
from returns.result import Success

from devhub.testing_framework import AdvancedTestRunner
from devhub.testing_framework import ContractTest
from devhub.testing_framework import PerformanceMetrics
from devhub.testing_framework import TestingExecution
from devhub.testing_framework import TestingResult
from devhub.testing_framework import TestingStrategy
from devhub.testing_framework import TestingSuite
from devhub.testing_framework import get_global_runner
from devhub.testing_framework import reset_global_runner


class TestPerformanceMetrics:
    """Test performance metrics functionality."""

    def test_performance_metrics_creation(self) -> None:
        """Test performance metrics creation."""
        metrics = PerformanceMetrics(
            execution_time_seconds=1.5,
            memory_usage_mb=128.0,
            success_count=10,
            error_count=2,
        )
        assert metrics.execution_time_seconds == 1.5
        assert metrics.memory_usage_mb == 128.0
        assert metrics.success_count == 10
        assert metrics.error_count == 2
        assert metrics.total_operations == 12
        assert metrics.success_rate == (10 / 12) * 100

    def test_performance_metrics_properties(self) -> None:
        """Test performance metrics calculated properties."""
        # Test with no operations
        empty_metrics = PerformanceMetrics(execution_time_seconds=0.0)
        assert empty_metrics.total_operations == 0
        assert empty_metrics.success_rate == 0.0

        # Test with only successes
        success_metrics = PerformanceMetrics(
            execution_time_seconds=1.0,
            success_count=5,
            error_count=0,
        )
        assert success_metrics.success_rate == 100.0

        # Test with only errors
        error_metrics = PerformanceMetrics(
            execution_time_seconds=1.0,
            success_count=0,
            error_count=3,
        )
        assert error_metrics.success_rate == 0.0


class TestContractTest:
    """Test contract testing functionality."""

    def test_contract_test_creation(self) -> None:
        """Test contract test creation."""
        spec = {"openapi": "3.0.0", "info": {"title": "Test API"}}
        contract = ContractTest(
            name="user_api_contract",
            provider="user_service",
            consumer="web_client",
            specification=spec,
        )
        assert contract.name == "user_api_contract"
        assert contract.provider == "user_service"
        assert contract.consumer == "web_client"
        assert contract.specification == spec
        assert contract.version == "1.0.0"
        assert len(contract.test_cases) == 0

    def test_contract_test_with_cases(self) -> None:
        """Test contract test with test cases."""
        test_cases = (
            {"method": "GET", "path": "/users", "expected_status": 200},
            {"method": "POST", "path": "/users", "expected_status": 201},
        )
        contract = ContractTest(
            name="test_contract",
            provider="api",
            consumer="client",
            specification={},
            test_cases=test_cases,
            version="2.0.0",
        )
        assert len(contract.test_cases) == 2
        assert contract.version == "2.0.0"


class TestTestingExecution:
    """Test test execution results."""

    def test_test_execution_creation(self) -> None:
        """Test test execution creation."""
        execution = TestingExecution(
            test_name="test_user_creation",
            strategy=TestingStrategy.UNIT,
            result=TestingResult.PASSED,
            execution_time=0.5,
        )
        assert execution.test_name == "test_user_creation"
        assert execution.strategy == TestingStrategy.UNIT
        assert execution.result == TestingResult.PASSED
        assert execution.execution_time == 0.5
        assert execution.error_message is None

    def test_test_execution_with_error(self) -> None:
        """Test test execution with error."""
        execution = TestingExecution(
            test_name="test_failing",
            strategy=TestingStrategy.INTEGRATION,
            result=TestingResult.FAILED,
            execution_time=1.0,
            error_message="Assertion failed",
            metadata={"retry_count": 3},
        )
        assert execution.result == TestingResult.FAILED
        assert execution.error_message == "Assertion failed"
        assert execution.metadata["retry_count"] == 3


class TestTestingSuite:
    """Test test suite configuration."""

    def test_default_test_suite(self) -> None:
        """Test default test suite configuration."""
        suite = TestingSuite("default_suite")
        assert suite.name == "default_suite"
        assert TestingStrategy.UNIT in suite.enabled_strategies
        assert TestingStrategy.INTEGRATION in suite.enabled_strategies
        assert suite.timeout_seconds == 300.0
        assert suite.parallel_execution is True

    def test_custom_test_suite(self) -> None:
        """Test custom test suite configuration."""
        strategies = frozenset([TestingStrategy.PERFORMANCE, TestingStrategy.CONTRACT])
        suite = TestingSuite(
            name="performance_suite",
            enabled_strategies=strategies,
            timeout_seconds=600.0,
            parallel_execution=False,
        )
        assert suite.enabled_strategies == strategies
        assert suite.timeout_seconds == 600.0
        assert suite.parallel_execution is False


class TestAdvancedTestRunner:
    """Test advanced test runner functionality."""

    @pytest.fixture
    def test_suite(self) -> TestingSuite:
        """Create test suite for testing."""
        return TestingSuite(
            "test_suite",
            enabled_strategies=frozenset(
                [
                    TestingStrategy.UNIT,
                    TestingStrategy.PERFORMANCE,
                    TestingStrategy.CONTRACT,
                ]
            ),
        )

    @pytest.fixture
    def test_runner(self, test_suite: TestingSuite) -> AdvancedTestRunner:
        """Create test runner for testing."""
        return AdvancedTestRunner(test_suite)

    def test_runner_initialization(self, test_runner: AdvancedTestRunner) -> None:
        """Test runner initialization."""
        assert test_runner is not None

    def test_register_test_function(self, test_runner: AdvancedTestRunner) -> None:
        """Test test function registration."""

        def sample_test() -> None:
            assert True

        result = test_runner.register_test_function(sample_test, TestingStrategy.UNIT)
        assert isinstance(result, Success)

        # Test registering with disabled strategy
        result = test_runner.register_test_function(sample_test, TestingStrategy.CHAOS)
        assert isinstance(result, Failure)
        assert "not enabled" in str(result).lower()

    def test_performance_test_decorator(self, test_runner: AdvancedTestRunner) -> None:
        """Test performance test decorator."""

        @test_runner.performance_test(thresholds={"execution_time_seconds": 1.0})
        def fast_test() -> None:
            time.sleep(0.01)  # Should pass threshold

        # This should execute without raising an exception
        fast_test()

        @test_runner.performance_test(thresholds={"execution_time_seconds": 0.001})
        def slow_test() -> None:
            time.sleep(0.01)  # Should fail threshold

        # This should raise an AssertionError due to threshold violation
        with pytest.raises(AssertionError, match="Performance thresholds violated"):
            slow_test()

    def test_performance_test_with_exception(self, test_runner: AdvancedTestRunner) -> None:
        """Test performance test decorator with exception in test."""

        @test_runner.performance_test()
        def failing_test() -> None:
            msg = "Test error"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Test error"):
            failing_test()

        # Check that error was recorded
        assert test_runner.get_success_rate() < 100.0

    def test_contract_test_decorator(self, test_runner: AdvancedTestRunner) -> None:
        """Test contract test decorator."""
        contract = ContractTest("test_contract", "provider", "consumer", {"version": "1.0"})

        @test_runner.contract_test(contract)
        def contract_validation_test() -> None:
            # Simulate contract validation
            assert True

        # Should execute without exception
        contract_validation_test()

    def test_run_all_tests(self, test_runner: AdvancedTestRunner) -> None:
        """Test running all registered tests."""

        def unit_test() -> None:
            assert True

        def failing_test() -> None:
            msg = "Test failed"
            raise AssertionError(msg)

        test_runner.register_test_function(unit_test, TestingStrategy.UNIT)
        test_runner.register_test_function(failing_test, TestingStrategy.UNIT)

        result = test_runner.run_all_tests()
        assert isinstance(result, Success)

        executions = result.unwrap()
        assert len(executions) >= 2

        # Check that we have both passed and failed results
        results = [e.result for e in executions]
        assert TestingResult.PASSED in results
        assert TestingResult.FAILED in results

    def test_success_rate_calculation(self, test_runner: AdvancedTestRunner) -> None:
        """Test success rate calculation."""
        # Initially no tests
        assert test_runner.get_success_rate() == 0.0

        # Add some test results manually for testing
        test_runner._test_results = [
            TestingExecution("test1", TestingStrategy.UNIT, TestingResult.PASSED),
            TestingExecution("test2", TestingStrategy.UNIT, TestingResult.PASSED),
            TestingExecution("test3", TestingStrategy.UNIT, TestingResult.FAILED),
        ]

        # Should be 66.67% (2 out of 3 passed)
        success_rate = test_runner.get_success_rate()
        assert abs(success_rate - 66.666666666666667) < 0.001

    def test_performance_summary(self, test_runner: AdvancedTestRunner) -> None:
        """Test performance summary generation."""
        # Initially no performance tests
        summary = test_runner.get_performance_summary()
        assert summary["total_tests"] == 0

        # Add performance test results
        metrics = PerformanceMetrics(
            execution_time_seconds=1.5,
            memory_usage_mb=64.0,
            success_count=1,
        )
        test_runner._test_results = [
            TestingExecution(
                "perf_test",
                TestingStrategy.PERFORMANCE,
                TestingResult.PASSED,
                performance_metrics=metrics,
            )
        ]

        summary = test_runner.get_performance_summary()
        assert summary["total_tests"] == 1
        assert summary["average_execution_time"] == 1.5
        assert summary["average_memory_usage"] == 64.0
        assert summary["success_rate"] == 100.0

    def test_mutation_score(self, test_runner: AdvancedTestRunner) -> None:
        """Test mutation score calculation."""
        # Initially no mutations
        assert test_runner.get_mutation_score() == 0.0

        # Add some mutation results manually
        from devhub.testing_framework import MutationTestingResult

        test_runner._mutation_results = {
            "mut1": MutationTestingResult("mut1", "==", "!=", "comparison", killed=True),
            "mut2": MutationTestingResult("mut2", "<", "<=", "comparison", killed=False),
            "mut3": MutationTestingResult("mut3", ">", ">=", "comparison", killed=True),
        }

        # Should be 66.67% (2 out of 3 killed)
        score = test_runner.get_mutation_score()
        assert abs(score - 66.666666666666667) < 0.001

    def test_export_results(self, test_runner: AdvancedTestRunner) -> None:
        """Test exporting test results."""
        # Add some test results
        test_runner._test_results = [
            TestingExecution("test1", TestingStrategy.UNIT, TestingResult.PASSED, execution_time=0.5),
            TestingExecution("test2", TestingStrategy.UNIT, TestingResult.FAILED, error_message="Failed"),
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_file = Path(f.name)

        try:
            result = test_runner.export_results(output_file)
            assert isinstance(result, Success)
            assert output_file.exists()

            # Verify exported content
            import json

            with output_file.open(encoding="utf-8") as f:
                data = json.load(f)

            assert "test_suite" in data
            assert "summary" in data
            assert "test_results" in data
            assert len(data["test_results"]) == 2

        finally:
            if output_file.exists():
                output_file.unlink()

    def test_mutation_testing(self, test_runner: AdvancedTestRunner) -> None:
        """Test mutation testing functionality."""
        # Create a simple Python file for testing
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
def compare_values(a, b):
    if a == b:
        return True
    elif a < b:
        return False
    else:
        return None
""")
            source_file = Path(f.name)

        try:
            result = test_runner.run_mutation_tests(source_file)
            assert isinstance(result, Success)

            mutations = result.unwrap()
            assert len(mutations) > 0

            # Check that mutations were generated
            for mutation in mutations:
                assert mutation.mutation_id
                assert mutation.original_code
                assert mutation.mutated_code
                assert mutation.mutation_type

        finally:
            if source_file.exists():
                source_file.unlink()

    def test_mutation_testing_invalid_file(self, test_runner: AdvancedTestRunner) -> None:
        """Test mutation testing with invalid file."""
        result = test_runner.run_mutation_tests(Path("nonexistent.py"))
        assert isinstance(result, Failure)
        assert "not found" in str(result).lower()

    @given(
        test_name=st.text(min_size=1, max_size=50),
        execution_time=st.floats(min_value=0.001, max_value=10.0, allow_nan=False),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_test_execution_property(
        self,
        test_runner: AdvancedTestRunner,
        test_name: str,
        execution_time: float,
    ) -> None:
        """Property test for test execution recording."""
        execution = TestingExecution(
            test_name=test_name,
            strategy=TestingStrategy.UNIT,
            result=TestingResult.PASSED,
            execution_time=execution_time,
        )

        test_runner._test_results.append(execution)
        assert len(test_runner._test_results) >= 1
        assert execution_time > 0.0


class TestGlobalTestRunner:
    """Test global test runner functionality."""

    def test_global_runner_singleton(self) -> None:
        """Test global runner singleton behavior."""
        reset_global_runner()  # Ensure clean state

        runner1 = get_global_runner()
        runner2 = get_global_runner()
        assert runner1 is runner2

    def test_global_runner_with_custom_suite(self) -> None:
        """Test global runner with custom suite."""
        reset_global_runner()

        custom_suite = TestingSuite("custom", enabled_strategies=frozenset([TestingStrategy.PERFORMANCE]))
        runner = get_global_runner(custom_suite)
        assert runner._suite.name == "custom"

    def test_global_runner_reset(self) -> None:
        """Test global runner reset functionality."""
        runner1 = get_global_runner()
        reset_global_runner()
        runner2 = get_global_runner()
        assert runner1 is not runner2


class TestTestingFrameworkIntegration:
    """Integration tests for the testing framework."""

    def test_complete_testing_workflow(self) -> None:
        """Test complete testing workflow."""
        # Create comprehensive test suite
        suite = TestingSuite(
            "integration_suite",
            enabled_strategies=frozenset(
                [
                    TestingStrategy.UNIT,
                    TestingStrategy.PERFORMANCE,
                    TestingStrategy.CONTRACT,
                ]
            ),
        )
        runner = AdvancedTestRunner(suite)

        # Register various types of tests
        @runner.performance_test(thresholds={"execution_time_seconds": 0.1})
        def performance_test() -> None:
            time.sleep(0.01)  # Should pass

        contract = ContractTest("api_contract", "service", "client", {"version": "1.0"})

        @runner.contract_test(contract)
        def contract_test() -> None:
            assert True

        def unit_test() -> None:
            assert 2 + 2 == 4

        # Register all test functions
        runner.register_test_function(unit_test, TestingStrategy.UNIT)
        runner.register_test_function(performance_test, TestingStrategy.PERFORMANCE)
        runner.register_test_function(contract_test, TestingStrategy.CONTRACT)

        # Run all tests
        result = runner.run_all_tests()
        assert isinstance(result, Success)

        # Verify results
        executions = result.unwrap()
        strategies = {e.strategy for e in executions}
        assert TestingStrategy.UNIT in strategies
        assert TestingStrategy.PERFORMANCE in strategies
        assert TestingStrategy.CONTRACT in strategies

        # Check success rate
        success_rate = runner.get_success_rate()
        assert success_rate > 0.0

        # Export results
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_file = Path(f.name)

        try:
            export_result = runner.export_results(output_file)
            assert isinstance(export_result, Success)
        finally:
            if output_file.exists():
                output_file.unlink()

    def test_error_handling_and_recovery(self) -> None:
        """Test error handling and recovery in testing framework."""
        suite = TestingSuite("error_test_suite")
        runner = AdvancedTestRunner(suite)

        # Test with various error conditions
        def exception_test() -> None:
            msg = "Simulated error"
            raise RuntimeError(msg)

        def assertion_test() -> None:
            msg = "Assertion failure"
            raise AssertionError(msg)

        def timeout_test() -> None:
            time.sleep(0.01)  # Simulate work

        runner.register_test_function(exception_test, TestingStrategy.UNIT)
        runner.register_test_function(assertion_test, TestingStrategy.UNIT)
        runner.register_test_function(timeout_test, TestingStrategy.UNIT)

        # Run tests - should handle errors gracefully
        result = runner.run_all_tests()
        assert isinstance(result, Success)

        executions = result.unwrap()
        assert len(executions) >= 3

        # Should have recorded failures
        failed_tests = [e for e in executions if e.result == TestingResult.FAILED]
        assert len(failed_tests) >= 2

        # Success rate should reflect failures
        success_rate = runner.get_success_rate()
        assert success_rate < 100.0

    def test_concurrent_test_execution(self) -> None:
        """Test framework behavior with concurrent operations."""
        suite = TestingSuite("concurrent_suite", parallel_execution=True)
        runner = AdvancedTestRunner(suite)

        # Register multiple tests that could run concurrently
        def concurrent_test_1() -> None:
            time.sleep(0.01)
            assert True

        def concurrent_test_2() -> None:
            time.sleep(0.01)
            assert True

        def concurrent_test_3() -> None:
            time.sleep(0.01)
            assert True

        runner.register_test_function(concurrent_test_1, TestingStrategy.UNIT)
        runner.register_test_function(concurrent_test_2, TestingStrategy.UNIT)
        runner.register_test_function(concurrent_test_3, TestingStrategy.UNIT)

        # Run tests
        time.time()
        result = runner.run_all_tests()
        time.time()

        assert isinstance(result, Success)
        executions = result.unwrap()
        assert len(executions) >= 3

        # All tests should pass
        passed_tests = [e for e in executions if e.result == TestingResult.PASSED]
        assert len(passed_tests) >= 3
