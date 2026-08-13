import json
import socket
import threading

import pytest

from scrolls.comm.udp import (
    MAX_UDP_PAYLOAD_BYTES,
    MIN_AUTHENTICATED_UDP_RESPONSE_BYTES,
    UDP_RESPONSE_TRUNCATION_MARKER,
    UdpChannel,
    build_udp_channel,
)
from scrolls.base.relayserver import RelayServer
from scrolls.comm.udp_protocol import (
    AuthenticationFailed,
    Envelope,
    ExpiredEnvelope,
    MalformedEnvelope,
    ProtocolDowngradeConflict,
    ProtocolNegotiationRequired,
    ReplayCache,
    ReplayCacheFull,
    ReplayedEnvelope,
    UnsupportedProtocolVersions,
    UdpProtocol,
    canonical_json_bytes,
)
from scrolls.terminal_server import dispatch_udp_payload


KEY = b"test-key-material-that-is-at-least-32-bytes"
WRONG_KEY = b"different-test-key-material-at-least-32-bytes"
ADDR = ("127.0.0.1", 10000)


class Clock:
    def __init__(self, value=1_800_000_000):
        self.value = value

    def __call__(self):
        return self.value


class Nonces:
    def __init__(self, start=1):
        self.value = start

    def __call__(self):
        value = self.value
        self.value += 1
        return value.to_bytes(16, "big")


class FakeUdpSocket:
    def __init__(self, received=None):
        self.received = list(received or [])
        self.sent = []

    def recvfrom(self, size):
        assert size == MAX_UDP_PAYLOAD_BYTES + 1
        return self.received.pop(0)

    def sendto(self, data, addr):
        self.sent.append((data, addr))


class CapturingClientSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def close(self):
        self.closed = True


def protocols(clock=None):
    clock = clock or Clock()
    return (
        UdpProtocol(KEY, clock=clock, nonce_factory=Nonces(1)),
        UdpProtocol(KEY, clock=clock, nonce_factory=Nonces(100)),
    )


def test_authenticated_dispatch_round_trip_and_response_correlation():
    client_protocol, server_protocol = protocols()
    request_data, request = client_protocol.encode_request_with_context(
        "exec echo hello",
        MAX_UDP_PAYLOAD_BYTES,
    )
    fake_socket = FakeUdpSocket()
    handler_calls = []

    dispatch_udp_payload(
        fake_socket,
        request_data,
        ADDR,
        lambda command: handler_calls.append(command) or "hello",
        protocol=server_protocol,
    )

    assert handler_calls == [b"exec echo hello"]
    response_data, response_addr = fake_socket.sent[0]
    response = client_protocol.decode_response(response_data, request, 4096)
    assert response_addr == ADDR
    assert response.payload == "hello"
    assert response.request_nonce == request.nonce
    assert response.protocol_version == 1
    assert response.supported_versions == (1,)


def test_real_udp_channel_exchange_uses_authenticated_envelopes():
    server_protocol = UdpProtocol(KEY)
    client_protocol = UdpProtocol(KEY)
    server_channel = UdpChannel(protocol=server_protocol)
    server_channel.setup_server(target_host="127.0.0.1", target_port=0)
    port = server_channel.server.getsockname()[1]
    completed = []

    def serve_once():
        message = server_channel.receive_command()
        completed.append(message.command)
        message.answer("ACK authenticated")

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    try:
        client_channel = UdpChannel(protocol=client_protocol, timeout_seconds=1)
        response = client_channel.send_command("ls", target_host="127.0.0.1", target_port=port)
        thread.join(timeout=1)
    finally:
        server_channel.server.close()

    assert response == b"ACK authenticated"
    assert completed == [b"ls"]
    assert not thread.is_alive()


