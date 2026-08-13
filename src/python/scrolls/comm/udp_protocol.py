"""Authenticated, version-negotiated envelopes for the UDP transport."""

from collections import OrderedDict
import base64
import hashlib
import hmac
import json
import secrets
import time


PROTOCOL_NAME = "scrolls-udp"
ENVELOPE_VERSION = 1
HMAC_ALGORITHM = "HMAC-SHA256"
IMPLEMENTED_PROTOCOL_VERSIONS = (1,)
NONCE_BYTES = 16
NONCE_TEXT_LENGTH = 22
MAX_SUPPORTED_VERSIONS = 16
MAX_PROTOCOL_VERSION = 65535
MAX_TIMESTAMP = (1 << 63) - 1
MAX_HMAC_KEY_BYTES = 4096
DEFAULT_MAX_CLOCK_SKEW_SECONDS = 30
DEFAULT_REPLAY_CACHE_ENTRIES = 4096
DEFAULT_REPLAY_CACHE_TTL_SECONDS = 61
UDP_RESPONSE_TRUNCATION_MARKER = "\n[UDP response truncated]"

_ENVELOPE_FIELDS = {
    "algorithm",
    "envelope_version",
    "error",
    "kind",
    "mac",
    "nonce",
    "payload",
    "protocol",
    "protocol_version",
    "request_nonce",
    "supported_versions",
    "timestamp",
}
_KINDS = {"request", "response", "error"}
_ERROR_CODES = {
    "downgrade_conflict",
    "negotiation_required",
    "unsupported_versions",
}


class UdpProtocolError(ValueError):
    """Base class for datagrams rejected by the protocol boundary."""


class MalformedEnvelope(UdpProtocolError):
    pass


class AuthenticationFailed(UdpProtocolError):
    pass


class ExpiredEnvelope(UdpProtocolError):
    pass


class ReplayedEnvelope(UdpProtocolError):
    pass


class ReplayCacheFull(UdpProtocolError):
    pass


class ProtocolVersionError(UdpProtocolError):
    def __init__(self, message, envelope=None, selected_version=None, peer_versions=()):
        super().__init__(message)
        self.envelope = envelope
        self.selected_version = selected_version
        self.peer_versions = tuple(peer_versions)


class UnsupportedProtocolVersions(ProtocolVersionError):
    pass


class ProtocolNegotiationRequired(ProtocolVersionError):
    pass


class ProtocolDowngradeConflict(ProtocolVersionError):
    pass


class Envelope:
    """Validated envelope data, with the wire dictionary retained for replies."""

    def __init__(self, values):
        self.values = values
        self.kind = values["kind"]
        self.error = values["error"]
        self.nonce = values["nonce"]
        self.payload = values["payload"]
        self.protocol_version = values["protocol_version"]
        self.request_nonce = values["request_nonce"]
        self.supported_versions = tuple(values["supported_versions"])
        self.timestamp = values["timestamp"]


class ReplayCache:
    """A bounded, fail-closed nonce cache.

    Live entries are never evicted to admit new traffic: when capacity is reached,
    new datagrams are rejected until expiry. This avoids reopening a replay window
    under nonce-flooding pressure.
    """

    def __init__(
        self,
        max_entries=DEFAULT_REPLAY_CACHE_ENTRIES,
        ttl_seconds=DEFAULT_REPLAY_CACHE_TTL_SECONDS,
    ):
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
            raise ValueError("replay cache entry limit must be a positive integer")
        if ttl_seconds <= 0:
            raise ValueError("replay cache TTL must be positive")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries = OrderedDict()

    def __len__(self):
        return len(self._entries)

    def _evict_expired(self, now):
        for nonce, expiry in list(self._entries.items()):
            if expiry <= now:
                del self._entries[nonce]

    def check_and_store(self, nonce, now):
        self._evict_expired(now)
        if nonce in self._entries:
            raise ReplayedEnvelope("replayed UDP envelope")
        if len(self._entries) >= self.max_entries:
            raise ReplayCacheFull("UDP replay cache is at capacity")
        self._entries[nonce] = now + self.ttl_seconds


