# DevHub Contributing Guidelines

## Overview

DevHub serves as a **shining example** of clean, maintainable Python code that strictly adheres to **Functional Programming (FP) principles**. This document outlines our standards for maintaining the highest quality codebase through immutable data structures, modularity, and comprehensive documentation.

## Core Principles

### 1. Functional Programming First
- **Pure Functions**: All functions should be pure when possible - same input always produces same output with no side effects
- **Immutability**: Use immutable data structures throughout the codebase
- **Composition over Inheritance**: Favor function composition and data transformation pipelines
- **Explicit Side Effects**: Isolate and clearly mark functions that perform I/O or other side effects

### 2. Type Safety Excellence
- **Comprehensive Type Hints**: Every function, method, and variable must have explicit type annotations
- **Strict Type Checking**: Maintain 100% compliance with mypy and pyright in strict mode
- **Result Types**: Use `returns.Result` for error handling instead of exceptions where appropriate
- **No `Any` Types**: Avoid `Any` types except when interfacing with untyped third-party libraries

### 3. Immutable Data Structures

#### Domain Models
All domain models must be implemented as frozen dataclasses:

```python
@dataclass(frozen=True, slots=True)
class MyModel:
    """Immutable domain model with clear documentation."""
    field1: str
    field2: int
    optional_field: str | None = None
```

#### Collections
- Use `tuple` instead of `list` for fixed collections
- Use `frozenset` instead of `set` for immutable collections
- Consider `immutables.Map` for large dictionaries that need frequent updates
- Prefer `toolz` functions for data transformations

#### Data Transformations
```python
# Good: Functional transformation
def transform_data(items: tuple[Item, ...]) -> tuple[ProcessedItem, ...]:
    return tuple(
        ProcessedItem(name=item.name.upper(), value=item.value * 2)
        for item in items
    )

# Avoid: Mutating collections
def transform_data_bad(items: list[Item]) -> list[ProcessedItem]:
    items.sort()  # Mutation!
    return [process(item) for item in items]
```

### 4. Error Handling with Result Types

Use `returns.Result` for operations that can fail:

```python
def fetch_data(url: str) -> Result[Data, str]:
    """Fetch data from URL, returning Result type for error handling."""
    try:
        response = urllib.request.urlopen(url)
        data = json.loads(response.read())
        return Success(Data.from_dict(data))
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        return Failure(f"Failed to fetch data: {e}")
```

## Code Organization and Modularity

### File Structure
- **Single Responsibility**: Each module should have one clear purpose
- **Pure Functions**: Group pure functions together
- **Side Effects**: Isolate I/O and side effects in dedicated modules
- **Domain Models**: Keep all domain models in a dedicated section or module

### Function Design
- **Small Functions**: Maximum 30 statements per function (enforced by Pylint)
- **Single Purpose**: Each function should do exactly one thing well
- **Descriptive Names**: Function names should clearly indicate their purpose and return type
- **Parameter Limits**: Maximum 5 parameters per function (use dataclasses for more complex input)

### Dependency Management
- **Functional Libraries**: Prioritize libraries that support FP patterns (`returns`, `toolz`, `attrs`, `immutables`)
- **Pure Dependencies**: Prefer libraries with minimal side effects
- **Version Pinning**: Pin all dependencies to specific versions for reproducibility

## Documentation Standards

### Module Documentation
Every module must start with a comprehensive docstring:

```python
"""Module for handling GitHub API interactions.

This module provides pure functions for fetching and transforming GitHub data,
following strict functional programming principles. All functions are pure
except those explicitly marked as performing I/O operations.

Functions:
    fetch_repository_info: Fetch repository metadata from GitHub API
    parse_pull_request: Transform raw PR data into domain model
    
Classes:
    Repository: Immutable repository information
    PullRequest: Immutable pull request data
"""
```

### Function Documentation
Use Google-style docstrings for all functions:

```python
def transform_comments(
    comments: tuple[RawComment, ...], 
    filter_resolved: bool = True
) -> Result[tuple[ReviewComment, ...], str]:
    """Transform raw comments into domain models.
    
    Pure function that converts raw GitHub comment data into immutable
    ReviewComment instances, optionally filtering resolved comments.
    
    Args:
        comments: Tuple of raw comment data from GitHub API
        filter_resolved: Whether to exclude resolved comments
        
    Returns:
        Result containing tuple of ReviewComment instances, or error message
        
    Example:
        >>> raw_comments = (RawComment(...), RawComment(...))
        >>> result = transform_comments(raw_comments)
        >>> match result:
        ...     case Success(comments): print(f"Got {len(comments)} comments")
        ...     case Failure(error): print(f"Error: {error}")
    """
```

### Class Documentation
Document all classes with their immutability guarantees:

