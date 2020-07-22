import socket


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
        data, addr = self.server.recvfrom(1024)

        message_data = _MessageData()
        message_data.command = data
        message_data.addr = addr
        message_data.server = self.server

        return message_data
