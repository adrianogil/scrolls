import os
import socket
import subprocess

from scrolls.comm.udp import (
    InvalidUdpPayload,
    MAX_UDP_PAYLOAD_BYTES,
    MAX_UDP_RESPONSE_BYTES,
    invalid_payload_response,
    send_udp_response,
    validate_udp_payload,
)

BIND_IP = '0.0.0.0'
BIND_PORT = 9000


def dispatch_udp_payload(
    server,
    data,
    addr,
    data_handler_callback=None,
    max_response_bytes=MAX_UDP_RESPONSE_BYTES,
):
    try:
        data = validate_udp_payload(data)
    except InvalidUdpPayload as exception:
        send_udp_response(
            server,
            invalid_payload_response(exception),
            addr,
            max_response_bytes,
        )
        return

    answer = 'ACK'
    if data_handler_callback is not None:
        answer = data_handler_callback(data)

    send_udp_response(server, answer, addr, max_response_bytes)


def udp_server(
    data_handler_callback=None,
    max_response_bytes=MAX_UDP_RESPONSE_BYTES,
):
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((BIND_IP, BIND_PORT))
    print("Waiting on port: " + str(BIND_PORT))

    while 1:
        data, addr = server.recvfrom(MAX_UDP_PAYLOAD_BYTES)
        print(addr)
        dispatch_udp_payload(
            server,
            data,
            addr,
            data_handler_callback,
            max_response_bytes,
        )


def command_handler(command_received):
    command_received = command_received.decode("utf8")
    print("Command received: %s" % (command_received,))
    answer = 'ACK'
    if command_received == "ls":
        answer = ""
        dir_content = os.listdir()
        for content in dir_content:
            answer += content + "\n"
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
        answer = "Moved to path: %s" % (next_path,)
    elif command_received[0:5] == "exec ":
        cmd = command_received[5:]
        print("Executing command: %s" % (cmd,))

        try:
            subprocess_cmd = cmd
            subprocess_output = subprocess.check_output(subprocess_cmd, shell=True)
            subprocess_output = subprocess_output.decode("utf8")
            subprocess_output = subprocess_output.strip()
            answer = subprocess_output
        except:
            answer = "ERROR: something went wrong!!!"

    return answer


if __name__ == '__main__':
    udp_server(command_handler)
