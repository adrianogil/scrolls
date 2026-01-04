# scrolls
A simple python terminal emulator

## Commands

## Telegram channel

The Telegram communication channel requires a bot token and chat IDs:

* `TELEGRAM_BOT_TOKEN` (required)
* `TELEGRAM_ALLOWED_CHAT_IDS` (optional, comma-separated)
* `TELEGRAM_CHAT_ID` (optional, used by the client to send commands)

Example usage:

```
export TELEGRAM_BOT_TOKEN="123456:ABCDEF"
export TELEGRAM_ALLOWED_CHAT_IDS="12345678"
python -m scrolls --server --telegram
```

## Similar tools:
* https://github.com/cornerpirate/gitshell
