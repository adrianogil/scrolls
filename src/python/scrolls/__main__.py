from scrolls.base.baseserver import ScrollServer
from scrolls.base.baseclient import ScrollClient
from scrolls.comm.udp import UdpChannel
from scrolls.comm.git import GitChannel


if __name__ == '__main__':
    import sys
    import os
    args = sys.argv[1:]

    target_channel = None

    if "--git" in args:
        target_channel = GitChannel()
        target_channel.git_repo_path = os.getcwd()
        target_channel.setup_server()
    else:
        target_channel = UdpChannel()

    if "--server" in args:
        server = ScrollServer()
        server.comm_channel = target_channel
        server.run()
    elif "--client" in args:
        client = ScrollClient()
        client.comm_channel = target_channel
        client.command_loop()
