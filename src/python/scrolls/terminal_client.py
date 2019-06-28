import sys
import socket


HOST = '127.0.0.1'
PORT = 9000
DATA = 'AAAAAAAAAA'


def udp_client(command_to_send, answer_handler_callback=None):
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.sendto(command_to_send.encode(), (HOST, PORT))
    data, addr = client.recvfrom(4096)
    # print("%s %s\n" % (data, addr))
    if answer_handler_callback is not None:
        answer_handler_callback(data)


def show_commands_output(cmd_output):
    cmd_output = cmd_output.decode("utf8")
    print(cmd_output)


def parse_command_input(command_input):
    if command_input != "quit" and command_input[0:2] not in ['cd', 'ls']:
        command_input = "exec " + command_input

    return command_input


def command_loop():
    command_input = ""
    while command_input != "quit":
        command_input = input(">> ")
        command_to_send = parse_command_input(command_input)
        udp_client(command_to_send, show_commands_output)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        command_loop()
        exit()

    command_to_send = DATA
    if len(sys.argv) > 1:
        command_to_send = sys.argv[1]

    udp_client(command_to_send, show_commands_output)
