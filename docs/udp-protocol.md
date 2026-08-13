# Scrolls UDP protocol

## Security model

Authenticated UDP mode uses a pre-shared key of 32 to 4,096 bytes. The key is
used only as HMAC key material: it is never serialized into an envelope or
written to application logs. HMAC authenticates and integrity-protects a
datagram but does not encrypt it. Network observers can still read commands and
responses.

The current implementation supports payload protocol version `1` and stable
envelope format version `1`. Plaintext UDP is a separate, explicit compatibility
mode. An authenticated endpoint never attempts to parse an invalid envelope as
legacy plaintext.

## Canonical envelope

Every authenticated request, response, and protocol error is a UTF-8 JSON object
with exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `algorithm` | string | Fixed value `HMAC-SHA256`. |
| `envelope_version` | integer | Stable control-envelope version, currently `1`. |
| `error` | string or null | A defined protocol error code for `error` envelopes; otherwise null. |
| `kind` | string | `request`, `response`, or `error`. |
| `mac` | string | Lowercase 64-character SHA-256 HMAC hex digest. |
| `nonce` | string | Unpadded base64url encoding of exactly 16 random bytes (22 characters). |
| `payload` | string | Command, response, or deterministic error text. |
| `protocol` | string | Fixed value `scrolls-udp`. |
| `protocol_version` | integer or null | Selected payload version; null only when no common version exists. |
| `request_nonce` | string or null | Request nonce echoed by responses/errors; null on requests. |
| `supported_versions` | integer array | 1–16 unique ascending values in the range 1–65535. |
| `timestamp` | integer | Unix time in seconds, bounded to 0 through 2^63-1. |

Canonical bytes are produced with JSON object keys sorted lexicographically,
ASCII escaping enabled, and separators `,` and `:` with no added whitespace.
There is no trailing newline. Implementations reject a datagram unless its bytes
exactly equal this canonical representation. This also rejects duplicate keys,
alternative escaping, and whitespace variants.

The MAC input is the canonical representation of the same object with the `mac`
field omitted entirely. The algorithm is:

```
hex_lower(HMAC-SHA256(shared_key, canonical_json(envelope_without_mac)))
```

Receivers validate the fixed schema and canonical bytes, calculate the expected
MAC, and compare it with `hmac.compare_digest`. A key identifier is intentionally
not sent: deployments should coordinate key rotation rather than exposing key
metadata on the wire.

## Freshness and replay handling

- Nonces contain 128 random bits and have one canonical encoding.
- Timestamps may differ from the receiver clock by at most 30 seconds in either
  direction.
- Each process remembers up to 4,096 authenticated nonces for 61 seconds. The
  TTL exceeds twice the clock-skew window so an accepted future-dated datagram
  cannot become replayable before it becomes stale.
- Expired cache entries are removed on receipt. If all 4,096 entries are still
  live, the cache rejects new datagrams until space expires. It never evicts a
  live nonce to admit traffic, because doing so would reopen a replay window.
- A process restart clears the in-memory cache. The timestamp window still
  bounds post-restart replay exposure, so hosts should use synchronized clocks.

Request and response nonces are both checked. A response must also contain the
exact request nonce, compared in constant time, so a valid old response cannot
be attached to a new command.

## Connectionless version negotiation

A request selects the highest member of its own `supported_versions`. Selecting
a lower advertised version is a `downgrade_conflict`, even if that lower version
is supported by the server.

The server then intersects the authenticated client set with its own set:

1. If the selected version is supported, the server dispatches the payload and
   returns that version in an authenticated response.
2. If a lower common version exists, the server returns an authenticated
   `negotiation_required` error with the highest common version and its explicit
   supported set. A capable client retries with the authenticated intersection
   as its new offered set. There is no silent reinterpretation of the first
   payload.
3. If there is no intersection, the server returns an authenticated
   `unsupported_versions` error with a null selected version and its supported
   set.

Because all negotiation data and request correlation are signed, an intermediary
cannot remove a higher version or forge a step-down response. Servers implement
only versions whose payload semantics they understand; adding a number to the
advertised set must accompany the corresponding implementation.

## Validation order and failure behavior

The receive buffer is one byte larger than the configured datagram limit. This
detects kernel truncation instead of accidentally validating a prefix of an
oversized packet. The request limit is 1,024 bytes for the entire envelope, not
just the command. The response limit is 4,096 bytes for the entire envelope and
cannot be configured below 512 bytes in authenticated mode.

Syntax, canonical representation, fixed identifiers, field bounds, MAC,
timestamp, nonce replay, version rules, and payload validity are all checked
before command execution or relay dispatch. Tampered, wrong-key, malformed,
expired, replayed, and oversized packets are silently dropped to avoid providing
an unauthenticated response oracle. After successful authentication, version
incompatibilities receive deterministic authenticated errors.

Long responses are truncated as text without splitting Unicode characters. The
marker `\n[UDP response truncated]` is included inside the signed payload, and
envelope overhead is included in the response-size calculation. If the limit
cannot fit even an authenticated envelope and marker, configuration fails rather
than sending an oversized or unsigned response.

## Operations and migration

Prefer a mode-`0600` key file passed with `--udp-key-file`, or set its path in
`SCROLLS_UDP_HMAC_KEY_FILE`. Secret managers may inject the value through
`SCROLLS_UDP_HMAC_KEY`. There is deliberately no `--udp-key VALUE` option because
command-line values are commonly visible in process listings and shell history.
Do not include key material in commands, payloads, filenames, or logs.

For rotation, stop or drain both endpoints, replace the shared key, and restart
both sides. Mixed keys fail closed as authentication failures. For migration
from an older release, run both endpoints with `--udp-legacy` only for the
minimum required period, then switch both to authenticated mode. An endpoint
cannot accept authenticated and legacy datagrams simultaneously.

Telegram and Git messages keep their existing transport-specific formats and
security properties. A relay authenticates and validates an incoming UDP
envelope before unwrapping it; when the relay forwards a message onto UDP it
creates a fresh nonce, timestamp, and HMAC envelope.
