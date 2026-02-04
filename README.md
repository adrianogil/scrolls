# scrolls

A simple Python terminal emulator that ships with multiple communication channels for remote command execution.

## Features

- Client/server architecture with a CLI loop for sending commands.  
- Built-in commands: `ls`, `cd <path>`, and `exec <command>` (client automatically prefixes non-built-ins with `exec`).  
- Multiple communication backends:
  - UDP transport (default) on `127.0.0.1:9000`.
  - Git-backed transport that exchanges commands via committed `in.txt`/`out.txt` buffers.
  - Telegram bot transport for remote command delivery and responses.
- Minimal dependencies (pure Python standard library).

## Commands

| Command | Description |
| --- | --- |
| `ls` | List directory contents on the server. |
| `cd <path>` | Change the server working directory. |
| `<anything else>` | Executes the command on the server via `exec <command>`. |
| `quit` | Exit the client loop. |

## Usage

### UDP (default)

Run the server:

```
python -m scrolls --server
```

Run the client:

```
python -m scrolls --client
```

### Git channel

The Git channel commits command buffers to a repository and expects a configured upstream.

Run the server (from the target repo):

```
python -m scrolls --server --git
```

Run the client (from the same repo clone):

```
python -m scrolls --client --git
```

### Telegram channel

The Telegram communication channel requires a bot token and chat IDs:

- `TELEGRAM_BOT_TOKEN` (required)
- `TELEGRAM_ALLOWED_CHAT_IDS` (optional, comma-separated)
- `TELEGRAM_CHAT_ID` (optional, used by the client to send commands)

Example usage:

```
export TELEGRAM_BOT_TOKEN="123456:ABCDEF"
export TELEGRAM_ALLOWED_CHAT_IDS="12345678"
python -m scrolls --server --telegram
```

## Similar tools

- https://github.com/cornerpirate/gitshell