def test_real_udp_negotiation_retries_after_authenticated_selection():
    server_protocol = UdpProtocol(KEY)
    client_protocol = UdpProtocol(KEY)
    # Simulate a future client encoder. The server never dispatches the version
    # 2 attempt; it authenticates the negotiation and dispatches only the retry.
    client_protocol.supported_versions = (1, 2)
    server_channel = UdpChannel(protocol=server_protocol)
    server_channel.setup_server(target_host="127.0.0.1", target_port=0)
    port = server_channel.server.getsockname()[1]
    completed = []

    def serve_once():
        message = server_channel.receive_command()
        completed.append(message.command)
        message.answer("ACK negotiated")

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    try:
        client_channel = UdpChannel(protocol=client_protocol, timeout_seconds=1)
        response = client_channel.send_command("ls", target_host="127.0.0.1", target_port=port)
        thread.join(timeout=1)
    finally:
        server_channel.server.close()

    assert response == b"ACK negotiated"
    assert completed == [b"ls"]
    assert not thread.is_alive()


def test_relay_creates_fresh_authenticated_udp_envelope(monkeypatch):
    sender, receiver = protocols()
    capturing_socket = CapturingClientSocket()
    monkeypatch.setattr(
        "scrolls.comm.udp.socket.socket",
        lambda *args, **kwargs: capturing_socket,
    )
    source_channel = object()
    udp_channel = UdpChannel(protocol=sender)
    relay = RelayServer()
    relay.add_channel(source_channel)
    relay.add_channel(udp_channel)

    relay._relay_message(source_channel, b"ls")

    datagram, target = capturing_socket.sent[0]
    decoded = receiver.decode_request(datagram, MAX_UDP_PAYLOAD_BYTES)
    assert target == ("127.0.0.1", 9000)
    assert decoded.payload == "ls"
    assert capturing_socket.closed is True


def test_tampering_is_rejected_before_dispatch_without_response():
    client_protocol, server_protocol = protocols()
    request_data = client_protocol.encode_request("ls", MAX_UDP_PAYLOAD_BYTES)
    values = json.loads(request_data)
    values["payload"] = "exec whoami"
    tampered = canonical_json_bytes(values)
    fake_socket = FakeUdpSocket()
    handler_calls = []

    dispatch_udp_payload(
        fake_socket,
        tampered,
        ADDR,
        lambda data: handler_calls.append(data),
        protocol=server_protocol,
    )

    assert handler_calls == []
    assert fake_socket.sent == []


def test_wrong_key_is_rejected_with_constant_time_mac_path():
    sender = UdpProtocol(WRONG_KEY, clock=Clock(), nonce_factory=Nonces())
    receiver = UdpProtocol(KEY, clock=Clock(), nonce_factory=Nonces())
    request = sender.encode_request("ls", MAX_UDP_PAYLOAD_BYTES)

    with pytest.raises(AuthenticationFailed):
        receiver.decode_request(request, MAX_UDP_PAYLOAD_BYTES)


def test_replayed_request_is_rejected():
    sender, receiver = protocols()
    request = sender.encode_request("ls", MAX_UDP_PAYLOAD_BYTES)

    receiver.decode_request(request, MAX_UDP_PAYLOAD_BYTES)
    with pytest.raises(ReplayedEnvelope):
        receiver.decode_request(request, MAX_UDP_PAYLOAD_BYTES)


def test_replayed_response_is_rejected_even_when_correlation_is_valid():
    client_protocol, server_protocol = protocols()
    request_data, request = client_protocol.encode_request_with_context(
        "ls",
        MAX_UDP_PAYLOAD_BYTES,
    )
    decoded_request = server_protocol.decode_request(request_data, MAX_UDP_PAYLOAD_BYTES)
    response_data = server_protocol.encode_response("ACK", decoded_request, 4096)

    client_protocol.decode_response(response_data, request, 4096)
    with pytest.raises(ReplayedEnvelope):
        client_protocol.decode_response(response_data, request, 4096)


