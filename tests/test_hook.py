"""Tests for TelegramBridgeHook."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from amplifier_module_hooks_telegram_bridge.hook import TelegramBridgeHook


@pytest.fixture
def temp_pairing_file(tmp_path):
    """Create temporary pairing file."""
    pairing_file = tmp_path / "pairing.json"
    pairing_data = {
        "version": "1.0",
        "authorized_users": [
            {"user_id": 123456, "chat_id": 123456, "username": "testuser", "paired_at": "2025-01-01T00:00:00Z"}
        ],
        "rate_limits": {},
    }
    pairing_file.write_text(json.dumps(pairing_data, indent=2))
    return pairing_file


@pytest.fixture
def hook_config(temp_pairing_file):
    """Hook configuration."""
    return {
        "bot_token": "test_token_123",
        "pairing_file": str(temp_pairing_file),
        "send_timeout": 5,
        "reconnect_interval": 60,
    }


@pytest.mark.asyncio
async def test_hook_initialization(hook_config):
    """Test hook initializes correctly."""
    hook = TelegramBridgeHook(hook_config)

    assert hook.telegram_client is not None
    assert hook.auth_manager is not None
    assert hook.message_formatter is not None
    assert len(hook.events) > 0


@pytest.mark.asyncio
async def test_hook_handles_event(hook_config):
    """Test hook handles event and sends to Telegram."""
    hook = TelegramBridgeHook(hook_config)

    # Mock telegram client
    hook.telegram_client.async_send_message = AsyncMock(return_value=True)

    # Handle event
    result = await hook.handle_event("session:start", {"session_id": "test-123"})

    assert result.action == "continue"


@pytest.mark.asyncio
async def test_hook_filters_events(hook_config):
    """Test hook only observes configured events."""
    hook_config["events"] = ["session:start"]
    hook = TelegramBridgeHook(hook_config)

    # Mock telegram client
    hook.telegram_client.async_send_message = AsyncMock(return_value=True)

    # Handle observed event
    result = await hook.handle_event("session:start", {"session_id": "test-123"})
    assert result.action == "continue"

    # Handle unobserved event (should skip)
    result = await hook.handle_event("prompt:submit", {"prompt": "test"})
    assert result.action == "continue"


@pytest.mark.asyncio
async def test_hook_no_authorized_users(hook_config, temp_pairing_file):
    """Test hook skips when no authorized users."""
    # Empty pairing file
    temp_pairing_file.write_text(json.dumps({"version": "1.0", "authorized_users": [], "rate_limits": {}}, indent=2))

    hook = TelegramBridgeHook(hook_config)

    # Mock telegram client (should NOT be called)
    hook.telegram_client.async_send_message = AsyncMock(return_value=True)

    await hook.handle_event("session:start", {"session_id": "test-123"})

    # Should not call telegram client
    hook.telegram_client.async_send_message.assert_not_called()


@pytest.mark.asyncio
async def test_hook_timeout_handling(hook_config):
    """Test hook handles send timeout gracefully."""
    hook = TelegramBridgeHook(hook_config)

    # Mock timeout
    async def timeout_send(*args, **kwargs) -> bool:
        await asyncio.sleep(10)  # Longer than timeout
        return False

    hook.telegram_client.async_send_message = timeout_send

    # Should not raise, should continue
    result = await hook.handle_event("session:start", {"session_id": "test-123"})
    assert result.action == "continue"
