import pytest

from scrolls.comm.udp import (
    InvalidUdpPayload,
    UdpChannel,
    invalid_payload_response,
    validate_udp_payload,
)
from scrolls.terminal_server import dispatch_udp_payload


class FakeUdpSocket:
    def __init__(self, received=None):
        self.received = list(received or [])
        self.sent = []

    def recvfrom(self, payload_size):
        assert payload_size == 1024
        return self.received.pop(0)

    def sendto(self, data, addr):
        self.sent.append((data, addr))


def test_validate_udp_payload_accepts_non_blank_utf8_bytes():
    payload = "ls".encode("utf-8")

    assert validate_udp_payload(payload) == payload


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"   \n\t",
        b"\xff",
        b"exec echo\x00hidden",
        "not bytes",
    ],
)
def test_validate_udp_payload_rejects_malformed_payloads(payload):
    with pytest.raises(InvalidUdpPayload):
        validate_udp_payload(payload)


def test_receive_command_rejects_invalid_payload_before_dispatch():
    invalid_addr = ("127.0.0.1", 10000)
    valid_addr = ("127.0.0.1", 10001)
    fake_socket = FakeUdpSocket(
        [
            (b"\xff", invalid_addr),
            (b"ls", valid_addr),
        ]
    )
    channel = UdpChannel()
    channel.server = fake_socket

    message_data = channel.receive_command()

    assert message_data.command == b"ls"
    assert message_data.addr == valid_addr
    assert fake_socket.sent == [
        (invalid_payload_response("payload must be valid UTF-8").encode(), invalid_addr)
    ]


def test_terminal_dispatch_does_not_call_handler_for_invalid_payload():
    fake_socket = FakeUdpSocket()
    handler_calls = []

    def handler(data):
        handler_calls.append(data)
        return "ACK"

    dispatch_udp_payload(fake_socket, b"", ("127.0.0.1", 10000), handler)

    assert handler_calls == []
    assert fake_socket.sent == [
        (invalid_payload_response("payload must not be empty").encode(), ("127.0.0.1", 10000))
    ]


def test_terminal_dispatch_calls_handler_for_valid_payload():
    fake_socket = FakeUdpSocket()
    handler_calls = []

    def handler(data):
        handler_calls.append(data)
        return "handled"

    dispatch_udp_payload(fake_socket, b"pwd", ("127.0.0.1", 10000), handler)

    assert handler_calls == [b"pwd"]
    assert fake_socket.sent == [(b"handled", ("127.0.0.1", 10000))]
