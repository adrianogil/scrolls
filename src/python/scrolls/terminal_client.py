import argparse

from scrolls.comm.udp import build_udp_channel

HOST = '10.37.129.2'
PORT = 9000
DATA = 'AAAAAAAAAA'


def udp_client(command_to_send, answer_handler_callback=None, channel=None):
    channel = channel or build_udp_channel()
    data = channel.send_command(command_to_send, target_host=HOST, target_port=PORT)
    if answer_handler_callback is not None:
        answer_handler_callback(data)


def show_commands_output(cmd_output):
    cmd_output = cmd_output.decode("utf8")
    print(cmd_output)


def parse_command_input(command_input):
    if command_input != "quit" and command_input[0:2] not in ['cd', 'ls']:
        command_input = "exec " + command_input

    return command_input


def command_loop(channel=None):
    command_input = ""
    while command_input != "quit":
        command_input = input(">> ")
        command_to_send = parse_command_input(command_input)
        udp_client(command_to_send, show_commands_output, channel=channel)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scrolls authenticated UDP client")
    parser.add_argument("command", nargs="?")
    parser.add_argument("--udp-key-file")
    parser.add_argument("--udp-legacy", action="store_true")
    options = parser.parse_args(argv)
    channel_args = []
    if options.udp_key_file:
        channel_args.extend(["--udp-key-file", options.udp_key_file])
    if options.udp_legacy:
        channel_args.append("--udp-legacy")
    channel = build_udp_channel(channel_args)

    if options.command is None:
        command_loop(channel=channel)
        return 0

    udp_client(options.command or DATA, show_commands_output, channel=channel)
    return 0


if __name__ == '__main__':
    main()