def test_expired_and_future_envelopes_are_rejected_with_controlled_clock():
    sender_clock = Clock(1_800_000_000)
    receiver_clock = Clock(1_800_000_031)
    sender = UdpProtocol(KEY, clock=sender_clock, nonce_factory=Nonces())
    receiver = UdpProtocol(KEY, clock=receiver_clock, nonce_factory=Nonces())

    with pytest.raises(ExpiredEnvelope):
        receiver.decode_request(
            sender.encode_request("old", MAX_UDP_PAYLOAD_BYTES),
            MAX_UDP_PAYLOAD_BYTES,
        )

    receiver_clock.value = 1_799_999_969
    with pytest.raises(ExpiredEnvelope):
        receiver.decode_request(
            sender.encode_request("future", MAX_UDP_PAYLOAD_BYTES),
            MAX_UDP_PAYLOAD_BYTES,
        )


def test_replay_cache_expires_entries_and_fails_closed_at_capacity():
    cache = ReplayCache(max_entries=1, ttl_seconds=10)
    cache.check_and_store("first", now=100)

    with pytest.raises(ReplayedEnvelope):
        cache.check_and_store("first", now=101)
    with pytest.raises(ReplayCacheFull):
        cache.check_and_store("second", now=101)

    cache.check_and_store("second", now=110)
    assert len(cache) == 1


def test_unsupported_versions_return_deterministic_authenticated_error():
    signer, server = protocols()
    request_data = signer.encode_envelope(
        "request",
        "ls",
        2,
        [2],
        nonce="AAAAAAAAAAAAAAAAAAAAAQ",
        timestamp=int(signer.clock()),
    )
    request = Envelope(json.loads(request_data))
    fake_socket = FakeUdpSocket()

    dispatch_udp_payload(fake_socket, request_data, ADDR, protocol=server)

    response_data = fake_socket.sent[0][0]
    with pytest.raises(UnsupportedProtocolVersions) as raised:
        signer.decode_response(response_data, request, 4096)
    assert str(raised.value) == "ERROR: unsupported protocol versions; server supports: 1"


def test_higher_version_gets_authenticated_negotiation_selection():
    signer, server = protocols()
    request_data = signer.encode_envelope(
        "request",
        "ls",
        2,
        [1, 2],
        nonce="AAAAAAAAAAAAAAAAAAAAAg",
        timestamp=int(signer.clock()),
    )

    with pytest.raises(ProtocolNegotiationRequired) as raised:
        server.decode_request(request_data, MAX_UDP_PAYLOAD_BYTES)
    assert raised.value.selected_version == 1


def test_lower_than_highest_offered_version_is_downgrade_conflict():
    signer, server = protocols()
    request_data = signer.encode_envelope(
        "request",
        "ls",
        1,
        [1, 2],
        nonce="AAAAAAAAAAAAAAAAAAAAAw",
        timestamp=int(signer.clock()),
    )

    with pytest.raises(ProtocolDowngradeConflict) as raised:
        server.decode_request(request_data, MAX_UDP_PAYLOAD_BYTES)
    assert raised.value.selected_version == 2


def test_downgrade_conflict_returns_authenticated_deterministic_error():
    signer, server = protocols()
    request_data = signer.encode_envelope(
        "request",
        "ls",
        1,
        [1, 2],
        nonce="AAAAAAAAAAAAAAAAAAAABA",
        timestamp=int(signer.clock()),
    )
    request = Envelope(json.loads(request_data))
    fake_socket = FakeUdpSocket()

    dispatch_udp_payload(fake_socket, request_data, ADDR, protocol=server)

    with pytest.raises(ProtocolDowngradeConflict) as raised:
        signer.decode_response(fake_socket.sent[0][0], request, 4096)
    assert raised.value.envelope.error == "downgrade_conflict"
    assert str(raised.value) == (
        "ERROR: protocol downgrade conflict; highest offered version: 2"
    )


def test_noncanonical_and_oversized_datagrams_never_dispatch():
    client_protocol, server_protocol = protocols()
    canonical = client_protocol.encode_request("ls", MAX_UDP_PAYLOAD_BYTES)
    noncanonical = json.dumps(json.loads(canonical), indent=2).encode("utf-8")
    oversized = b"x" * (MAX_UDP_PAYLOAD_BYTES + 1)
    fake_socket = FakeUdpSocket()
    calls = []

    for data in (noncanonical, oversized):
        dispatch_udp_payload(
            fake_socket,
            data,
            ADDR,
            lambda payload: calls.append(payload),
            protocol=server_protocol,
        )

    assert calls == []
    assert fake_socket.sent == []


