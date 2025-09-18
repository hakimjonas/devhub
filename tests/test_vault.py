"""Comprehensive tests for the secure credential vault system."""

import json
import tempfile
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from hypothesis import HealthCheck
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st
from returns.result import Failure
from returns.result import Success

from devhub.vault import CredentialMetadata
from devhub.vault import CredentialType
from devhub.vault import EncryptedCredential
from devhub.vault import SecureVault
from devhub.vault import VaultAuditEntry
from devhub.vault import VaultBackend
from devhub.vault import VaultConfig
from devhub.vault import get_global_vault
from devhub.vault import shutdown_global_vault


class TestVaultConfig:
    """Test vault configuration."""

    def test_default_config(self) -> None:
        """Test default vault configuration."""
        config = VaultConfig()
        assert config.backend == VaultBackend.OS_KEYRING
        assert config.fallback_backend == VaultBackend.FILE_SYSTEM
        assert config.encryption_rounds == 100000
        assert config.audit_enabled is True
        assert config.auto_lock_timeout == 3600.0
        assert config.max_failed_attempts == 3

    def test_custom_config(self) -> None:
        """Test custom vault configuration."""
        custom_dir = Path("/tmp/test_vault")
        config = VaultConfig(
            backend=VaultBackend.FILE_SYSTEM,
            vault_dir=custom_dir,
            encryption_rounds=50000,
            auto_lock_timeout=1800.0,
        )
        assert config.backend == VaultBackend.FILE_SYSTEM
        assert config.vault_dir == custom_dir
        assert config.encryption_rounds == 50000
        assert config.auto_lock_timeout == 1800.0


class TestCredentialMetadata:
    """Test credential metadata."""

    def test_metadata_creation(self) -> None:
        """Test credential metadata creation."""
        metadata = CredentialMetadata(
            name="test_token",
            credential_type=CredentialType.API_TOKEN,
            description="Test API token",
            tags=frozenset({"api", "test"}),
        )
        assert metadata.name == "test_token"
        assert metadata.credential_type == CredentialType.API_TOKEN
        assert metadata.description == "Test API token"
        assert "api" in metadata.tags
        assert "test" in metadata.tags
        assert not metadata.is_expired
        assert not metadata.needs_rotation

    def test_expiration_check(self) -> None:
        """Test credential expiration check."""
        # Not expired
        metadata = CredentialMetadata(
            name="test",
            credential_type=CredentialType.API_TOKEN,
            expires_at=time.time() + 3600,  # 1 hour from now
        )
        assert not metadata.is_expired

        # Expired
        metadata = CredentialMetadata(
            name="test",
            credential_type=CredentialType.API_TOKEN,
            expires_at=time.time() - 3600,  # 1 hour ago
        )
        assert metadata.is_expired

    def test_rotation_check(self) -> None:
        """Test credential rotation check."""
        # No rotation needed
        metadata = CredentialMetadata(
            name="test",
            credential_type=CredentialType.API_TOKEN,
            rotation_interval=3600,  # 1 hour
            updated_at=time.time(),  # Just updated
        )
        assert not metadata.needs_rotation

        # Needs rotation
        metadata = CredentialMetadata(
            name="test",
            credential_type=CredentialType.API_TOKEN,
            rotation_interval=3600,  # 1 hour
            updated_at=time.time() - 7200,  # 2 hours ago
        )
        assert metadata.needs_rotation

    def test_access_tracking(self) -> None:
        """Test access tracking functionality."""
        metadata = CredentialMetadata(
            name="test",
            credential_type=CredentialType.API_TOKEN,
            access_count=5,
        )

        updated = metadata.with_access()
        assert updated.access_count == 6
        assert updated.last_accessed > metadata.last_accessed
        assert updated.name == metadata.name  # Other fields unchanged

    @given(
        name=st.text(min_size=1, max_size=100),
        description=st.text(max_size=500),
        tags=st.frozensets(st.text(min_size=1, max_size=20), max_size=10),
    )
    def test_metadata_property_invariants(
        self,
        name: str,
        description: str,
        tags: frozenset[str],
    ) -> None:
        """Test metadata property invariants with random data."""
        metadata = CredentialMetadata(
            name=name,
            credential_type=CredentialType.API_TOKEN,
            description=description,
            tags=tags,
        )

        # Basic invariants
        assert metadata.name == name
        assert metadata.description == description
        assert metadata.tags == tags
        assert metadata.access_count >= 0
        assert metadata.created_at <= time.time()


