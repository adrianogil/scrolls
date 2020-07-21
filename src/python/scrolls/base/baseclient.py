"""Module responsible for client implementation """


class ScrollClient:
    """
        ScrollClient
        ------------

        Class responsible for client implementation
    """
    def __init__(self):
        self._comm_channel = None

    @property
    def comm_channel(self):
        return self._comm_channel

    @comm_channel.setter
    def comm_channel(self, channel_obj):
        self._comm_channel = channel_obj

    def show_commands_output(self, cmd_output):
        cmd_output = cmd_output.decode("utf8")
        print(cmd_output)

    def command_loop(self):
        command_input = ""
        while command_input != "quit":
            command_input = input(">> ")
            command_to_send = self.parse_command_input(command_input)
            cmd_output = self._comm_channel.send_command(command_to_send)
            self.show_commands_output(cmd_output)
