"""UDP channel with authenticated envelopes and explicit legacy mode."""

import os
import socket

from scrolls.comm.udp_protocol import (
    AuthenticationFailed,
    ExpiredEnvelope,
    IMPLEMENTED_PROTOCOL_VERSIONS,
    MAX_HMAC_KEY_BYTES,
    MalformedEnvelope,
    ProtocolDowngradeConflict,
    ProtocolNegotiationRequired,
    ProtocolVersionError,
    ReplayCache,
    ReplayCacheFull,
    ReplayedEnvelope,
    UDP_RESPONSE_TRUNCATION_MARKER,
    UnsupportedProtocolVersions,
    UdpProtocol,
    UdpProtocolError,
)


MAX_UDP_PAYLOAD_BYTES = 1024
MAX_UDP_RESPONSE_BYTES = 4096
MIN_AUTHENTICATED_UDP_RESPONSE_BYTES = 512
DEFAULT_UDP_TIMEOUT_SECONDS = 5
UDP_HMAC_KEY_ENV = "SCROLLS_UDP_HMAC_KEY"
UDP_HMAC_KEY_FILE_ENV = "SCROLLS_UDP_HMAC_KEY_FILE"
UDP_LEGACY_ENV = "SCROLLS_UDP_LEGACY"
MAX_UDP_HMAC_KEY_BYTES = MAX_HMAC_KEY_BYTES


class InvalidUdpPayload(ValueError):
    pass


def validate_udp_payload(payload):
    """Validate a plaintext datagram used only by explicit legacy mode."""

    if not isinstance(payload, (bytes, bytearray)):
        raise InvalidUdpPayload("payload must be bytes")

    payload = bytes(payload)
    if len(payload) == 0:
        raise InvalidUdpPayload("payload must not be empty")
    if len(payload) > MAX_UDP_PAYLOAD_BYTES:
        raise InvalidUdpPayload("payload is too large")

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exception:
        raise InvalidUdpPayload("payload must be valid UTF-8") from exception

    if text.strip() == "":
        raise InvalidUdpPayload("payload must not be blank")
    if "\x00" in text:
        raise InvalidUdpPayload("payload must not contain NUL bytes")

    return payload


def invalid_payload_response(exception):
    return "ERROR: invalid UDP payload: %s" % (exception,)


def encode_udp_response(message, max_response_bytes=MAX_UDP_RESPONSE_BYTES):
    """Encode a plaintext response used only by explicit legacy mode."""

    marker = UDP_RESPONSE_TRUNCATION_MARKER.encode("utf-8")
    if max_response_bytes < len(marker):
        raise ValueError("UDP response limit must fit the truncation marker")

    response = message.encode("utf-8")
    if len(response) <= max_response_bytes:
        return response

    prefix_size = max_response_bytes - len(marker)
    prefix = response[:prefix_size].decode("utf-8", errors="ignore").encode("utf-8")
    return prefix + marker


def send_udp_response(server, message, addr, max_response_bytes=MAX_UDP_RESPONSE_BYTES):
    """Send a plaintext response used only by explicit legacy mode."""

    server.sendto(encode_udp_response(message, max_response_bytes), addr)


def _is_truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _option_value(args, option):
    if option not in args:
        return None
    index = args.index(option)
    if index + 1 >= len(args) or args[index + 1].startswith("--"):
        raise ValueError("%s requires a value" % option)
    return args[index + 1]


