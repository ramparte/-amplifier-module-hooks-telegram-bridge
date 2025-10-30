"""
Message formatter for converting Amplifier events to Telegram messages.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MessageFormatter:
    """Formats Amplifier events as human-readable Telegram messages."""

    # Telegram message length limit
    MAX_MESSAGE_LENGTH = 4000

    @staticmethod
    def _truncate(text: str, max_length: int) -> str:
        """
        Truncate text to fit within length limit.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text with ellipsis if needed
        """
        if len(text) <= max_length:
            return text
        return text[: max_length - 4] + "..."

    @staticmethod
    def _chunk_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
        """
        Split long message into chunks at newline boundaries.

        Args:
            text: Message text
            max_length: Maximum chunk length

        Returns:
            List of message chunks
        """
        if len(text) <= max_length:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = []
        current_length = 0

        for line in lines:
            line_length = len(line) + 1  # +1 for newline

            if current_length + line_length > max_length:
                # Finish current chunk
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0

                # Handle line longer than max_length
                if line_length > max_length:
                    # Split at max_length boundaries
                    for i in range(0, len(line), max_length):
                        chunks.append(line[i : i + max_length])
                else:
                    current_chunk.append(line)
                    current_length = line_length
            else:
                current_chunk.append(line)
                current_length += line_length

        # Add final chunk
        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    @classmethod
    def format_session_start(cls, data: dict[str, Any]) -> list[str]:
        """Format session:start event."""
        session_id = data.get("session_id", "unknown")
        message = f"🚀 *Session Started*\n\nSession ID: `{session_id}`"
        return [message]

    @classmethod
    def format_prompt_submit(cls, data: dict[str, Any]) -> list[str]:
        """Format prompt:submit event."""
        prompt = data.get("prompt", "")
        message = f"💬 *Prompt Submitted*\n\n{cls._truncate(prompt, 500)}"
        return cls._chunk_message(message)

    @classmethod
    def format_prompt_complete(cls, data: dict[str, Any]) -> list[str]:
        """Format prompt:complete event."""
        response = data.get("response", "")
        message = f"✅ *Prompt Complete*\n\n{cls._truncate(response, 1000)}"
        return cls._chunk_message(message)

    @classmethod
    def format_provider_request(cls, data: dict[str, Any]) -> list[str]:
        """Format provider:request event."""
        provider = data.get("provider", "unknown")
        message_count = len(data.get("messages", []))
        message = f"🤖 *Provider Request*\n\nProvider: {provider}\nMessages: {message_count}"
        return [message]

    @classmethod
    def format_provider_response(cls, data: dict[str, Any]) -> list[str]:
        """Format provider:response event."""
        provider = data.get("provider", "unknown")
        tokens = data.get("usage", {})
        message = f"📊 *Provider Response*\n\nProvider: {provider}\n"

        if tokens:
            message += f"Tokens: input={tokens.get('input_tokens', 0)}, output={tokens.get('output_tokens', 0)}"

        return [message]

    @classmethod
    def format_tool_post(cls, data: dict[str, Any]) -> list[str]:
        """Format tool:post event."""
        tool_name = data.get("tool_name", "unknown")
        success = data.get("success", False)
        status = "✅" if success else "❌"
        message = f"{status} *Tool Executed*\n\nTool: `{tool_name}`\nSuccess: {success}"
        return [message]

    @classmethod
    def format_generic_event(cls, event: str, data: dict[str, Any]) -> list[str]:
        """Format any event as JSON (fallback)."""
        import json

        message = f"📝 *Event: {event}*\n\n```json\n{json.dumps(data, indent=2)[:1000]}\n```"
        return cls._chunk_message(message)

    @classmethod
    def format_event(cls, event: str, data: dict[str, Any]) -> list[str]:
        """
        Format event based on type.

        Args:
            event: Event name
            data: Event data

        Returns:
            List of message chunks
        """
        # Map events to formatters
        formatters = {
            "session:start": cls.format_session_start,
            "prompt:submit": cls.format_prompt_submit,
            "prompt:complete": cls.format_prompt_complete,
            "provider:request": cls.format_provider_request,
            "provider:response": cls.format_provider_response,
            "tool:post": cls.format_tool_post,
        }

        formatter = formatters.get(event)

        try:
            if formatter:
                return formatter(data)
            return cls.format_generic_event(event, data)
        except Exception as e:
            logger.error(f"Error formatting event {event}: {e}")
            return [f"❌ Error formatting event: {event}"]
