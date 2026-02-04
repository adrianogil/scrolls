import socket

from scrolls.utils.encryption import decrypt_message, encrypt_message


class _MessageData:
    def __init__(self):
        self.command = None
        self.addr = None
        self.server = None

    def answer(self, message):
        self.server.send_reply(message, self.addr)


class UdpChannel:
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 9000
        self.server = None
        self.encryption_key = None

    def send_command(self, command_to_send, target_host=None, target_port=None):
        if target_host is None:
            target_host = self.host
        if target_port is None:
            target_port = self.port

        command_to_send = self._normalize_message(command_to_send)
        command_to_send = encrypt_message(command_to_send, self.encryption_key)

        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.sendto(command_to_send.encode(), (target_host, target_port))
        data, addr = client.recvfrom(4096)

        if self.encryption_key is None:
            return data
        return decrypt_message(data.decode("utf-8"), self.encryption_key)

    def setup_server(self, target_host=None, target_port=None):
        if target_host is None:
            target_host = self.host
        if target_port is None:
            target_port = self.port

        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.bind((target_host, target_port))

    def receive_command(self):
        data, addr = self.server.recvfrom(1024)

        if self.encryption_key is None:
            command = data
        else:
            command = decrypt_message(data.decode("utf-8"), self.encryption_key)

        message_data = _MessageData()
        message_data.command = command
        message_data.addr = addr
        message_data.server = self

        return message_data

    def send_reply(self, message, addr):
        message = self._normalize_message(message)
        message = encrypt_message(message, self.encryption_key)
        self.server.sendto(message.encode(), addr)

    @staticmethod
    def _normalize_message(message):
        if isinstance(message, bytes):
            return message.decode("utf-8")
        return message
