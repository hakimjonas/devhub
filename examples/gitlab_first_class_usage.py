"""Example demonstrating GitLab as a first-class citizen in DevHub.

This example shows how GitLab receives the same level of support as GitHub,
with no preferential treatment for any platform.
"""

import asyncio

from devhub.gitlab_integration import get_gitlab_client
from devhub.platform_sdk import get_platform_sdk
from devhub.plugins import get_global_registry
from devhub.sdk import DevHubClient
from devhub.vault import CredentialMetadata
from devhub.vault import CredentialType
from devhub.vault import SecureVault
from devhub.vault import VaultConfig


async def demonstrate_gitlab_first_class() -> None:
    """Demonstrate GitLab as a first-class platform."""
    # 1. Direct GitLab API Client (same quality as GitHub)

    await get_gitlab_client("https://gitlab.com")

    # In practice, you'd set a real token with set_token("your-gitlab-token")

    # 2. Secure Credential Management

    # Set up secure vault for GitLab credentials
    vault_config = VaultConfig()
    SecureVault(vault_config)

    # Initialize vault (in practice, use a real password) with initialize("your-master-password")

    # Store GitLab token securely (in practice)
    CredentialMetadata(
        name="gitlab_token",
        credential_type=CredentialType.API_TOKEN,
        description="GitLab API token for project access",
        tags=frozenset({"gitlab", "api", "development"}),
    )

    # Store token with store_credential(gitlab_metadata, "your-gitlab-token")

    # 3. Plugin System Integration

    get_global_registry()

    # GitLab plugin provides same capabilities as GitHub

    # 4. Platform-Agnostic SDK Usage

    platform_sdk = get_platform_sdk()

    # Get GitLab capabilities (same interface as GitHub)
    platform_sdk.get_platform_capabilities("gitlab")

    # Same workflow works for GitLab or GitHub

    # 5. DevHub Context Bundling with GitLab

    # DevHub SDK automatically detects GitLab projects
    DevHubClient()

    # In practice, this would work in a GitLab repository

    # 6. Multi-Platform Workflow Example

    # 7. Company Migration Support

    migration_benefits = [
        "✅ Zero code changes needed for GitLab migration",
        "✅ Same DevHub commands work with GitLab",
        "✅ Secure credential migration tools",
        "✅ Gradual migration with multi-platform support",
        "✅ Full feature parity between platforms",
        "✅ Team training minimal (same interface)",
    ]

    for _benefit in migration_benefits:
        pass


async def gitlab_real_world_example() -> None:
    """Real-world GitLab integration example."""
    # Example: Getting merge request context for code review
    await get_gitlab_client()

    # In a real scenario:


if __name__ == "__main__":
    asyncio.run(demonstrate_gitlab_first_class())
    asyncio.run(gitlab_real_world_example())
