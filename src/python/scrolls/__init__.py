from scrolls.base.baseserver import ScrollServer
from scrolls.base.baseclient import ScrollClient
from scrolls.comm.udp import UdpChannel
from scrolls.comm.git import GitChannel
from scrolls.comm.telegram import TelegramChannel


def get_udp_server():
    server = ScrollServer()
    server.comm_channel = UdpChannel()
    return server


def get_udp_client():
    client = ScrollClient()
    client.comm_channel = UdpChannel()
    return client


def get_git_server():
    server = ScrollServer()
    server.comm_channel = GitChannel()
    return server


def get_git_client():
    client = ScrollClient()
    client.comm_channel = GitChannel()
    return client


def get_telegram_server():
    server = ScrollServer()
    server.comm_channel = TelegramChannel()
    return server


def get_telegram_client():
    client = ScrollClient()
    client.comm_channel = TelegramChannel()
    return client
