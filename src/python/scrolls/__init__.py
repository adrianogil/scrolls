from scrolls.base.baseserver import ScrollServer
from scrolls.base.baseclient import ScrollClient
from scrolls.comm.udp import UdpChannel


def get_udp_server():
    server = ScrollServer()
    server.comm_channel = UdpChannel()
    return server


def get_upd_client():
    client = ScrollClient()
    client.comm_channel = UdpChannel()
    return client
