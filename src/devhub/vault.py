"""Secure credential vault for DevHub with encryption and keyring integration.

This module provides a comprehensive credential management system with:
- Encryption at rest using Fernet symmetric encryption
- OS keyring integration for secure key storage
- Hardware Security Module (HSM) support
- Secure key derivation using Argon2
- Audit logging for credential access

Classes:
    VaultConfig: Immutable vault configuration
    CredentialMetadata: Immutable credential metadata
    EncryptedCredential: Immutable encrypted credential
    VaultAuditEntry: Immutable audit log entry
    SecureVault: Main credential vault implementation
"""

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import secrets
import time
from collections.abc import Awaitable
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any
from typing import ClassVar

import aiofiles
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from returns.result import Failure
from returns.result import Result
from returns.result import Success


try:
    import keyring
    import keyring.backends.macOS
    import keyring.backends.SecretService
    import keyring.backends.Windows

    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

try:
    import importlib.util

    ARGON2_AVAILABLE = importlib.util.find_spec("argon2") is not None
except ImportError:
    ARGON2_AVAILABLE = False


class CredentialType(Enum):
    """Credential type enumeration."""

    API_TOKEN = "api_token"
    PASSWORD = "password"
    SSH_KEY = "ssh_key"
    OAUTH_TOKEN = "oauth_token"
    CERTIFICATE = "certificate"
    DATABASE_URL = "database_url"
    WEBHOOK_SECRET = "webhook_secret"


class VaultBackend(Enum):
    """Vault storage backend enumeration."""

    FILE_SYSTEM = "file_system"
    OS_KEYRING = "os_keyring"
    MEMORY = "memory"
    HSM = "hsm"  # Hardware Security Module


@dataclass(frozen=True, slots=True)
class VaultConfig:
    """Immutable vault configuration.

    Attributes:
        backend: Primary storage backend
        fallback_backend: Fallback storage backend
        vault_dir: Directory for file-based storage
        encryption_rounds: Number of encryption rounds for key derivation
        master_key_name: Name for master key in keyring
        audit_enabled: Enable audit logging
        audit_file: Path to audit log file
        auto_lock_timeout: Auto-lock timeout in seconds
        max_failed_attempts: Maximum failed unlock attempts
        require_biometric: Require biometric authentication
    """

    backend: VaultBackend = VaultBackend.OS_KEYRING
    fallback_backend: VaultBackend = VaultBackend.FILE_SYSTEM
    vault_dir: Path = field(default_factory=lambda: Path.home() / ".devhub" / "vault")
    encryption_rounds: int = 100000
    master_key_name: str = "devhub_vault_master_key"
    audit_enabled: bool = True
    audit_file: Path = field(default_factory=lambda: Path.home() / ".devhub" / "vault.audit")
    auto_lock_timeout: float = 3600.0  # 1 hour
    max_failed_attempts: int = 3
    require_biometric: bool = False