class TestEncryptedCredential:
    """Test encrypted credential."""

    def test_integrity_verification(self) -> None:
        """Test data integrity verification."""
        import hashlib
        import secrets

        metadata = CredentialMetadata("test", CredentialType.API_TOKEN)
        encrypted_data = b"encrypted_content"
        salt = secrets.token_bytes(32)
        nonce = secrets.token_bytes(16)
        checksum = hashlib.sha256(encrypted_data + salt + nonce).hexdigest()

        credential = EncryptedCredential(
            metadata=metadata,
            encrypted_data=encrypted_data,
            salt=salt,
            nonce=nonce,
            checksum=checksum,
        )

        assert credential.verify_integrity() is True

        # Test with corrupted data
        corrupted_credential = EncryptedCredential(
            metadata=metadata,
            encrypted_data=b"corrupted_data",
            salt=salt,
            nonce=nonce,
            checksum=checksum,
        )

        assert corrupted_credential.verify_integrity() is False


class TestVaultAuditEntry:
    """Test vault audit entry."""

    def test_audit_entry_creation(self) -> None:
        """Test audit entry creation."""
        entry = VaultAuditEntry(
            action="credential_accessed",
            credential_name="test_token",
            success=True,
        )

        assert entry.action == "credential_accessed"
        assert entry.credential_name == "test_token"
        assert entry.success is True
        assert entry.timestamp <= time.time()

    def test_audit_entry_with_error(self) -> None:
        """Test audit entry with error information."""
        entry = VaultAuditEntry(
            action="credential_store_failed",
            credential_name="test_token",
            success=False,
            error_message="Encryption failed",
            metadata={"attempt": 1},
        )

        assert entry.success is False
        assert entry.error_message == "Encryption failed"
        assert entry.metadata["attempt"] == 1


