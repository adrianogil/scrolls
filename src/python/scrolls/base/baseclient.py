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
        try:
            cmd_output = cmd_output.decode("utf8")
        except:
            cmd_output = cmd_output
        print(cmd_output)

    def parse_command_input(self, command_input):
        if command_input != "quit" and command_input[0:2] not in ['cd', 'ls']:
            command_input = "exec " + command_input

        return command_input

    def get_input(self):
        command_input = ""

        while not command_input:
            command_input = input(">> ")
            command_input = command_input.strip()

        return command_input

    def command_loop(self):
        command_input = ""
        while command_input != "quit":
            command_input = self.get_input()
            command_to_send = self.parse_command_input(command_input)
            cmd_output = self._comm_channel.send_command(command_to_send)
            self.show_commands_output(cmd_output)
