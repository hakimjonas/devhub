"""Additional tests for devhub.sdk branches and async client flows."""

from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from returns.result import Failure
from returns.result import Success

from devhub.main import Repository
from devhub.sdk import ContextRequest
from devhub.sdk import DevHubAsyncClient
from devhub.sdk import DevHubClient


@pytest.mark.asyncio
async def test_execute_cli_command_keyboard_interrupt():
    client = DevHubClient()
    with patch("asyncio.create_subprocess_exec") as mock_create, patch("asyncio.wait_for") as mock_wait:
        mock_create.return_value = AsyncMock()
        mock_wait.side_effect = KeyboardInterrupt()
        res = await client.execute_cli_command(["bundle"])
        assert isinstance(res, Failure)
        assert "interrupted" in res.failure().lower()


@pytest.mark.asyncio
async def test_process_result_invalid_json():
    client = DevHubClient()
    repo = Repository(owner="o", name="n")
    req = ContextRequest()
    res = client._process_result("not-json", repo, "b", req)
    assert isinstance(res, Failure)
    assert "Invalid JSON" in res.failure()


@pytest.mark.asyncio
async def test_async_client_context_and_multiple():
    # Ensure initialize succeeds quickly
    with (
        patch.object(DevHubClient, "initialize", AsyncMock(return_value=Success(None))),
        patch.object(DevHubClient, "get_bundle_context", AsyncMock(side_effect=[Success("A"), Failure("E")])),
    ):
        async with DevHubAsyncClient() as ac:
            results = await ac.get_multiple_contexts([ContextRequest(), ContextRequest()])
            assert len(results) == 2
            assert isinstance(results[0], Success)
            assert isinstance(results[1], Failure)
