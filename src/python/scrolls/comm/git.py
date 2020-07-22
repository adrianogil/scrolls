import scrolls.utils.clitools as clitools

import json
import time
import os


class _MessageData:
    def __init__(self):
        self.command = None
        self.addr = None
        self.server = None

    def answer(self, message):
        self.server.send_command(message, to_buffer="output", wait_for_answer=False)


class GitChannel:
    def __init__(self):
        self.git_repo_path = ""
        self.update_time_in_seconds = 1
        self.target_input_file = "in.txt"
        self.target_ouput_file = "out.txt"
        self.last_message_input_id = 0
        self.last_message_output_id = 0

    def send_command(self, command_to_send, wait_for_answer=True, to_buffer="input"):
        if to_buffer == "input":
            if self.last_message_input_id == 0:
                self._read_inbuffer()

            self._write_inbuffer(command_to_send)
        else:
            if self.last_message_output_id == 0:
                self._read_outbuffer()

            self._write_outbuffer(command_to_send)

        data = None
        if wait_for_answer:
            data = self.receive_command(from_buffer=("output" if to_buffer == "input" else "input"))
            data = data.command

        return data

    def setup_server(self):
        os.chdir(self.git_repo_path)
        self._read_inbuffer()
        self._read_outbuffer()

    def receive_command(self, from_buffer="input"):
        found_updates = False

        while not found_updates:
            if from_buffer == "input":
                command = self._read_inbuffer()
            else:
                command = self._read_outbuffer()

            found_updates = command is not None

            if not found_updates:
                time.sleep(self.update_time_in_seconds)

        message_data = _MessageData()
        message_data.command = command
        message_data.server = self

        return message_data

    def _write_inbuffer(self, data):
        os.chdir(self.git_repo_path)

        self.last_message_input_id += 1

        input_data = {
            "message_id": self.last_message_input_id,
            "message": data
        }

        with open(self.target_input_file, 'w', encoding="utf-8") as buffer_file:
            json.dump(input_data, buffer_file)

        clitools.run_cmd("git add " + self.target_input_file)
        clitools.run_cmd("git commit -m 'Update'")

        clitools.run_cmd("git push")

    def _read_inbuffer(self):
        message = None

        os.chdir(self.git_repo_path)
        clitools.run_cmd("git remote update")
        upstream_branch = clitools.run_cmd("git for-each-ref --format='%(upstream:short)' $(git symbolic-ref -q HEAD)")
        clitools.run_cmd("git reset --hard " + upstream_branch)

        try:
            with open(self.target_input_file, 'r', encoding="utf-8") as buffer_file:
                input_data = json.load(buffer_file)

            if input_data["message_id"] > self.last_message_input_id:
                self.last_message_input_id = input_data["message_id"]
                message = input_data["message"]
        except Exception as exception:
            print("error while reading in buffer: %s" % (exception,))

        return message

    def _write_outbuffer(self, data):
        os.chdir(self.git_repo_path)

        self.last_message_output_id += 1

        output_data = {
            "message_id": self.last_message_output_id,
            "message": data
        }

        with open(self.target_ouput_file, 'w', encoding="utf-8") as buffer_file:
            json.dump(output_data, buffer_file)

        clitools.run_cmd("git add " + self.target_ouput_file)
        clitools.run_cmd("git commit -m 'Update'")

        clitools.run_cmd("git push")

    def _read_outbuffer(self):
        message = None

        os.chdir(self.git_repo_path)
        clitools.run_cmd("git remote update")
        upstream_branch = clitools.run_cmd("git for-each-ref --format='%(upstream:short)' $(git symbolic-ref -q HEAD)")
        clitools.run_cmd("git reset --hard " + upstream_branch)

        try:
            with open(self.target_ouput_file, 'r', encoding="utf-8") as buffer_file:
                output_data = json.load(buffer_file)

            if output_data["message_id"] > self.last_message_output_id:
                self.last_message_output_id = output_data["message_id"]
                message = output_data["message"]
        except Exception as exception:
            print("error while reading out buffer: %s" % (exception,))

        return message
