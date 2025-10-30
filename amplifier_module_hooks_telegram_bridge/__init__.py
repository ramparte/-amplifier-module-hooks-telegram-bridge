"""
Telegram Bridge Hook Module for Amplifier.

Observes session events and pushes formatted notifications to authorized Telegram users.
"""

import logging
from typing import Any

from amplifier_core import ModuleCoordinator

from .hook import TelegramBridgeHook

logger = logging.getLogger(__name__)


async def mount(coordinator: ModuleCoordinator, config: dict[str, Any] | None = None) -> object | None:
    """
    Mount the Telegram bridge hook module.

    Args:
        coordinator: Module coordinator
        config: Hook configuration

    Configuration:
        bot_token (required): Telegram bot token
        pairing_file: Path to pairing.json (default: .amplifier/telegram_pairing.json)
        send_timeout: Timeout for send requests in seconds (default: 5)
        reconnect_interval: Interval for retry loop in seconds (default: 60)
        events: List of events to observe (default: session:start, prompt:submit, etc.)

    Returns:
        Optional cleanup function
    """
    config = config or {}

    # Validate required config
    if "bot_token" not in config:
        logger.error("bot_token is required in Telegram bridge config")
        return None

    try:
        # Create hook instance
        hook = TelegramBridgeHook(config)

        # Get hook registry
        hooks = coordinator.get("hooks")
        if not hooks:
            logger.warning("No hook registry found")
            return None

        # Register for all events the hook wants to observe
        unregister_funcs = []

        for event in hook.events:
            unregister_funcs.append(
                hooks.register(event, hook.handle_event, priority=50, name=f"telegram-bridge-{event}")
            )

        logger.info(f"Mounted TelegramBridgeHook for {len(hook.events)} events")

        # Start reconnect task
        await hook.start_reconnect_task()

        # Return cleanup function
        def cleanup():
            # Unregister hooks
            for unregister in unregister_funcs:
                unregister()

            # Stop reconnect task
            import asyncio

            if asyncio.get_event_loop().is_running():
                asyncio.create_task(hook.stop_reconnect_task())

            logger.info("Cleaned up TelegramBridgeHook")

        return cleanup

    except Exception as e:
        logger.error(f"Failed to mount Telegram bridge hook: {e}")
        return None
