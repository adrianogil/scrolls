import socket


MAX_UDP_PAYLOAD_BYTES = 1024
MAX_UDP_RESPONSE_BYTES = 4096
UDP_RESPONSE_TRUNCATION_MARKER = "\n[UDP response truncated]"


class InvalidUdpPayload(ValueError):
    pass


def validate_udp_payload(payload):
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
    server.sendto(encode_udp_response(message, max_response_bytes), addr)


class _MessageData:
    def __init__(self):
        self.command = None
        self.addr = None
        self.server = None
        self.max_response_bytes = MAX_UDP_RESPONSE_BYTES

    def answer(self, message):
        send_udp_response(
            self.server,
            message,
            self.addr,
            self.max_response_bytes,
        )


class UdpChannel:
    def __init__(self, max_response_bytes=MAX_UDP_RESPONSE_BYTES):
        self.host = "127.0.0.1"
        self.port = 9000
        self.server = None
        self.max_response_bytes = max_response_bytes

        if max_response_bytes < len(UDP_RESPONSE_TRUNCATION_MARKER.encode("utf-8")):
            raise ValueError("UDP response limit must fit the truncation marker")

    def send_message(self, message, target_host=None, target_port=None):
        if target_host is None:
            target_host = self.host
        if target_port is None:
            target_port = self.port

        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.sendto(message.encode(), (target_host, target_port))

    def send_command(self, command_to_send, target_host=None, target_port=None):
        if target_host is None:
            target_host = self.host
        if target_port is None:
            target_port = self.port

        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.sendto(command_to_send.encode(), (target_host, target_port))
        data, addr = client.recvfrom(self.max_response_bytes)

        return data

    def setup_server(self, target_host=None, target_port=None):
        if target_host is None:
            target_host = self.host
        if target_port is None:
            target_port = self.port

        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.bind((target_host, target_port))

    def receive_command(self):
        while True:
            data, addr = self.server.recvfrom(MAX_UDP_PAYLOAD_BYTES)

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

            message_data = _MessageData()
            message_data.command = data
            message_data.addr = addr
            message_data.server = self.server
            message_data.max_response_bytes = self.max_response_bytes

            return message_data
