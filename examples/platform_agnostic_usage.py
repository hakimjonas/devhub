"""Example of platform-agnostic DevHub usage.

This example demonstrates how DevHub now treats all platforms as first-class citizens,
with no preferential treatment for GitHub or Jira.
"""

import asyncio

from devhub.platform_sdk import get_platform_sdk


async def main() -> None:
    """Demonstrate platform-agnostic usage."""
    # Get the unified platform SDK
    sdk = get_platform_sdk()

    # List all available platforms
    sdk.list_available_platforms()

    # Example: Working with GitLab (first-class citizen!)

    # Authenticate with GitLab

    # Note: In real usage, you'd get credentials from the secure vault with authenticate_platform("gitlab", gitlab_credentials)

    # Get GitLab capabilities
    sdk.get_platform_capabilities("gitlab")

    # Example GitLab operations (when authenticated): get_project(), list_merge_requests(), get_pipeline_status()

    # Example: Working with GitHub Projects V2 (enhanced support!)

    sdk.get_platform_capabilities("github")

    # Example GitHub operations (when authenticated): list_projects_v2(), get_project_v2_items(), get_repository_insights()

    # Example: Multi-platform workflow

    # In a real scenario, you could:
    # 1. Fetch issues from GitLab
    # 2. Create corresponding GitHub Project items
    # 3. Sync status between platforms
    # 4. Generate unified reports


if __name__ == "__main__":
    asyncio.run(main())
