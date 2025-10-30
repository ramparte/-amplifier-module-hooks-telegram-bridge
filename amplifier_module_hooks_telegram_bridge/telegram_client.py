"""
Telegram Bot API client with resilience and retry logic.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta

import requests

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """Queued message for retry."""

    chat_id: int
    text: str
    queued_at: datetime
    retry_count: int = 0


class TelegramClient:
    """Direct Telegram Bot API client with retry logic."""

    def __init__(
        self,
        bot_token: str,
        send_timeout: int = 5,
        max_retries: int = 5,
        max_queue_size: int = 100,
        queue_ttl_hours: int = 1,
    ):
        """
        Initialize Telegram client.

        Args:
            bot_token: Telegram bot token
            send_timeout: Timeout for send requests (seconds)
            max_retries: Maximum retry attempts
            max_queue_size: Maximum queued messages
            queue_ttl_hours: Hours before queued messages expire
        """
        self.bot_token = bot_token
        self.send_timeout = send_timeout
        self.max_retries = max_retries
        self.max_queue_size = max_queue_size
        self.queue_ttl = timedelta(hours=queue_ttl_hours)

        # Failed message queue
        self.message_queue: deque[QueuedMessage] = deque(maxlen=max_queue_size)

        # Retry backoff (exponential: 1s, 2s, 4s, 8s, max 60s)
        self.base_backoff = 1.0
        self.max_backoff = 60.0

    @property
    def base_url(self) -> str:
        """Get base API URL."""
        return f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Send message to Telegram chat (synchronous).

        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: Telegram parse mode

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}

        try:
            response = requests.post(url, json=payload, timeout=self.send_timeout)

            if response.status_code == 200:
                logger.debug(f"Sent message to chat {chat_id}")
                return True
            logger.warning(f"Failed to send message: {response.status_code} - {response.text}")
            # Queue for retry
            self._queue_message(chat_id, text)
            return False

        except requests.Timeout:
            logger.warning(f"Timeout sending message to chat {chat_id}")
            self._queue_message(chat_id, text)
            return False

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self._queue_message(chat_id, text)
            return False

    def _queue_message(self, chat_id: int, text: str) -> None:
        """Queue failed message for retry."""
        if len(self.message_queue) >= self.max_queue_size:
            logger.warning(f"Message queue full ({self.max_queue_size}), dropping oldest message")

        queued = QueuedMessage(chat_id=chat_id, text=text, queued_at=datetime.now())
        self.message_queue.append(queued)
        logger.info(f"Queued message for retry (queue size: {len(self.message_queue)})")

    def retry_queue(self) -> int:
        """
        Retry queued messages with exponential backoff.

        Returns:
            Number of successfully sent messages
        """
        if not self.message_queue:
            return 0

        sent_count = 0
        failed_messages = []

        # Process queue
        while self.message_queue:
            msg = self.message_queue.popleft()

            # Check TTL
            if datetime.now() - msg.queued_at > self.queue_ttl:
                logger.warning(f"Message expired (queued {msg.queued_at}), dropping")
                continue

            # Check retry limit
            if msg.retry_count >= self.max_retries:
                logger.warning(f"Message exceeded max retries ({self.max_retries}), dropping")
                continue

            # Calculate backoff
            backoff = min(self.base_backoff * (2**msg.retry_count), self.max_backoff)

            logger.info(f"Retrying message (attempt {msg.retry_count + 1}, backoff {backoff}s)")
            time.sleep(backoff)

            # Retry send
            success = self.send_message(msg.chat_id, msg.text)

            if success:
                sent_count += 1
            else:
                # Re-queue with incremented retry count
                msg.retry_count += 1
                failed_messages.append(msg)

        # Re-queue failed messages
        self.message_queue.extend(failed_messages)

        logger.info(f"Retry batch complete: {sent_count} sent, {len(self.message_queue)} remain queued")
        return sent_count

    async def async_send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Send message asynchronously (runs sync version in executor).

        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: Telegram parse mode

        Returns:
            True if successful, False otherwise
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.send_message, chat_id, text, parse_mode)

    def get_queue_status(self) -> dict:
        """
        Get current queue status.

        Returns:
            Dictionary with queue metrics
        """
        return {
            "queued_messages": len(self.message_queue),
            "max_queue_size": self.max_queue_size,
            "oldest_message_age": (datetime.now() - self.message_queue[0].queued_at).total_seconds()
            if self.message_queue
            else 0,
        }
