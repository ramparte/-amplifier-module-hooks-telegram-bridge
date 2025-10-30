"""
Telegram Bridge Hook - observes Amplifier events and pushes to Telegram.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from amplifier_core import HookRegistry
from amplifier_core import HookResult

from .auth_manager import AuthManager
from .message_formatter import MessageFormatter
from .telegram_client import TelegramClient

logger = logging.getLogger(__name__)


class TelegramBridgeHook:
    """Hook that bridges Amplifier events to Telegram."""

    # Default events to observe
    DEFAULT_EVENTS = [
        HookRegistry.SESSION_START,
        HookRegistry.PROMPT_SUBMIT,
        HookRegistry.PROMPT_COMPLETE,
        HookRegistry.PROVIDER_REQUEST,
        HookRegistry.PROVIDER_RESPONSE,
        HookRegistry.TOOL_POST,
    ]

    def __init__(self, config: dict[str, Any]):
        """
        Initialize Telegram bridge hook.

        Args:
            config: Hook configuration
        """
        self.config = config

        # Required config
        bot_token = config.get("bot_token")
        if not bot_token:
            raise ValueError("bot_token is required in config")

        # Initialize components
        pairing_file = Path(config.get("pairing_file", ".amplifier/telegram_pairing.json"))
        self.auth_manager = AuthManager(pairing_file)

        send_timeout = config.get("send_timeout", 5)
        reconnect_interval = config.get("reconnect_interval", 60)

        self.telegram_client = TelegramClient(bot_token=bot_token, send_timeout=send_timeout)

        self.message_formatter = MessageFormatter()

        # Events to observe
        self.events = set(config.get("events", self.DEFAULT_EVENTS))

        # Reconnection
        self.reconnect_interval = reconnect_interval
        self._reconnect_task: asyncio.Task | None = None

    async def start_reconnect_task(self) -> None:
        """Start background task to retry queued messages."""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
            logger.info("Started reconnect task")

    async def stop_reconnect_task(self) -> None:
        """Stop background reconnect task."""
        import contextlib

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
            logger.info("Stopped reconnect task")

    async def _reconnect_loop(self) -> None:
        """Background loop to retry queued messages."""
        while True:
            try:
                await asyncio.sleep(self.reconnect_interval)

                queue_status = self.telegram_client.get_queue_status()
                if queue_status["queued_messages"] > 0:
                    logger.info(f"Retrying {queue_status['queued_messages']} queued messages...")

                    # Run retry in executor (sync function)
                    loop = asyncio.get_event_loop()
                    sent_count = await loop.run_in_executor(None, self.telegram_client.retry_queue)

                    if sent_count > 0:
                        logger.info(f"Successfully sent {sent_count} queued messages")

            except asyncio.CancelledError:
                logger.info("Reconnect loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Error in reconnect loop: {e}")

    async def handle_event(self, event: str, data: dict[str, Any]) -> HookResult:
        """
        Handle Amplifier event and push to Telegram.

        Args:
            event: Event name
            data: Event data

        Returns:
            HookResult
        """
        # Check if we should observe this event
        if event not in self.events:
            return HookResult(action="continue")

        try:
            # Get authorized chat IDs
            chat_ids = self.auth_manager.get_chat_ids()

            if not chat_ids:
                logger.debug(f"No authorized users, skipping event {event}")
                return HookResult(action="continue")

            # Format message
            message_chunks = self.message_formatter.format_event(event, data)

            # Send to all authorized chats
            for chat_id in chat_ids:
                for chunk in message_chunks:
                    # Non-blocking send with timeout
                    try:
                        success = await asyncio.wait_for(
                            self.telegram_client.async_send_message(chat_id, chunk),
                            timeout=self.config.get("send_timeout", 5),
                        )

                        if success:
                            logger.debug(f"Sent event {event} to chat {chat_id}")
                        else:
                            logger.warning(f"Failed to send event {event} to chat {chat_id} (queued for retry)")

                    except TimeoutError:
                        logger.warning(f"Timeout sending event {event} to chat {chat_id}")
                    except Exception as e:
                        logger.error(f"Error sending to chat {chat_id}: {e}")

            return HookResult(action="continue")

        except Exception as e:
            logger.error(f"Error handling event {event}: {e}")
            # Never block on hook failures
            return HookResult(action="continue")