def load_udp_hmac_key(key_file=None, environ=None):
    """Load key material without accepting the secret as a CLI argument."""

    environ = os.environ if environ is None else environ
    environment_key = environ.get(UDP_HMAC_KEY_ENV)
    environment_key_file = environ.get(UDP_HMAC_KEY_FILE_ENV)
    selected_key_file = key_file or environment_key_file
    if environment_key and selected_key_file:
        raise ValueError("configure the UDP HMAC key with either an environment value or a key file")
    if selected_key_file:
        with open(selected_key_file, "rb") as key_handle:
            key = key_handle.read(MAX_UDP_HMAC_KEY_BYTES + 2)
        key = key.rstrip(b"\r\n")
    elif environment_key:
        key = environment_key.encode("utf-8")
    else:
        raise ValueError(
            "authenticated UDP requires SCROLLS_UDP_HMAC_KEY or --udp-key-file"
        )
    if len(key) < 32:
        raise ValueError("UDP HMAC key must contain at least 32 bytes")
    if len(key) > MAX_UDP_HMAC_KEY_BYTES:
        raise ValueError("UDP HMAC key must not exceed 4096 bytes")
    return key


def build_udp_channel(args=None, environ=None, **channel_options):
    """Build a channel from CLI/environment configuration."""

    args = list(args or [])
    environ = os.environ if environ is None else environ
    legacy_mode = "--udp-legacy" in args or _is_truthy(environ.get(UDP_LEGACY_ENV, ""))
    key_file = _option_value(args, "--udp-key-file")
    if legacy_mode:
        if key_file or environ.get(UDP_HMAC_KEY_ENV) or environ.get(UDP_HMAC_KEY_FILE_ENV):
            raise ValueError("legacy UDP mode cannot be combined with HMAC key configuration")
        return UdpChannel(legacy_mode=True, **channel_options)
    key = load_udp_hmac_key(key_file=key_file, environ=environ)
    return UdpChannel(key=key, **channel_options)


class _MessageData:
    def __init__(self):
        self.command = None
        self.addr = None
        self.server = None
        self.max_response_bytes = MAX_UDP_RESPONSE_BYTES
        self.protocol = None
        self.request = None
        self.legacy_mode = False

    def answer(self, message):
        if self.legacy_mode:
            send_udp_response(
                self.server,
                message,
                self.addr,
                self.max_response_bytes,
            )
            return
        response = self.protocol.encode_response(
            str(message),
            self.request,
            self.max_response_bytes,
        )
        self.server.sendto(response, self.addr)