def canonical_json_bytes(values):
    """Return the protocol's sole canonical JSON representation."""

    return json.dumps(
        values,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_unsigned_bytes(values):
    unsigned = dict(values)
    unsigned.pop("mac", None)
    return canonical_json_bytes(unsigned)


def _encode_nonce(raw_nonce):
    if not isinstance(raw_nonce, bytes) or len(raw_nonce) != NONCE_BYTES:
        raise ValueError("nonce source must return exactly 16 bytes")
    return base64.urlsafe_b64encode(raw_nonce).rstrip(b"=").decode("ascii")


def _validate_nonce(nonce, field_name):
    if not isinstance(nonce, str) or len(nonce) != NONCE_TEXT_LENGTH:
        raise MalformedEnvelope("%s must be a canonical 128-bit nonce" % field_name)
    try:
        raw_nonce = base64.b64decode(nonce + "==", altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exception:
        raise MalformedEnvelope("%s must be a canonical 128-bit nonce" % field_name) from exception
    if _encode_nonce(raw_nonce) != nonce:
        raise MalformedEnvelope("%s must be a canonical 128-bit nonce" % field_name)


def _validate_versions(versions):
    if not isinstance(versions, list) or not 1 <= len(versions) <= MAX_SUPPORTED_VERSIONS:
        raise MalformedEnvelope("supported_versions must contain 1 to 16 versions")
    previous = 0
    for version in versions:
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or not 1 <= version <= MAX_PROTOCOL_VERSION
            or version <= previous
        ):
            raise MalformedEnvelope(
                "supported_versions must be unique, ascending integers from 1 to 65535"
            )
        previous = version


def normalize_supported_versions(versions):
    versions = list(versions)
    _validate_versions(versions)
    return tuple(versions)


def _validate_payload_text(payload, kind):
    if not isinstance(payload, str):
        raise MalformedEnvelope("UDP envelope payload must be text")
    try:
        payload.encode("utf-8")
    except UnicodeEncodeError as exception:
        raise MalformedEnvelope("UDP envelope payload must contain valid Unicode") from exception
    if kind == "request" and (payload.strip() == "" or "\x00" in payload):
        raise MalformedEnvelope("UDP request payload is invalid")
    if kind == "error" and payload.strip() == "":
        raise MalformedEnvelope("UDP protocol error payload must not be blank")


class UdpProtocol:
    """Encode and validate authenticated UDP envelopes.

    Envelope framing is version 1 and HMAC-SHA256 is fixed. Protocol versions
    describe payload semantics and are negotiated inside that stable framing.
    """

    def __init__(
        self,
        key,
        supported_versions=IMPLEMENTED_PROTOCOL_VERSIONS,
        clock=None,
        nonce_factory=None,
        max_clock_skew_seconds=DEFAULT_MAX_CLOCK_SKEW_SECONDS,
        replay_cache=None,
    ):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("UDP HMAC key must contain at least 32 bytes")
        if len(key) > MAX_HMAC_KEY_BYTES:
            raise ValueError("UDP HMAC key must not exceed 4096 bytes")
        self._key = key
        self.supported_versions = normalize_supported_versions(supported_versions)
        unsupported = set(self.supported_versions) - set(IMPLEMENTED_PROTOCOL_VERSIONS)
        if unsupported:
            raise ValueError("configured UDP protocol version is not implemented")
        if max_clock_skew_seconds <= 0:
            raise ValueError("maximum clock skew must be positive")
        self.clock = clock or time.time
        self.nonce_factory = nonce_factory or (lambda: secrets.token_bytes(NONCE_BYTES))
        self.max_clock_skew_seconds = max_clock_skew_seconds
        self.replay_cache = replay_cache
        if self.replay_cache is None:
            self.replay_cache = ReplayCache(
                ttl_seconds=(2 * max_clock_skew_seconds) + 1,
            )
        if self.replay_cache.ttl_seconds <= 2 * max_clock_skew_seconds:
            raise ValueError("replay cache TTL must exceed twice the maximum clock skew")

    def _new_base_envelope(
        self,
        kind,
        payload,
        protocol_version,
        supported_versions,
        request_nonce=None,
        error=None,
        nonce=None,
        timestamp=None,
    ):
        if kind not in _KINDS:
            raise MalformedEnvelope("UDP envelope kind is invalid")
        _validate_payload_text(payload, kind)
        if nonce is None:
            nonce = _encode_nonce(self.nonce_factory())
        if timestamp is None:
            timestamp = int(self.clock())
        values = {
            "algorithm": HMAC_ALGORITHM,
            "envelope_version": ENVELOPE_VERSION,
            "error": error,
            "kind": kind,
            "mac": "",
            "nonce": nonce,
            "payload": payload,
            "protocol": PROTOCOL_NAME,
            "protocol_version": protocol_version,
            "request_nonce": request_nonce,
            "supported_versions": list(supported_versions),
            "timestamp": timestamp,
        }
        values["mac"] = hmac.new(
            self._key,
            _canonical_unsigned_bytes(values),
            hashlib.sha256,
        ).hexdigest()
        return values

    def encode_envelope(
        self,
        kind,
        payload,
        protocol_version,
        supported_versions,
        request_nonce=None,
        error=None,
        nonce=None,
        timestamp=None,
    ):
        """Low-level encoder, useful for protocol implementations and tests."""

        values = self._new_base_envelope(
            kind,
            payload,
            protocol_version,
            supported_versions,
            request_nonce=request_nonce,
            error=error,
            nonce=nonce,
            timestamp=timestamp,
        )
        return canonical_json_bytes(values)

    def encode_request_with_context(self, payload, max_datagram_bytes, versions=None):
        offered_versions = tuple(versions or self.supported_versions)
        normalize_supported_versions(offered_versions)
        _validate_payload_text(payload, "request")
        values = self._new_base_envelope(
            "request",
            payload,
            max(offered_versions),
            offered_versions,
        )
        data = canonical_json_bytes(values)
        if len(data) > max_datagram_bytes:
            raise MalformedEnvelope("authenticated UDP request is too large")
        return data, Envelope(values)

    def encode_request(self, payload, max_datagram_bytes, versions=None):
        data, _ = self.encode_request_with_context(
            payload,
            max_datagram_bytes,
            versions=versions,
        )
        return data

    def _encode_sized_reply(self, values, max_datagram_bytes):
        values["mac"] = hmac.new(
            self._key,
            _canonical_unsigned_bytes(values),
            hashlib.sha256,
        ).hexdigest()
        data = canonical_json_bytes(values)
        if len(data) <= max_datagram_bytes:
            return data

        original_payload = values["payload"]
        marker = UDP_RESPONSE_TRUNCATION_MARKER
        values["payload"] = marker
        values["mac"] = hmac.new(
            self._key,
            _canonical_unsigned_bytes(values),
            hashlib.sha256,
        ).hexdigest()
        if len(canonical_json_bytes(values)) > max_datagram_bytes:
            raise ValueError("UDP response limit cannot fit an authenticated envelope")

        low = 0
        high = len(original_payload)
        best = marker
        while low <= high:
            middle = (low + high) // 2
            candidate = original_payload[:middle] + marker
            values["payload"] = candidate
            values["mac"] = hmac.new(
                self._key,
                _canonical_unsigned_bytes(values),
                hashlib.sha256,
            ).hexdigest()
            candidate_data = canonical_json_bytes(values)
            if len(candidate_data) <= max_datagram_bytes:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1

        values["payload"] = best
        values["mac"] = hmac.new(
            self._key,
            _canonical_unsigned_bytes(values),
            hashlib.sha256,
        ).hexdigest()
        return canonical_json_bytes(values)

    def encode_response(self, payload, request, max_datagram_bytes):
        values = self._new_base_envelope(
            "response",
            payload,
            request.protocol_version,
            self.supported_versions,
            request_nonce=request.nonce,
        )
        return self._encode_sized_reply(values, max_datagram_bytes)

    def encode_version_error(self, exception, max_datagram_bytes):
        request = exception.envelope
        if isinstance(exception, UnsupportedProtocolVersions):
            error = "unsupported_versions"
            selected_version = None
            payload = "ERROR: unsupported protocol versions; server supports: %s" % (
                ",".join(str(version) for version in self.supported_versions),
            )
        elif isinstance(exception, ProtocolNegotiationRequired):
            error = "negotiation_required"
            selected_version = exception.selected_version
            payload = "ERROR: protocol negotiation required; selected version: %s" % (
                selected_version,
            )
        else:
            error = "downgrade_conflict"
            selected_version = exception.selected_version
            payload = "ERROR: protocol downgrade conflict; highest offered version: %s" % (
                selected_version,
            )
        values = self._new_base_envelope(
            "error",
            payload,
            selected_version,
            self.supported_versions,
            request_nonce=request.nonce,
            error=error,
        )
        return self._encode_sized_reply(values, max_datagram_bytes)

    def _decode(self, data, max_datagram_bytes, expected_kinds):
        if not isinstance(data, (bytes, bytearray)):
            raise MalformedEnvelope("UDP datagram must be bytes")
        data = bytes(data)
        if not data:
            raise MalformedEnvelope("UDP datagram must not be empty")
        if len(data) > max_datagram_bytes:
            raise MalformedEnvelope("UDP datagram is too large")
        try:
            values = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exception:
            raise MalformedEnvelope("UDP envelope must be canonical UTF-8 JSON") from exception
        if not isinstance(values, dict) or set(values) != _ENVELOPE_FIELDS:
            raise MalformedEnvelope("UDP envelope fields are invalid")
        if canonical_json_bytes(values) != data:
            raise MalformedEnvelope("UDP envelope is not canonically encoded")
        self._validate_structure(values)
        if values["kind"] not in expected_kinds:
            raise MalformedEnvelope("unexpected UDP envelope kind")

        supplied_mac = values["mac"]
        expected_mac = hmac.new(
            self._key,
            _canonical_unsigned_bytes(values),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(supplied_mac, expected_mac):
            raise AuthenticationFailed("UDP envelope authentication failed")

        now = self.clock()
        if abs(now - values["timestamp"]) > self.max_clock_skew_seconds:
            raise ExpiredEnvelope("UDP envelope timestamp is outside the accepted window")
        self.replay_cache.check_and_store(values["nonce"], now)
        return Envelope(values)

    def _validate_structure(self, values):
        if values["protocol"] != PROTOCOL_NAME:
            raise MalformedEnvelope("UDP protocol identifier is invalid")
        if values["envelope_version"] != ENVELOPE_VERSION:
            raise MalformedEnvelope("UDP envelope version is unsupported")
        if values["algorithm"] != HMAC_ALGORITHM:
            raise MalformedEnvelope("UDP authentication algorithm is unsupported")
        if values["kind"] not in _KINDS:
            raise MalformedEnvelope("UDP envelope kind is invalid")
        _validate_payload_text(values["payload"], values["kind"])
        if (
            not isinstance(values["timestamp"], int)
            or isinstance(values["timestamp"], bool)
            or not 0 <= values["timestamp"] <= MAX_TIMESTAMP
        ):
            raise MalformedEnvelope("UDP envelope timestamp is invalid")
        _validate_nonce(values["nonce"], "nonce")
        _validate_versions(values["supported_versions"])
        if (
            not isinstance(values["mac"], str)
            or len(values["mac"]) != 64
            or any(character not in "0123456789abcdef" for character in values["mac"])
        ):
            raise MalformedEnvelope("UDP envelope MAC is invalid")

        kind = values["kind"]
        protocol_version = values["protocol_version"]
        if protocol_version is not None and (
            not isinstance(protocol_version, int)
            or isinstance(protocol_version, bool)
            or not 1 <= protocol_version <= MAX_PROTOCOL_VERSION
        ):
            raise MalformedEnvelope("UDP protocol version is invalid")
        if kind == "request":
            if values["request_nonce"] is not None or values["error"] is not None:
                raise MalformedEnvelope("UDP request correlation fields are invalid")
            if protocol_version is None:
                raise MalformedEnvelope("UDP request must select a protocol version")
        else:
            _validate_nonce(values["request_nonce"], "request_nonce")
            if kind == "response" and (values["error"] is not None or protocol_version is None):
                raise MalformedEnvelope("UDP response fields are invalid")
            if kind == "error" and values["error"] not in _ERROR_CODES:
                raise MalformedEnvelope("UDP protocol error code is invalid")

    def decode_request(self, data, max_datagram_bytes):
        envelope = self._decode(data, max_datagram_bytes, {"request"})

        highest_offered = max(envelope.supported_versions)
        if envelope.protocol_version != highest_offered:
            raise ProtocolDowngradeConflict(
                "UDP request conflicts with its offered versions",
                envelope=envelope,
                selected_version=highest_offered,
                peer_versions=envelope.supported_versions,
            )

        common = sorted(set(envelope.supported_versions) & set(self.supported_versions))
        if not common:
            raise UnsupportedProtocolVersions(
                "no mutually supported UDP protocol version",
                envelope=envelope,
                peer_versions=envelope.supported_versions,
            )
        selected = max(common)
        if envelope.protocol_version not in self.supported_versions:
            raise ProtocolNegotiationRequired(
                "authenticated UDP protocol negotiation is required",
                envelope=envelope,
                selected_version=selected,
                peer_versions=envelope.supported_versions,
            )
        return envelope

    def decode_response(self, data, request, max_datagram_bytes):
        envelope = self._decode(data, max_datagram_bytes, {"response", "error"})
        if not hmac.compare_digest(envelope.request_nonce, request.nonce):
            raise AuthenticationFailed("UDP response does not match the request")

        common = sorted(set(request.supported_versions) & set(envelope.supported_versions))
        if envelope.kind == "response":
            expected = max(common) if common else None
            if (
                expected is None
                or envelope.protocol_version != request.protocol_version
                or envelope.protocol_version != expected
            ):
                raise ProtocolDowngradeConflict("UDP response version conflicts with request")
            return envelope

        if envelope.error == "unsupported_versions":
            if common or envelope.protocol_version is not None:
                raise ProtocolDowngradeConflict("invalid unsupported-version response")
            raise UnsupportedProtocolVersions(
                envelope.payload,
                envelope=envelope,
                peer_versions=envelope.supported_versions,
            )
        if envelope.error == "negotiation_required":
            expected = max(common) if common else None
            if expected is None or envelope.protocol_version != expected:
                raise ProtocolDowngradeConflict("invalid protocol negotiation response")
            raise ProtocolNegotiationRequired(
                envelope.payload,
                envelope=envelope,
                selected_version=expected,
                peer_versions=envelope.supported_versions,
            )
        raise ProtocolDowngradeConflict(
            envelope.payload,
            envelope=envelope,
            selected_version=envelope.protocol_version,
            peer_versions=envelope.supported_versions,
        )
