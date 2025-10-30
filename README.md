# amplifier-module-hooks-telegram-bridge

Telegram Bridge Hook Module for Amplifier - observes session events and pushes formatted notifications to authorized Telegram users.

## Features

- **Event Observation**: Monitors Amplifier session events (session start/end, prompts, provider calls, tool executions)
- **Message Formatting**: Converts events to human-readable Telegram messages with smart chunking
- **Authorization**: Only sends to authorized users (via pairing.json whitelist)
- **Resilience**: Non-blocking sends with timeout, queue for retry, exponential backoff
- **Reconnection**: Background task retries queued messages automatically

## Installation

```bash
pip install git+https://github.com/ramparte/amplifier-module-hooks-telegram-bridge@main
```

## Setup

### 1. Create Telegram Bot

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow instructions
3. Save the bot token (format: `123456:ABC-DEF1234...`)
4. Send `/setprivacy` → Disable (allows bot to see all messages in groups)

### 2. Configure Module

Add to your Amplifier mount plan:

```yaml
hooks:
  - module: hooks-telegram-bridge
    source: git+https://github.com/ramparte/amplifier-module-hooks-telegram-bridge@main
    config:
      bot_token: "YOUR_BOT_TOKEN"
      pairing_file: ".amplifier/telegram_pairing.json"
      send_timeout: 5
      reconnect_interval: 60
      events:
        - "session:start"
        - "session:end"
        - "prompt:submit"
        - "prompt:complete"
        - "provider:request"
        - "provider:response"
        - "tool:post"
```

### 3. Authorize Users

Create `.amplifier/telegram_pairing.json` with authorized users:

```json
{
  "version": "1.0",
  "authorized_users": [
    {
      "user_id": 123456789,
      "chat_id": 123456789,
      "username": "alice",
      "paired_at": "2025-10-29T10:30:00Z"
    }
  ],
  "rate_limits": {}
}
```

**Finding User/Chat IDs:**
- Start chat with your bot
- Use [@userinfobot](https://t.me/userinfobot) to get your user/chat ID
- Or use the tool module's pairing flow (see amplifier-module-tool-telegram-input)

## Configuration Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bot_token` | string | *required* | Telegram bot token from @BotFather |
| `pairing_file` | string | `.amplifier/telegram_pairing.json` | Path to authorization file |
| `send_timeout` | int | 5 | Timeout for send requests (seconds) |
| `reconnect_interval` | int | 60 | Interval for retry loop (seconds) |
| `events` | list[string] | All defaults | Events to observe |

### Default Events

If `events` not specified, hook observes:
- `session:start` - Session started
- `session:end` - Session ended
- `prompt:submit` - User submitted prompt
- `prompt:complete` - Prompt completed
- `provider:request` - LLM provider called
- `provider:response` - LLM provider responded
- `tool:post` - Tool executed

## Message Formatting

Events are formatted as human-readable Telegram messages:

**Session Start:**
```
🚀 Session Started

Session ID: abc-123-def
```

**Prompt Submit:**
```
💬 Prompt Submitted

[Prompt text, truncated to 500 chars]
```

**Tool Execution:**
```
✅ Tool Executed

Tool: `filesystem_read`
Success: True
```

Messages automatically chunk at 4000 char limit (Telegram max), breaking at newline boundaries.

## Architecture

### Components

1. **TelegramBridgeHook** (`hook.py`)
   - Implements Amplifier Hook interface
   - Observes configured events
   - Routes to formatter and client
   - Non-blocking with timeout

2. **TelegramClient** (`telegram_client.py`)
   - Direct Bot API calls (https://api.telegram.org/bot{token}/sendMessage)
   - Timeout: 5 seconds
   - Retry: Exponential backoff (1s, 2s, 4s, 8s, max 60s)
   - Queue: Failed messages (max 100, 1 hour TTL)

3. **MessageFormatter** (`message_formatter.py`)
   - Converts events to formatted messages
   - Smart chunking (4000 char limit, break on newlines)
   - Event-specific formatters

4. **AuthManager** (`auth_manager.py`)
   - Reads pairing.json to get authorized users
   - Shared with tool module (identical implementation)

### Flow

```
Amplifier Event
    ↓
TelegramBridgeHook.handle_event()
    ↓
Check authorized users (AuthManager)
    ↓
Format message (MessageFormatter)
    ↓
Send to Telegram (TelegramClient)
    ↓
Success → Done
Failure → Queue for retry
    ↓
Background task retries every 60s
```

## Security

- **Whitelist-only**: Only sends to users in pairing.json
- **No ambient authority**: Bot token required explicitly
- **Rate limiting**: Tracks failed auth attempts (managed by tool module)
- **Non-interference**: Hook failures never crash session

## Error Handling

- **Send timeout**: Queue for retry, continue processing
- **Network failure**: Queue for retry, emit `bridge:send_failed` event
- **Authorization failure**: Skip user, log warning
- **Formatting failure**: Send generic JSON, log error

## Events Emitted

Hook emits these events for observability:

- `bridge:message_sent` - Successfully sent message
  - Data: `{user_id, chat_id, event, success}`

- `bridge:send_failed` - Failed to send message
  - Data: `{user_id, chat_id, event, error}`

- `bridge:reconnecting` - Retrying queued messages
  - Data: `{queued_messages, retry_attempt}`

## Example Mount Plan

Complete example with hook and tool modules:

```yaml
hooks:
  - module: hooks-telegram-bridge
    source: git+https://github.com/ramparte/amplifier-module-hooks-telegram-bridge@main
    config:
      bot_token: "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
      pairing_file: ".amplifier/telegram_pairing.json"
      events:
        - "session:start"
        - "prompt:complete"
        - "tool:post"

tools:
  - module: tool-telegram-input
    source: git+https://github.com/ramparte/amplifier-module-tool-telegram-input@main
    config:
      bot_token: "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
      pairing_file: ".amplifier/telegram_pairing.json"
```

## Testing

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest tests/ -v

# Run specific test
uv run pytest tests/test_hook.py::test_hook_handles_event -v
```

## Development

### Structure

```
amplifier-module-hooks-telegram-bridge/
├── amplifier_module_hooks_telegram_bridge/
│   ├── __init__.py          # Module mount point
│   ├── hook.py              # TelegramBridgeHook
│   ├── telegram_client.py   # API client with resilience
│   ├── message_formatter.py # Event → message formatting
│   └── auth_manager.py      # Authorization checking (shared)
├── tests/
│   ├── test_hook.py
│   └── ...
├── pyproject.toml
└── README.md
```

### Philosophy

Follows Amplifier design principles:

- **Ruthless simplicity**: Direct API calls, minimal abstractions
- **Non-interference**: Hook failures never crash session
- **Mechanism not policy**: Hook provides observation, formatting is swappable
- **Event-first observability**: All actions emit events

## Troubleshooting

### Messages not sending

1. Check bot token is correct: `curl https://api.telegram.org/bot<TOKEN>/getMe`
2. Verify users in pairing.json have correct user_id and chat_id
3. Check logs for send failures and queue status

### Messages delayed

- Check `reconnect_interval` (default 60s)
- Monitor queue size in logs
- Verify network connectivity

### Hook not observing events

- Verify `events` config matches Amplifier event names
- Check hook registered successfully in logs: "Mounted TelegramBridgeHook"

## License

MIT

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md)

## Related Modules

- [amplifier-module-tool-telegram-input](https://github.com/ramparte/amplifier-module-tool-telegram-input) - Complementary tool for receiving messages from Telegram
