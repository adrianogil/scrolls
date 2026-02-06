"""Module responsible for relaying messages between communication channels."""
import threading


class RelayServer:
    """Relay messages between multiple communication channels."""
    def __init__(self):
        self._comm_channels = []
        self.is_running = False
        self.ack_message = "ACK"

    def add_channel(self, channel_obj):
        self._comm_channels.append(channel_obj)

    def run(self):
        if not self._comm_channels:
            raise ValueError("At least one communication channel is required")

        for channel in self._comm_channels:
            channel.setup_server()

        self.is_running = True
        threads = []
        for channel in self._comm_channels:
            thread = threading.Thread(
                target=self._run_channel_loop,
                args=(channel,),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

    def _run_channel_loop(self, channel):
        while self.is_running:
            message_data = channel.receive_command()
            self._relay_message(channel, message_data.command)
            if self.ack_message is not None:
                try:
                    message_data.answer(self.ack_message)
                except Exception as exception:
                    print("Failed to send ack: %s" % (exception,))

    def _relay_message(self, source_channel, message):
        relay_message = self._normalize_message(message)
        for channel in self._comm_channels:
            if channel is source_channel:
                continue
            self._send_message(channel, relay_message)

    def _normalize_message(self, message):
        if isinstance(message, bytes):
            return message.decode("utf8", errors="replace")
        return str(message)

    def _send_message(self, channel, message):
        send_method = getattr(channel, "send_message", None)
        if callable(send_method):
            send_method(message=message)
            return

        try:
            channel.send_command(message, wait_for_answer=False)
        except TypeError:
            channel.send_command(message)
