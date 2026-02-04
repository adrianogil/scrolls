import json
import time
from urllib import parse, request

from scrolls.utils.encryption import decrypt_message, encrypt_message


class _MessageData:
    def __init__(self):
        self.command = None
        self.chat_id = None
        self.server = None

    def answer(self, message):
        self.server.send_message(self.chat_id, message)


class TelegramChannel:
    def __init__(self):
        self.bot_token = ""
        self.poll_timeout_seconds = 30
        self.update_offset = None
        self.allowed_chat_ids = set()
        self.target_chat_id = None
        self.encryption_key = None

    def setup_server(self):
        if not self.bot_token:
            raise ValueError("Telegram bot token is required")

    def send_command(self, command_to_send, target_chat_id=None):
        if target_chat_id is None:
            target_chat_id = self.target_chat_id
        if not target_chat_id:
            raise ValueError("Target chat id is required to send commands")

        self.send_message(target_chat_id, command_to_send)
        response = self.receive_command()
        return response.command

    def receive_command(self):
        while True:
            updates = self._get_updates()
            if not updates:
                continue

            for update in updates:
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue

                chat = message.get("chat", {})
                chat_id = chat.get("id")
                if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
                    continue

                text = message.get("text")
                if not text:
                    continue

                text = decrypt_message(text, self.encryption_key)
                message_data = _MessageData()
                message_data.command = text
                message_data.chat_id = chat_id
                message_data.server = self
                return message_data

    def send_message(self, chat_id, message):
        message = encrypt_message(message, self.encryption_key)
        payload = {"chat_id": chat_id, "text": message}
        self._api_request("sendMessage", payload)

    def _get_updates(self):
        payload = {"timeout": self.poll_timeout_seconds}
        if self.update_offset is not None:
            payload["offset"] = self.update_offset

        data = self._api_request("getUpdates", payload)
        updates = data.get("result", [])

        if updates:
            last_update_id = updates[-1].get("update_id")
            if last_update_id is not None:
                self.update_offset = last_update_id + 1

        return updates

    def _api_request(self, method, payload):
        url = "https://api.telegram.org/bot{}/{}".format(self.bot_token, method)
        encoded_payload = parse.urlencode(payload).encode("utf-8")
        req = request.Request(url, data=encoded_payload)
        with request.urlopen(req, timeout=self.poll_timeout_seconds + 5) as response:
            response_data = response.read().decode("utf-8")
        data = json.loads(response_data)
        if not data.get("ok"):
            description = data.get("description", "Unknown error")
            raise ValueError("Telegram API error: {}".format(description))
        return data
