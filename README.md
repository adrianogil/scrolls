# scrolls

A simple Python terminal emulator that ships with multiple communication channels for remote command execution.

## Features

- Client/server architecture with a CLI loop for sending commands.
- Built-in commands: `ls`, `cd <path>`, and `exec <command>` (client automatically prefixes non-built-ins with `exec`).
- Multiple communication backends:
  - UDP transport (default) on `127.0.0.1:9000`.
  - Git-backed transport that exchanges commands via committed `in.txt`/`out.txt` buffers.
  - Telegram bot transport for remote command delivery and responses.
- Authenticated, replay-resistant UDP messages with explicit protocol-version negotiation.
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

UDP is authenticated by default. Create one 32-byte-or-longer shared key and make
the key file readable only by the account running Scrolls:

```
umask 077
python -c 'import secrets; print(secrets.token_hex(32))' > scrolls-udp.key
```

Run the server:

```
python -m scrolls --server --udp-key-file ./scrolls-udp.key
```

Run the client:

```
python -m scrolls --client --udp-key-file ./scrolls-udp.key
```

`SCROLLS_UDP_HMAC_KEY_FILE` can supply the key-file path instead. For managed
secret injection, `SCROLLS_UDP_HMAC_KEY` can hold the key itself; the CLI
deliberately has no inline key option, which keeps the secret out of process
argument listings and shell history. The same key must be configured at both
ends. Scrolls never puts it in a datagram or log message.

Plaintext compatibility is available only when explicitly selected with
`--udp-legacy` or `SCROLLS_UDP_LEGACY=1`. Do not combine legacy mode with key
configuration. Legacy mode has no authentication, replay protection, or version
negotiation and should only be used during a controlled migration.

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

## Relay server

Relay mode forwards messages between multiple channels. For example, to relay Telegram
messages to UDP (and vice versa):

```
export TELEGRAM_BOT_TOKEN="123456:ABCDEF"
export TELEGRAM_ALLOWED_CHAT_IDS="12345678"
export TELEGRAM_CHAT_ID="12345678"
python -m scrolls --relay --telegram --udp
```

When a relay contains UDP, configure its UDP key in the same way as a normal
server. Telegram and Git retain their existing transport formats; only the UDP
leg uses the authenticated envelope. A relay unwraps a validated UDP payload
before forwarding it and creates a new authenticated envelope when forwarding
to UDP.

## UDP security and protocol

The current payload protocol version is `1`. Each datagram advertises an explicit
ordered version set and selected version inside a canonical JSON envelope,
authenticated with HMAC-SHA256. Servers reject malformed, oversized, expired,
replayed, tampered, unsupported, and downgrade-conflicting datagrams before
application or relay dispatch. The complete wire format, negotiation rules,
limits, failure behavior, and rotation guidance are documented in
[`docs/udp-protocol.md`](docs/udp-protocol.md).

HMAC provides authenticity and integrity, not confidentiality: commands and
responses remain visible on the network. Keep the default loopback binding or
use firewall/VPN controls when exposing this remote-command service. Keep clocks
synchronized because authenticated messages have a short acceptance window.

## Similar tools:
* https://github.com/cornerpirate/gitshell
