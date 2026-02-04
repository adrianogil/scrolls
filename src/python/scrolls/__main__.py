from scrolls.base.baseserver import ScrollServer
from scrolls.base.baseclient import ScrollClient
from scrolls.base.relayserver import RelayServer
from scrolls.comm.udp import UdpChannel
from scrolls.comm.git import GitChannel
from scrolls.comm.telegram import TelegramChannel


if __name__ == '__main__':
    import sys
    import os
    args = sys.argv[1:]

    target_channel = None

    def build_telegram_channel():
        channel = TelegramChannel()
        channel.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        allowed_chat_ids = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
        if allowed_chat_ids:
            channel.allowed_chat_ids = {
                int(chat_id.strip())
                for chat_id in allowed_chat_ids.split(",")
                if chat_id.strip()
            }
        channel.target_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        channel.setup_server()
        return channel

    def build_git_channel():
        channel = GitChannel()
        channel.git_repo_path = os.getcwd()
        channel.setup_server()
        return channel

    def build_udp_channel():
        return UdpChannel()

    if "--relay" in args:
        relay_server = RelayServer()
        channels = []
        if "--telegram" in args:
            channels.append(build_telegram_channel())
        if "--git" in args:
            channels.append(build_git_channel())
        if "--udp" in args or not channels:
            channels.append(build_udp_channel())

        for channel in channels:
            relay_server.add_channel(channel)

        relay_server.run()
        sys.exit(0)

    if "--telegram" in args:
        target_channel = build_telegram_channel()
    elif "--git" in args:
        target_channel = build_git_channel()
    else:
        target_channel = build_udp_channel()

    if "--server" in args:
        server = ScrollServer()
        server.comm_channel = target_channel
        server.run()
    elif "--client" in args:
        client = ScrollClient()
        client.comm_channel = target_channel
        client.command_loop()
