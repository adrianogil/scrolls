"""Module responsible for server implementation """
import scrolls.utils.clitools as clitools

import os


class ScrollServer:
    """
        ScrollServer1
        ------------

        Class responsible for client implementation
    """
    def __init__(self):
        self._comm_channel = None
        self.is_running = False

    @property
    def comm_channel(self):
        return self._comm_channel

    @comm_channel.setter
    def comm_channel(self, channel_obj):
        self._comm_channel = channel_obj

    def show_commands_output(self, cmd_output):
        cmd_output = cmd_output.decode("utf8")
        print(cmd_output)

    def run(self):
        self.is_running = True
        self._comm_channel.setup_server()
        self._run_server_loop()

    def _run_server_loop(self):
        while self.is_running:
            command_data = self._comm_channel.receive_command()
            cmd_output = self._process_command(command_data.command)
            command_data.answer(cmd_output)

    def _process_command(self, command):
        try:
            command_received = command.decode("utf8")
        except:
            command_received = command
        print("Command received: %s" % (command_received,))
        cmd_output = 'ACK'
        if command_received == "ls":
            cmd_output = ""
            dir_content = os.listdir()
            for content in dir_content:
                cmd_output += content + "\n"
        elif command_received[0:2] == "cd":
            next_path = ""
            if len(command_received) == 2:
                home_path = os.path.expanduser("~")
                os.chdir(home_path)
                next_path = home_path
            else:
                cmd_split = command_received.split(" ")
                target_path = cmd_split[1]
                os.chdir(target_path)
                next_path = target_path
            next_path = os.path.abspath(next_path)
            cmd_output = "Moved to path: %s" % (next_path,)
        elif command_received[0:5] == "exec ":
            cmd = command_received[5:]
            print("Executing command: %s" % (cmd,))

            try:
                cmd_output = clitools.run_cmd(cmd)
            except Exception as exception:
                cmd_output = "ERROR: something went wrong! Got error: %s" % (exception,)

        return cmd_output