# Module-level fixtures for all test classes
@pytest.fixture
def temp_vault_dir() -> Generator[Path]:
    """Create temporary vault directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def vault_config(temp_vault_dir: Path) -> VaultConfig:
    """Create test vault configuration."""
    return VaultConfig(
        backend=VaultBackend.FILE_SYSTEM,
        vault_dir=temp_vault_dir,
        audit_file=temp_vault_dir / "audit.log",
        audit_enabled=False,  # Disable audit to prevent background task issues
        auto_lock_timeout=1.0,  # 1 second for testing
    )


@pytest.fixture
def vault(vault_config: VaultConfig) -> SecureVault:
    """Create test vault instance."""
    return SecureVault(vault_config)


@pytest.fixture
def vault_with_audit(temp_vault_dir: Path) -> SecureVault:
    """Create test vault instance with audit enabled."""
    config = VaultConfig(
        backend=VaultBackend.FILE_SYSTEM,
        vault_dir=temp_vault_dir,
        audit_file=temp_vault_dir / "audit.log",
        audit_enabled=True,  # Enable audit for specific tests
        auto_lock_timeout=1.0,  # 1 second for testing
    )
    return SecureVault(config)


class TestSecureVault:
    """Test secure vault functionality."""

    @pytest.mark.asyncio
    async def test_vault_initialization(self, vault: SecureVault) -> None:
        """Test vault initialization."""
        result = await vault.initialize("test_password")
        assert isinstance(result, Success)
        assert not vault.is_locked()

    @pytest.mark.asyncio
    async def test_vault_lock_unlock(self, vault: SecureVault) -> None:
        """Test vault locking and unlocking."""
        await vault.initialize("test_password")

        # Lock vault
        vault.lock()
        assert vault.is_locked()

        # Unlock vault
        result = vault.unlock("test_password")
        assert isinstance(result, Success)
        assert not vault.is_locked()

        # Test wrong password
        vault.lock()
        result = vault.unlock("wrong_password")
        assert isinstance(result, Failure)
        assert vault.is_locked()

    @pytest.mark.asyncio
    async def test_auto_lock(self, vault: SecureVault) -> None:
        """Test automatic vault locking."""
        await vault.initialize("test_password")
        assert not vault.is_locked()

        # Mock time to advance past auto-lock timeout deterministically
        from unittest.mock import patch

        # Patch time in the vault module to control auto-lock timing
        with patch("devhub.vault.time.time") as mock_time:
            # Return a time that exceeds the auto-lock timeout
            mock_time.return_value = vault._last_activity + vault._config.auto_lock_timeout + 0.1

            # Trigger auto-lock check by calling is_locked()
            assert vault.is_locked()

    @pytest.mark.asyncio
    async def test_failed_attempts_lockout(self, vault: SecureVault) -> None:
        """Test failed attempts lockout."""
        await vault.initialize("test_password")
        vault.lock()

        # Make multiple failed attempts
        for _ in range(3):
            result = vault.unlock("wrong_password")
            assert isinstance(result, Failure)

        # Should be locked out now
        result = vault.unlock("test_password")  # Even correct password fails
        assert isinstance(result, Failure)
        assert "too many failed attempts" in str(result).lower()

    @pytest.mark.asyncio
    async def test_store_and_retrieve_credential(self, vault: SecureVault) -> None:
        """Test storing and retrieving credentials."""
        await vault.initialize("test_password")

        metadata = CredentialMetadata(
            name="github_token",
            credential_type=CredentialType.API_TOKEN,
            description="GitHub API token",
        )

        # Store credential
        result = await vault.store_credential(metadata, "ghp_1234567890")
        assert isinstance(result, Success)

        # Retrieve credential
        get_result = await vault.get_credential("github_token")
        assert isinstance(get_result, Success)
        assert get_result.unwrap() == "ghp_1234567890"

    @pytest.mark.asyncio
    async def test_credential_not_found(self, vault: SecureVault) -> None:
        """Test retrieving non-existent credential."""
        await vault.initialize("test_password")

        result = await vault.get_credential("nonexistent")
        assert isinstance(result, Failure)
        assert "not found" in str(result).lower()

    @pytest.mark.asyncio
    async def test_expired_credential(self, vault: SecureVault) -> None:
        """Test retrieving expired credential."""
        await vault.initialize("test_password")

        metadata = CredentialMetadata(
            name="expired_token",
            credential_type=CredentialType.API_TOKEN,
            expires_at=time.time() - 3600,  # Expired 1 hour ago
        )

        await vault.store_credential(metadata, "expired_token_value")

        result = await vault.get_credential("expired_token")
        assert isinstance(result, Failure)
        assert "expired" in str(result).lower()

    @pytest.mark.asyncio
    async def test_delete_credential(self, vault: SecureVault) -> None:
        """Test deleting credentials."""
        await vault.initialize("test_password")

        metadata = CredentialMetadata("test_token", CredentialType.API_TOKEN)
        await vault.store_credential(metadata, "token_value")

        # Verify it exists
        result = await vault.get_credential("test_token")
        assert isinstance(result, Success)

        # Delete it
        delete_result = await vault.delete_credential("test_token")
        assert isinstance(delete_result, Success)

        # Verify it's gone
        result = await vault.get_credential("test_token")
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_list_credentials(self, vault: SecureVault) -> None:
        """Test listing credential metadata."""
        await vault.initialize("test_password")

        # Store multiple credentials
        for i in range(3):
            metadata = CredentialMetadata(
                f"token_{i}",
                CredentialType.API_TOKEN,
                description=f"Test token {i}",
            )
            await vault.store_credential(metadata, f"value_{i}")

        # List credentials
        credentials = vault.list_credentials()
        assert len(credentials) == 3
        assert all(cred.name.startswith("token_") for cred in credentials)

        # Lock vault and verify empty list
        vault.lock()
        credentials = vault.list_credentials()
        assert len(credentials) == 0

    @pytest.mark.asyncio
    async def test_locked_vault_operations(self, vault: SecureVault) -> None:
        """Test operations on locked vault."""
        await vault.initialize("test_password")
        vault.lock()

        metadata = CredentialMetadata("test", CredentialType.API_TOKEN)

        # All operations should fail on locked vault
        result = await vault.store_credential(metadata, "value")
        assert isinstance(result, Failure)
        assert "locked" in str(result).lower()

        get_result = await vault.get_credential("test")
        assert isinstance(get_result, Failure)
        assert "locked" in str(get_result).lower()

        result = await vault.delete_credential("test")
        assert isinstance(result, Failure)
        assert "locked" in str(result).lower()

    @pytest.mark.asyncio
    async def test_unlock_context_manager(self, vault: SecureVault) -> None:
        """Test unlock context manager."""
        await vault.initialize("test_password")
        vault.lock()

        metadata = CredentialMetadata("test", CredentialType.API_TOKEN)

        # Use context manager
        with vault.unlock_context("test_password"):
            assert not vault.is_locked()
            await vault.store_credential(metadata, "value")
            result = await vault.get_credential("test")
            assert isinstance(result, Success)

        # Should be locked again after context
        assert vault.is_locked()

    @pytest.mark.asyncio
    async def test_persistence(self, vault: SecureVault, temp_vault_dir: Path) -> None:
        """Test credential persistence across vault instances."""
        await vault.initialize("test_password")

        metadata = CredentialMetadata("persistent_token", CredentialType.API_TOKEN)
        await vault.store_credential(metadata, "persistent_value")

        # Create new vault instance with same config
        config = VaultConfig(
            backend=VaultBackend.FILE_SYSTEM,
            vault_dir=temp_vault_dir,
        )
        new_vault = SecureVault(config)
        await new_vault.initialize("test_password")

        # Should be able to retrieve stored credential
        result = await new_vault.get_credential("persistent_token")
        assert isinstance(result, Success)
        assert result.unwrap() == "persistent_value"

    @pytest.mark.asyncio
    async def test_audit_logging(self, vault_with_audit: SecureVault, temp_vault_dir: Path) -> None:
        """Test audit logging functionality."""
        await vault_with_audit.initialize("test_password")

        metadata = CredentialMetadata("audit_test", CredentialType.API_TOKEN)
        await vault_with_audit.store_credential(metadata, "audit_value")
        await vault_with_audit.get_credential("audit_test")
        await vault_with_audit.delete_credential("audit_test")

        # Check audit file
        audit_file = temp_vault_dir / "audit.log"
        assert audit_file.exists()

        with audit_file.open(encoding="utf-8") as f:
            audit_lines = f.readlines()

        assert len(audit_lines) >= 4  # init, store, get, delete

        # Parse and verify audit entries
        for line in audit_lines:
            entry = json.loads(line.strip())
            assert "timestamp" in entry
            assert "action" in entry
            assert "success" in entry

    @pytest.mark.asyncio
    async def test_access_tracking(self, vault: SecureVault) -> None:
        """Test credential access tracking."""
        await vault.initialize("test_password")

        metadata = CredentialMetadata("tracked_token", CredentialType.API_TOKEN)
        await vault.store_credential(metadata, "tracked_value")

        # Access multiple times
        for _ in range(3):
            await vault.get_credential("tracked_token")

        # Check access count
        credentials = vault.list_credentials()
        tracked_cred = next(c for c in credentials if c.name == "tracked_token")
        assert tracked_cred.access_count == 3
        assert tracked_cred.last_accessed > 0

    @given(
        credential_name=st.text(min_size=1, max_size=50),
        credential_value=st.text(min_size=1, max_size=1000),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_credential_roundtrip_property(
        self,
        vault: SecureVault,
        credential_name: str,
        credential_value: str,
    ) -> None:
        """Property test for credential storage/retrieval roundtrip."""
        await vault.initialize("test_password")

        metadata = CredentialMetadata(credential_name, CredentialType.API_TOKEN)

        # Store credential
        store_result = await vault.store_credential(metadata, credential_value)
        assert isinstance(store_result, Success)

        # Retrieve credential
        get_result = await vault.get_credential(credential_name)
        assert isinstance(get_result, Success)
        assert get_result.unwrap() == credential_value

    @pytest.mark.asyncio
    async def test_binary_credential_data(self, vault: SecureVault) -> None:
        """Test storing binary credential data."""
        await vault.initialize("test_password")

        # Test with binary data
        binary_data = b"\x00\x01\x02\x03\xff\xfe\xfd"
        metadata = CredentialMetadata("binary_cred", CredentialType.CERTIFICATE)

        result = await vault.store_credential(metadata, binary_data)
        assert isinstance(result, Success)

        # Retrieve as binary (should be returned as string though)
        get_result = await vault.get_credential("binary_cred")
        assert isinstance(get_result, Success)
        # Binary data gets encoded as string during storage
        assert get_result.unwrap() == binary_data.decode("utf-8", errors="ignore")


class TestGlobalVault:
    """Test global vault functionality."""

    def test_global_vault_singleton(self) -> None:
        """Test global vault singleton behavior."""
        vault1 = get_global_vault()
        vault2 = get_global_vault()
        assert vault1 is vault2

    @pytest.mark.asyncio
    async def test_global_vault_shutdown(self) -> None:
        """Test global vault shutdown."""
        vault = get_global_vault()
        await vault.initialize("test_password")

        await shutdown_global_vault()
        assert vault.is_locked()

        # New instance after shutdown
        new_vault = get_global_vault()
        assert new_vault is not vault


class TestVaultIntegration:
    """Integration tests for vault system."""

    @pytest.mark.asyncio
    async def test_multiple_credential_types(self, vault: SecureVault) -> None:
        """Test storing different types of credentials."""
        await vault.initialize("test_password")

        credentials = [
            (CredentialMetadata("api_key", CredentialType.API_TOKEN), "sk-1234567890"),
            (CredentialMetadata("db_password", CredentialType.PASSWORD), "super_secret_password"),
            (CredentialMetadata("ssh_key", CredentialType.SSH_KEY), "-----BEGIN PRIVATE KEY-----"),
            (CredentialMetadata("oauth_token", CredentialType.OAUTH_TOKEN), "oauth2_bearer_token"),
        ]

        # Store all credentials
        for metadata, value in credentials:
            result = await vault.store_credential(metadata, value)
            assert isinstance(result, Success)

        # Retrieve all credentials
        for metadata, expected_value in credentials:
            get_result = await vault.get_credential(metadata.name)
            assert isinstance(get_result, Success)
            assert get_result.unwrap() == expected_value

    @pytest.mark.asyncio
    async def test_concurrent_access_simulation(self, vault: SecureVault) -> None:
        """Test simulated concurrent access patterns."""
        await vault.initialize("test_password")

        # Store a credential
        metadata = CredentialMetadata("concurrent_test", CredentialType.API_TOKEN)
        await vault.store_credential(metadata, "concurrent_value")

        # Simulate multiple rapid accesses
        results = []
        for _ in range(10):
            result = await vault.get_credential("concurrent_test")
            results.append(result)

        # All should succeed
        assert all(isinstance(r, Success) for r in results)
        assert all(r.unwrap() == "concurrent_value" for r in results)

        # Check access count
        credentials = vault.list_credentials()
        test_cred = next(c for c in credentials if c.name == "concurrent_test")
        assert test_cred.access_count == 10