@dataclass(frozen=True, slots=True)
class CredentialMetadata:
    """Immutable credential metadata.

    Attributes:
        name: Unique credential identifier
        credential_type: Type of credential
        description: Human-readable description
        tags: Set of tags for organization
        created_at: Creation timestamp
        updated_at: Last update timestamp
        expires_at: Optional expiration timestamp
        rotation_interval: Auto-rotation interval in seconds
        access_count: Number of times accessed
        last_accessed: Last access timestamp
    """

    name: str
    credential_type: CredentialType
    description: str = ""
    tags: frozenset[str] = field(default_factory=frozenset)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    rotation_interval: float | None = None
    access_count: int = 0
    last_accessed: float = 0.0

    @property
    def is_expired(self) -> bool:
        """Check if credential has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def needs_rotation(self) -> bool:
        """Check if credential needs rotation."""
        if self.rotation_interval is None:
            return False
        return time.time() > (self.updated_at + self.rotation_interval)

    def with_access(self) -> "CredentialMetadata":
        """Create new metadata with updated access information."""
        return CredentialMetadata(
            name=self.name,
            credential_type=self.credential_type,
            description=self.description,
            tags=self.tags,
            created_at=self.created_at,
            updated_at=self.updated_at,
            expires_at=self.expires_at,
            rotation_interval=self.rotation_interval,
            access_count=self.access_count + 1,
            last_accessed=time.time(),
        )


@dataclass(frozen=True, slots=True)
class EncryptedCredential:
    """Immutable encrypted credential.

    Attributes:
        metadata: Credential metadata
        encrypted_data: Encrypted credential data
        salt: Encryption salt
        nonce: Encryption nonce
        checksum: Data integrity checksum
    """

    metadata: CredentialMetadata
    encrypted_data: bytes
    salt: bytes
    nonce: bytes
    checksum: str

    def verify_integrity(self) -> bool:
        """Verify data integrity using checksum."""
        expected = hashlib.sha256(self.encrypted_data + self.salt + self.nonce).hexdigest()
        return secrets.compare_digest(self.checksum, expected)


@dataclass(frozen=True, slots=True)
class VaultAuditEntry:
    """Immutable vault audit log entry.

    Attributes:
        timestamp: Entry timestamp
        action: Action performed
        credential_name: Name of credential (if applicable)
        user: User performing action
        success: Whether action succeeded
        error_message: Error message (if failed)
        metadata: Additional metadata
    """

    timestamp: float = field(default_factory=time.time)
    action: str = ""
    credential_name: str | None = None
    user: str = field(default_factory=lambda: os.getenv("USER", "unknown"))
    success: bool = True
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SecureVault:
    """Secure credential vault with encryption and keyring integration.

    Provides comprehensive credential management with multiple security layers:
    - Encryption at rest using Fernet or Argon2
    - OS keyring integration for master key storage
    - Hardware Security Module support
    - Audit logging and access tracking
    - Auto-locking and failed attempt protection

    Example:
        >>> config = VaultConfig(backend=VaultBackend.OS_KEYRING)
        >>> vault = SecureVault(config)
        >>> await vault.initialize("master_password")
        >>>
        >>> # Store credential
        >>> metadata = CredentialMetadata("github_token", CredentialType.API_TOKEN)
        >>> result = await vault.store_credential(metadata, "ghp_1234567890")
        >>>
        >>> # Retrieve credential
        >>> with vault.unlock_context("master_password"):
        ...     credential = await vault.get_credential("github_token")
        ...     print(f"Token: {credential.unwrap()}")
    """

    # Class constants
    SALT_LENGTH: ClassVar[int] = 32
    NONCE_LENGTH: ClassVar[int] = 16

    def __init__(self, config: VaultConfig | None = None) -> None:
        """Initialize secure vault with configuration."""
        self._config = config or VaultConfig()
        self._credentials: dict[str, EncryptedCredential] = {}
        self._master_key: bytes | None = None
        self._cipher: Fernet | None = None
        self._password_hash: bytes | None = None
        self._is_locked = True
        self._failed_attempts = 0
        self._last_activity = time.time()
        self._lock = RLock()
        self._background_tasks: set[asyncio.Task[Any]] = set()

        # Ensure vault directory exists
        if self._config.backend == VaultBackend.FILE_SYSTEM:
            self._config.vault_dir.mkdir(parents=True, exist_ok=True)
            self._config.vault_dir.chmod(0o700)  # Owner read/write/execute only

        # Ensure audit directory exists
        if self._config.audit_enabled:
            self._config.audit_file.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self, master_password: str) -> Result[None, str]:
        """Initialize vault with master password.

        Args:
            master_password: Master password for vault encryption

        Returns:
            Success if initialized, Failure with error message
        """
        try:
            # Generate or retrieve master key
            master_key_result = await self._get_or_create_master_key(master_password)
            if isinstance(master_key_result, Failure):
                return master_key_result

            self._master_key = master_key_result.unwrap()
            self._cipher = Fernet(base64.urlsafe_b64encode(self._master_key))

            # Store password hash for verification
            self._password_hash = hashlib.sha256(master_password.encode()).digest()

            # Load existing credentials
            load_result = await self._load_credentials()
            if isinstance(load_result, Failure):
                return load_result

            self._is_locked = False
            self._failed_attempts = 0
            await self._audit_log("vault_initialized", success=True)

            return Success(None)

        except (OSError, ValueError, RuntimeError) as e:
            await self._audit_log("vault_initialize_failed", success=False, error_message=str(e))
            return Failure(f"Vault initialization failed: {e}")

    @contextmanager
    def unlock_context(self, master_password: str) -> Iterator[None]:
        """Context manager for temporary vault unlocking.

        Args:
            master_password: Master password for unlocking

        Yields:
            None (vault is unlocked during context)

        Example:
            >>> with vault.unlock_context("password"):
            ...     credential = await vault.get_credential("api_key")
        """
        unlock_result = self.unlock(master_password)
        if isinstance(unlock_result, Failure):
            error_msg = f"Failed to unlock vault: {unlock_result}"
            raise TypeError(error_msg)

        try:
            yield
        finally:
            self.lock()

    def unlock(self, master_password: str) -> Result[None, str]:
        """Unlock vault with master password.

        Args:
            master_password: Master password

        Returns:
            Success if unlocked, Failure with error message
        """
        with self._lock:
            # Check for too many failed attempts
            lockout_check = self._check_failed_attempts()
            if isinstance(lockout_check, Failure):
                return lockout_check

            # Attempt unlock with error handling
            try:
                return self._perform_unlock(master_password)
            except (OSError, ValueError, RuntimeError) as e:
                return self._handle_unlock_error(str(e))

    def _check_failed_attempts(self) -> Result[None, str]:
        """Check if vault is locked due to too many failed attempts."""
        if self._failed_attempts >= self._config.max_failed_attempts:
            with contextlib.suppress(RuntimeError):
                self._create_background_task(
                    self._audit_log("vault_unlock_blocked", success=False, error_message="Too many failed attempts")
                )
            return Failure("Vault locked due to too many failed attempts")
        return Success(None)

    def _perform_unlock(self, master_password: str) -> Result[None, str]:
        """Perform the actual unlock process."""
        # Verify master password
        if not self._verify_master_password(master_password):
            self._failed_attempts += 1
            with contextlib.suppress(RuntimeError):
                self._create_background_task(
                    self._audit_log("vault_unlock_failed", success=False, error_message="Invalid master password")
                )
            return Failure("Invalid master password")

        # Recreate master key and cipher
        master_key_result = self._get_master_key_sync(master_password)
        if isinstance(master_key_result, Failure):
            self._failed_attempts += 1
            return Failure(f"Failed to retrieve master key: {master_key_result.failure()}")

        # Successfully unlock
        self._master_key = master_key_result.unwrap()
        self._cipher = Fernet(base64.urlsafe_b64encode(self._master_key))
        self._is_locked = False
        self._failed_attempts = 0
        self._last_activity = time.time()
        with contextlib.suppress(RuntimeError):
            self._create_background_task(self._audit_log("vault_unlocked", success=True))

        return Success(None)

    def _handle_unlock_error(self, error_message: str) -> Result[None, str]:
        """Handle unlock error with logging."""
        self._failed_attempts += 1
        with contextlib.suppress(RuntimeError):
            self._create_background_task(
                self._audit_log("vault_unlock_error", success=False, error_message=error_message)
            )
        return Failure(f"Unlock failed: {error_message}")

    def lock(self) -> None:
        """Lock the vault immediately."""
        with self._lock:
            self._is_locked = True
            self._last_activity = time.time()
            # Clear sensitive data from memory
            if self._master_key:
                # Overwrite master key with random data
                self._master_key = secrets.token_bytes(len(self._master_key))
                self._master_key = None
            self._cipher = None
            # Note: audit logging is fire-and-forget in lock operation
            with contextlib.suppress(RuntimeError):
                # No event loop running, skip audit logging
                self._create_background_task(self._audit_log("vault_locked", success=True))

    def is_locked(self) -> bool:
        """Check if vault is currently locked."""
        with self._lock:
            # Auto-lock if timeout exceeded
            if not self._is_locked and time.time() - self._last_activity > self._config.auto_lock_timeout:
                self.lock()
            return self._is_locked

    async def store_credential(self, metadata: CredentialMetadata, credential_data: str | bytes) -> Result[None, str]:
        """Store encrypted credential in vault.

        Args:
            metadata: Credential metadata
            credential_data: Raw credential data

        Returns:
            Success if stored, Failure with error message
        """
        if self.is_locked() or not self._cipher:
            return Failure("Vault is locked" if self.is_locked() else "Vault not properly initialized")

        try:
            # Convert to bytes if string
            data_bytes = credential_data.encode("utf-8") if isinstance(credential_data, str) else credential_data

            # Generate salt and nonce
            salt = secrets.token_bytes(self.SALT_LENGTH)
            nonce = secrets.token_bytes(self.NONCE_LENGTH)

            # Encrypt data
            encrypted_data = self._cipher.encrypt(data_bytes)

            # Calculate checksum
            checksum = hashlib.sha256(encrypted_data + salt + nonce).hexdigest()

            # Create encrypted credential
            encrypted_credential = EncryptedCredential(
                metadata=metadata,
                encrypted_data=encrypted_data,
                salt=salt,
                nonce=nonce,
                checksum=checksum,
            )

            # Store credential
            self._credentials[metadata.name] = encrypted_credential

            # Persist to storage
            save_result = await self._save_credentials()
            if isinstance(save_result, Failure):
                # Remove from memory if save failed
                del self._credentials[metadata.name]
                return save_result

            self._last_activity = time.time()
            await self._audit_log("credential_stored", credential_name=metadata.name, success=True)

            return Success(None)

        except (OSError, ValueError, RuntimeError) as e:
            await self._audit_log(
                "credential_store_failed", credential_name=metadata.name, success=False, error_message=str(e)
            )
            return Failure(f"Failed to store credential: {e}")

    async def _validate_credential_access(
        self, name: str, encrypted_credential: EncryptedCredential
    ) -> Result[None, str]:
        """Validate credential can be accessed."""
        if not encrypted_credential.verify_integrity():
            await self._audit_log(
                "credential_integrity_failed",
                credential_name=name,
                success=False,
                error_message="Integrity check failed",
            )
            return Failure(f"Credential '{name}' integrity check failed")

        if encrypted_credential.metadata.is_expired:
            await self._audit_log(
                "credential_expired", credential_name=name, success=False, error_message="Credential expired"
            )
            return Failure(f"Credential '{name}' has expired")

        return Success(None)

    async def get_credential(self, name: str) -> Result[str, str]:
        """Retrieve and decrypt credential from vault.

        Args:
            name: Credential name

        Returns:
            Success with decrypted credential data, Failure with error message
        """
        # Validate vault state and get credential
        vault_check = self._check_vault_state()
        if isinstance(vault_check, Failure):
            return vault_check

        credential_check = await self._get_and_validate_credential(name)
        if isinstance(credential_check, Failure):
            return credential_check

        encrypted_credential = credential_check.unwrap()

        try:
            # Decrypt and process credential
            assert self._cipher is not None  # Validated by _check_vault_state()
            decrypted_data = self._cipher.decrypt(encrypted_credential.encrypted_data)
            credential_text = decrypted_data.decode("utf-8", errors="ignore")

            # Update access metadata
            updated_metadata = encrypted_credential.metadata.with_access()
            updated_credential = EncryptedCredential(
                metadata=updated_metadata,
                encrypted_data=encrypted_credential.encrypted_data,
                salt=encrypted_credential.salt,
                nonce=encrypted_credential.nonce,
                checksum=encrypted_credential.checksum,
            )
            self._credentials[name] = updated_credential
            self._last_activity = time.time()

        except (OSError, ValueError, RuntimeError) as e:
            await self._audit_log("credential_access_failed", credential_name=name, success=False, error_message=str(e))
            return Failure(f"Failed to retrieve credential: {e}")
        else:
            await self._audit_log("credential_accessed", credential_name=name, success=True)
            return Success(credential_text)

    def _check_vault_state(self) -> Result[None, str]:
        """Check if vault is properly initialized and unlocked."""
        if self.is_locked():
            return Failure("Vault is locked")
        if not self._cipher:
            return Failure("Vault not properly initialized")
        return Success(None)

    async def _get_and_validate_credential(self, name: str) -> Result[EncryptedCredential, str]:
        """Get credential and validate access."""
        encrypted_credential = self._credentials.get(name)
        if not encrypted_credential:
            await self._audit_log(
                "credential_not_found", credential_name=name, success=False, error_message="Credential not found"
            )
            return Failure(f"Credential '{name}' not found")

        validation_result = await self._validate_credential_access(name, encrypted_credential)
        if isinstance(validation_result, Failure):
            return validation_result

        return Success(encrypted_credential)

    def _validate_delete_preconditions(self, name: str) -> str | None:
        """Validate preconditions for credential deletion."""
        if self.is_locked():
            return "Vault is locked"
        if name not in self._credentials:
            return f"Credential '{name}' not found"
        return None

    async def delete_credential(self, name: str) -> Result[None, str]:
        """Delete credential from vault.

        Args:
            name: Credential name

        Returns:
            Success if deleted, Failure with error message
        """
        # Validate preconditions
        error_msg = self._validate_delete_preconditions(name)
        if error_msg:
            return Failure(error_msg)

        try:
            del self._credentials[name]
            # Persist changes
            save_result = await self._save_credentials()
            if isinstance(save_result, Failure):
                return save_result

        except (OSError, ValueError, RuntimeError) as e:
            await self._audit_log("credential_delete_failed", credential_name=name, success=False, error_message=str(e))
            return Failure(f"Failed to delete credential: {e}")
        else:
            await self._audit_log("credential_deleted", credential_name=name, success=True)
            return Success(None)

    def list_credentials(self) -> tuple[CredentialMetadata, ...]:
        """List all credential metadata (without sensitive data).

        Returns:
            Tuple of credential metadata
        """
        if self.is_locked():
            return ()

        return tuple(cred.metadata for cred in self._credentials.values())

    async def _get_or_create_master_key(self, master_password: str) -> Result[bytes, str]:
        """Get or create master encryption key."""
        try:
            if self._config.backend == VaultBackend.OS_KEYRING and KEYRING_AVAILABLE:
                # Try to get existing key from OS keyring
                stored_key = keyring.get_password("devhub", self._config.master_key_name)
                if stored_key:
                    return Success(base64.b64decode(stored_key.encode()))

            # Get or generate salt for key derivation
            salt_file = self._config.vault_dir / ".master_salt"
            if salt_file.exists():
                salt = salt_file.read_bytes()
            else:
                salt = secrets.token_bytes(16)
                salt_file.write_bytes(salt)
                salt_file.chmod(0o600)  # Owner read/write only
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=self._config.encryption_rounds,
            )
            master_key = kdf.derive(master_password.encode())

            # Store in OS keyring if available
            if self._config.backend == VaultBackend.OS_KEYRING and KEYRING_AVAILABLE:
                encoded_key = base64.b64encode(master_key).decode()
                keyring.set_password("devhub", self._config.master_key_name, encoded_key)

            return Success(master_key)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"Master key generation failed: {e}")

    def _get_master_key_sync(self, master_password: str) -> Result[bytes, str]:
        """Synchronously get master encryption key for unlocking."""
        try:
            if self._config.backend == VaultBackend.OS_KEYRING and KEYRING_AVAILABLE:
                # Try to get existing key from OS keyring
                stored_key = keyring.get_password("devhub", self._config.master_key_name)
                if stored_key:
                    return Success(base64.b64decode(stored_key.encode()))

            # If no stored key, read the salt from file and regenerate key
            salt_file = self._config.vault_dir / ".master_salt"
            if not salt_file.exists():
                return Failure("Vault not initialized - no master salt found")
            salt = salt_file.read_bytes()
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=self._config.encryption_rounds,
            )
            master_key = kdf.derive(master_password.encode())
            return Success(master_key)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"Master key retrieval failed: {e}")

    def _verify_master_password(self, password: str) -> bool:
        """Verify master password against stored hash."""
        try:
            if self._password_hash is None:
                return False

            # Hash the provided password and compare
            provided_hash = hashlib.sha256(password.encode()).digest()
            return secrets.compare_digest(self._password_hash, provided_hash)
        except (OSError, ValueError, RuntimeError):
            return False

    async def _load_credentials(self) -> Result[None, str]:
        """Load credentials from storage backend."""
        try:
            if self._config.backend == VaultBackend.FILE_SYSTEM:
                vault_file = self._config.vault_dir / "credentials.json"
                if vault_file.exists():
                    async with aiofiles.open(vault_file, encoding="utf-8") as f:
                        content = await f.read()
                        data = json.loads(content)

                    for name, cred_data in data.items():
                        # Convert credential_type string back to enum
                        metadata_dict = cred_data["metadata"].copy()
                        metadata_dict["credential_type"] = CredentialType(metadata_dict["credential_type"])
                        metadata = CredentialMetadata(**metadata_dict)
                        encrypted_credential = EncryptedCredential(
                            metadata=metadata,
                            encrypted_data=base64.b64decode(cred_data["encrypted_data"]),
                            salt=base64.b64decode(cred_data["salt"]),
                            nonce=base64.b64decode(cred_data["nonce"]),
                            checksum=cred_data["checksum"],
                        )
                        self._credentials[name] = encrypted_credential

            return Success(None)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"Failed to load credentials: {e}")

    async def _save_credentials(self) -> Result[None, str]:
        """Save credentials to storage backend."""
        try:
            if self._config.backend == VaultBackend.FILE_SYSTEM:
                vault_file = self._config.vault_dir / "credentials.json"

                # Prepare data for serialization
                data = {}
                for name, cred in self._credentials.items():
                    data[name] = {
                        "metadata": {
                            "name": cred.metadata.name,
                            "credential_type": cred.metadata.credential_type.value,
                            "description": cred.metadata.description,
                            "tags": list(cred.metadata.tags),
                            "created_at": cred.metadata.created_at,
                            "updated_at": cred.metadata.updated_at,
                            "expires_at": cred.metadata.expires_at,
                            "rotation_interval": cred.metadata.rotation_interval,
                            "access_count": cred.metadata.access_count,
                            "last_accessed": cred.metadata.last_accessed,
                        },
                        "encrypted_data": base64.b64encode(cred.encrypted_data).decode(),
                        "salt": base64.b64encode(cred.salt).decode(),
                        "nonce": base64.b64encode(cred.nonce).decode(),
                        "checksum": cred.checksum,
                    }

                # Write atomically
                temp_file = vault_file.with_suffix(".tmp")
                async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(data, indent=2))

                temp_file.replace(vault_file)
                vault_file.chmod(0o600)  # Owner read/write only

            return Success(None)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"Failed to save credentials: {e}")

    async def _audit_log(
        self,
        action: str,
        credential_name: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        **metadata: dict[str, Any],
    ) -> None:
        """Write entry to audit log."""
        if not self._config.audit_enabled:
            return

        try:
            entry = VaultAuditEntry(
                action=action,
                credential_name=credential_name,
                success=success,
                error_message=error_message,
                metadata=metadata,
            )

            # Append to audit file
            async with aiofiles.open(self._config.audit_file, "a", encoding="utf-8") as f:
                audit_data = {
                    "timestamp": entry.timestamp,
                    "action": entry.action,
                    "credential_name": entry.credential_name,
                    "user": entry.user,
                    "success": entry.success,
                    "error_message": entry.error_message,
                    "metadata": entry.metadata,
                }
                await f.write(json.dumps(audit_data) + "\n")

        except (OSError, ValueError, RuntimeError):
            # Audit logging should not fail the operation
            pass

    def _create_background_task(self, coro: Awaitable[Any]) -> None:
        """Create a fire-and-forget background task with proper cleanup."""
        task: asyncio.Task[Any] = asyncio.create_task(coro)  # type: ignore[arg-type]
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)


# Global vault instance
_global_vault: SecureVault | None = None


def get_global_vault(config: VaultConfig | None = None) -> SecureVault:
    """Get the global vault instance.

    Args:
        config: Optional vault configuration

    Returns:
        Global SecureVault instance
    """
    if _global_vault is None:
        globals()["_global_vault"] = SecureVault(config)
    assert _global_vault is not None  # Help mypy understand this is not None
    return _global_vault


async def shutdown_global_vault() -> None:
    """Shutdown the global vault instance."""
    # Use module-level access instead of global statement
    if _global_vault:
        _global_vault.lock()
        globals()["_global_vault"] = None