def test_canonical_bytes_are_stable_and_cover_all_signed_fields():
    protocol = UdpProtocol(KEY, clock=Clock(), nonce_factory=Nonces())
    first = protocol.encode_envelope(
        "request",
        "echo ☃",
        1,
        [1],
        nonce="AAAAAAAAAAAAAAAAAAAABQ",
        timestamp=1_800_000_000,
    )
    second = protocol.encode_envelope(
        "request",
        "echo ☃",
        1,
        [1],
        nonce="AAAAAAAAAAAAAAAAAAAABQ",
        timestamp=1_800_000_000,
    )

    assert first == second
    assert b'": ' not in first
    assert b", " not in first
    assert b"\\u2603" in first
    assert first == canonical_json_bytes(json.loads(first))


def test_authenticated_response_truncation_includes_envelope_overhead():
    client_protocol, server_protocol = protocols()
    request_data, request = client_protocol.encode_request_with_context(
        "ls",
        MAX_UDP_PAYLOAD_BYTES,
    )
    decoded_request = server_protocol.decode_request(request_data, MAX_UDP_PAYLOAD_BYTES)

    response_data = server_protocol.encode_response("🙂" * 1000, decoded_request, 512)
    response = client_protocol.decode_response(response_data, request, 512)

    assert len(response_data) <= 512
    assert response.payload.endswith(UDP_RESPONSE_TRUNCATION_MARKER)
    assert response.payload[: -len(UDP_RESPONSE_TRUNCATION_MARKER)]


def test_empty_authenticated_response_is_valid():
    client_protocol, server_protocol = protocols()
    request_data, request = client_protocol.encode_request_with_context(
        "ls",
        MAX_UDP_PAYLOAD_BYTES,
    )
    decoded_request = server_protocol.decode_request(request_data, MAX_UDP_PAYLOAD_BYTES)
    response_data = server_protocol.encode_response("", decoded_request, 4096)

    response = client_protocol.decode_response(response_data, request, 4096)
    assert response.payload == ""


def test_request_size_limit_accounts_for_envelope_overhead():
    protocol = UdpProtocol(KEY, clock=Clock(), nonce_factory=Nonces())

    with pytest.raises(MalformedEnvelope, match="too large"):
        protocol.encode_request("x" * MAX_UDP_PAYLOAD_BYTES, MAX_UDP_PAYLOAD_BYTES)


def test_authenticated_response_limit_rejects_impossible_configuration():
    with pytest.raises(ValueError, match="at least 512 bytes"):
        UdpChannel(
            key=KEY,
            max_response_bytes=MIN_AUTHENTICATED_UDP_RESPONSE_BYTES - 1,
        )


def test_cli_configuration_requires_key_and_legacy_is_explicit(tmp_path):
    with pytest.raises(ValueError, match="requires SCROLLS_UDP_HMAC_KEY"):
        build_udp_channel(args=[], environ={})

    legacy = build_udp_channel(args=["--udp-legacy"], environ={})
    assert legacy.legacy_mode is True
    assert legacy.protocol is None

    key_file = tmp_path / "udp.key"
    key_file.write_bytes(KEY + b"\n")
    authenticated = build_udp_channel(
        args=["--udp-key-file", str(key_file)],
        environ={},
    )
    assert authenticated.legacy_mode is False
    assert authenticated.protocol.supported_versions == (1,)

    request_data = authenticated.protocol.encode_request("ls", MAX_UDP_PAYLOAD_BYTES)
    assert KEY not in request_data

    with pytest.raises(ValueError, match="cannot be combined"):
        build_udp_channel(
            args=["--udp-legacy"],
            environ={"SCROLLS_UDP_HMAC_KEY": KEY.decode("ascii")},
        )

    with pytest.raises(ValueError, match="must not exceed 4096 bytes"):
        build_udp_channel(
            args=[],
            environ={"SCROLLS_UDP_HMAC_KEY": "x" * 4097},
        )
