import socket


MAX_UDP_PAYLOAD_BYTES = 1024


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


class _MessageData:
    def __init__(self):
        self.command = None
        self.addr = None
        self.server = None

    def answer(self, message):
        self.server.sendto(message.encode(), self.addr)


class UdpChannel:
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 9000
        self.server = None

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
        data, addr = client.recvfrom(4096)

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
                self.server.sendto(invalid_payload_response(exception).encode(), addr)
                continue

            message_data = _MessageData()
            message_data.command = data
            message_data.addr = addr
            message_data.server = self.server

            return message_data