```python
@dataclass(frozen=True, slots=True)
class ReviewComment:
    """Immutable review comment representation.
    
    This class represents a GitHub pull request review comment with
    all fields frozen to ensure immutability. Use factory methods
    or dataclass replace() for creating modified versions.
    
    Attributes:
        id: Unique comment identifier
        body: Comment text content
        path: File path where comment was made (None for general comments)
        author: Comment author username (None if unavailable)
        created_at: ISO timestamp of comment creation
        diff_hunk: Code diff context for the comment
        resolved: Whether the comment thread is resolved
    """
    id: str
    body: str
    path: str | None
    author: str | None
    created_at: str | None
    diff_hunk: str | None
    resolved: bool
```

## Code Quality Standards

### Linting and Formatting
- **Ruff**: Use all rules (`select = ["ALL"]`) with minimal exceptions
- **Line Length**: 120 characters maximum
- **Import Sorting**: Single-line imports, sorted alphabetically
- **Docstring Style**: Google convention for all docstrings

### Type Checking
- **MyPy**: Strict mode enabled with all warnings
- **PyRight**: Strict type checking mode
- **Coverage**: 100% type annotation coverage required

### Testing Standards
- **Property-Based Testing**: Use Hypothesis for testing pure functions
- **Coverage**: Minimum 90% test coverage required
- **Pure Function Tests**: Test pure functions with various inputs
- **Side Effect Tests**: Mock all external dependencies

```python
from hypothesis import given, strategies as st

@given(st.lists(st.text(min_size=1)))
def test_transform_data_properties(raw_data: list[str]) -> None:
    """Property-based test for data transformation."""
    input_tuple = tuple(raw_data)
    result = transform_data(input_tuple)
    
    # Properties that should always hold
    assert len(result) == len(input_tuple)
    assert all(isinstance(item, ProcessedItem) for item in result)
    
    # Transformation should be deterministic
    assert transform_data(input_tuple) == result
```

### Performance Considerations
- **Immutable Collections**: Use appropriate immutable collections for performance
- **Lazy Evaluation**: Use generators and itertools for large data processing
- **Memory Efficiency**: Prefer `slots=True` in dataclasses
- **Profiling**: Profile critical paths and optimize hot spots

## Development Workflow

### Pre-commit Hooks
All code must pass pre-commit hooks before submission:
- Type checking (mypy, pyright)
- Linting (ruff)
- Security scanning (bandit, semgrep)
- Test execution (pytest)
- Documentation validation

### Code Review Standards
- **FP Compliance**: Reviewer must verify adherence to FP principles
- **Immutability**: Verify all data structures remain immutable
- **Documentation**: Ensure comprehensive documentation for all additions
- **Test Coverage**: Verify adequate test coverage for new functionality

### Commit Message Standards
Use Conventional Commits format:
```
feat(core): add immutable configuration parsing

- Implement ConfigParser with frozen dataclass
- Add Result-based error handling for invalid configs
- Include comprehensive property-based tests
- Update documentation with usage examples

Resolves: #123
```

## Migration Guidelines

### Converting Mutable to Immutable
When updating existing code:

1. **Identify Mutable State**: Find all mutable data structures
2. **Create Immutable Alternatives**: Replace with frozen dataclasses or immutable collections
3. **Update Functions**: Ensure functions return new instances instead of modifying existing ones
4. **Add Type Hints**: Ensure full type coverage for updated code
5. **Test Thoroughly**: Add comprehensive tests for the new immutable version

### Adding New Features
For new functionality:

1. **Design Immutable First**: Start with immutable data models
2. **Pure Functions**: Implement business logic as pure functions
3. **Isolate Side Effects**: Separate I/O operations from pure logic
4. **Comprehensive Testing**: Include both unit and property-based tests
5. **Document Thoroughly**: Follow documentation standards

## Examples

### Good: Functional Pipeline
```python
def process_bundle_data(
    config: BundleConfig, 
    raw_data: dict[str, Any]
) -> Result[ProcessedBundle, str]:
    """Process raw bundle data through functional pipeline."""
    return (
        parse_raw_data(raw_data)
        .bind(validate_bundle_structure)
        .bind(lambda bundle: transform_bundle(bundle, config))
        .bind(enrich_bundle_metadata)
    )
```

### Good: Immutable Updates
```python
def update_config_limit(config: BundleConfig, new_limit: int) -> BundleConfig:
    """Create new config with updated limit."""
    return dataclasses.replace(config, limit=new_limit)
```

### Avoid: Mutable Operations
```python
# Don't do this
def bad_update_config(config: BundleConfig, new_limit: int) -> None:
    config.limit = new_limit  # Can't do this with frozen dataclass anyway
```

## Conclusion

By following these guidelines, DevHub maintains its position as an exemplary Python project that showcases the power and elegance of functional programming. Every contribution should strengthen our commitment to immutability, type safety, and clear documentation.

Remember: **We're not just building software; we're demonstrating how beautiful, maintainable, and robust Python code can be when FP principles are properly applied.**