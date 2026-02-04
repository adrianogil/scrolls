from scrolls.base.baseserver import ScrollServer
from scrolls.base.baseclient import ScrollClient
from scrolls.comm.udp import UdpChannel
from scrolls.comm.git import GitChannel
from scrolls.comm.telegram import TelegramChannel


if __name__ == '__main__':
    import sys
    import os
    args = sys.argv[1:]

    target_channel = None

    if "--telegram" in args:
        target_channel = TelegramChannel()
        target_channel.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        allowed_chat_ids = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
        if allowed_chat_ids:
            target_channel.allowed_chat_ids = {
                int(chat_id.strip())
                for chat_id in allowed_chat_ids.split(",")
                if chat_id.strip()
            }
        target_channel.target_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        target_channel.setup_server()
    elif "--git" in args:
        target_channel = GitChannel()
        target_channel.git_repo_path = os.getcwd()
        target_channel.setup_server()
    else:
        target_channel = UdpChannel()

    encryption_key = os.environ.get("SCROLLS_ENCRYPTION_KEY")
    if encryption_key:
        target_channel.encryption_key = encryption_key

    if "--server" in args:
        server = ScrollServer()
        server.comm_channel = target_channel
        server.run()
    elif "--client" in args:
        client = ScrollClient()
        client.comm_channel = target_channel
        client.command_loop()