class UdpChannel:
    def __init__(
        self,
        key=None,
        legacy_mode=False,
        protocol=None,
        max_response_bytes=MAX_UDP_RESPONSE_BYTES,
        timeout_seconds=DEFAULT_UDP_TIMEOUT_SECONDS,
    ):
        self.host = "127.0.0.1"
        self.port = 9000
        self.server = None
        self.max_response_bytes = max_response_bytes
        self.timeout_seconds = timeout_seconds
        self.legacy_mode = legacy_mode
        if legacy_mode and (key is not None or protocol is not None):
            raise ValueError("legacy UDP mode cannot use authenticated protocol configuration")
        self.protocol = protocol
        if not legacy_mode and self.protocol is None and key is not None:
            self.protocol = UdpProtocol(key)

        if legacy_mode and max_response_bytes < len(UDP_RESPONSE_TRUNCATION_MARKER.encode("utf-8")):
            raise ValueError("UDP response limit must fit the truncation marker")
        if (
            not legacy_mode
            and self.protocol is not None
            and max_response_bytes < MIN_AUTHENTICATED_UDP_RESPONSE_BYTES
        ):
            raise ValueError("authenticated UDP response limit must be at least 512 bytes")

    def _require_protocol(self):
        if not self.legacy_mode and self.protocol is None:
            raise ValueError("authenticated UDP requires an HMAC key")

    def _target(self, target_host, target_port):
        return (
            self.host if target_host is None else target_host,
            self.port if target_port is None else target_port,
        )

    def send_message(self, message, target_host=None, target_port=None):
        self._require_protocol()
        target = self._target(target_host, target_port)
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if self.legacy_mode:
                data = str(message).encode("utf-8")
                validate_udp_payload(data)
            else:
                data = self.protocol.encode_request(
                    str(message),
                    MAX_UDP_PAYLOAD_BYTES,
                )
            client.sendto(data, target)
        finally:
            client.close()

    def send_command(self, command_to_send, target_host=None, target_port=None):
        self._require_protocol()
        target = self._target(target_host, target_port)
        if self.legacy_mode:
            return self._send_legacy_command(str(command_to_send), target)

        offered_versions = self.protocol.supported_versions
        for attempt in range(2):
            data, request = self.protocol.encode_request_with_context(
                str(command_to_send),
                MAX_UDP_PAYLOAD_BYTES,
                versions=offered_versions,
            )
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                client.settimeout(self.timeout_seconds)
                client.sendto(data, target)
                response_data, unused_addr = client.recvfrom(self.max_response_bytes + 1)
            finally:
                client.close()
            try:
                response = self.protocol.decode_response(
                    response_data,
                    request,
                    self.max_response_bytes,
                )
            except ProtocolNegotiationRequired as exception:
                if attempt or exception.selected_version not in self.protocol.supported_versions:
                    raise
                offered_versions = tuple(
                    version
                    for version in self.protocol.supported_versions
                    if version in exception.peer_versions
                )
                continue
            return response.payload.encode("utf-8")
        raise ProtocolNegotiationRequired("UDP protocol negotiation did not converge")

    def _send_legacy_command(self, command_to_send, target):
        data = command_to_send.encode("utf-8")
        validate_udp_payload(data)
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            client.settimeout(self.timeout_seconds)
            client.sendto(data, target)
            response, unused_addr = client.recvfrom(self.max_response_bytes + 1)
        finally:
            client.close()
        if len(response) > self.max_response_bytes:
            raise InvalidUdpPayload("UDP response is too large")
        return response

    def setup_server(self, target_host=None, target_port=None):
        self._require_protocol()
        target = self._target(target_host, target_port)
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.bind(target)

    def receive_command(self):
        self._require_protocol()
        while True:
            data, addr = self.server.recvfrom(MAX_UDP_PAYLOAD_BYTES + 1)
            if self.legacy_mode:
                try:
                    data = validate_udp_payload(data)
                except InvalidUdpPayload as exception:
                    send_udp_response(
                        self.server,
                        invalid_payload_response(exception),
                        addr,
                        self.max_response_bytes,
                    )
                    continue
                request = None
                command = data
            else:
                try:
                    request = self.protocol.decode_request(data, MAX_UDP_PAYLOAD_BYTES)
                except ProtocolVersionError as exception:
                    response = self.protocol.encode_version_error(
                        exception,
                        self.max_response_bytes,
                    )
                    self.server.sendto(response, addr)
                    continue
                except UdpProtocolError:
                    # Authentication and syntax failures are dropped without an
                    # oracle response, and always before application dispatch.
                    continue
                command = request.payload.encode("utf-8")

            message_data = _MessageData()
            message_data.command = command
            message_data.addr = addr
            message_data.server = self.server
            message_data.max_response_bytes = self.max_response_bytes
            message_data.protocol = self.protocol
            message_data.request = request
            message_data.legacy_mode = self.legacy_mode
            return message_data


__all__ = [
    "IMPLEMENTED_PROTOCOL_VERSIONS",
    "AuthenticationFailed",
    "ExpiredEnvelope",
    "InvalidUdpPayload",
    "MAX_UDP_PAYLOAD_BYTES",
    "MAX_UDP_RESPONSE_BYTES",
    "MAX_UDP_HMAC_KEY_BYTES",
    "MIN_AUTHENTICATED_UDP_RESPONSE_BYTES",
    "MalformedEnvelope",
    "ProtocolDowngradeConflict",
    "ProtocolNegotiationRequired",
    "ProtocolVersionError",
    "ReplayCache",
    "ReplayCacheFull",
    "ReplayedEnvelope",
    "UDP_RESPONSE_TRUNCATION_MARKER",
    "UdpChannel",
    "UdpProtocol",
    "UdpProtocolError",
    "UnsupportedProtocolVersions",
    "build_udp_channel",
    "encode_udp_response",
    "invalid_payload_response",
    "load_udp_hmac_key",
    "send_udp_response",
    "validate_udp_payload",
]
