import os
import socket
import subprocess
import argparse

from scrolls.comm.udp import (
    InvalidUdpPayload,
    MAX_UDP_PAYLOAD_BYTES,
    MAX_UDP_RESPONSE_BYTES,
    ProtocolVersionError,
    UdpProtocolError,
    build_udp_channel,
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
    protocol=None,
    legacy_mode=False,
):
    if legacy_mode:
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
        request = None
    else:
        if protocol is None:
            raise ValueError("authenticated UDP dispatch requires a protocol")
        try:
            request = protocol.decode_request(data, MAX_UDP_PAYLOAD_BYTES)
        except ProtocolVersionError as exception:
            server.sendto(protocol.encode_version_error(exception, max_response_bytes), addr)
            return
        except UdpProtocolError:
            return
        data = request.payload.encode("utf-8")

    answer = 'ACK'
    if data_handler_callback is not None:
        answer = data_handler_callback(data)

    if legacy_mode:
        send_udp_response(server, answer, addr, max_response_bytes)
    else:
        server.sendto(protocol.encode_response(str(answer), request, max_response_bytes), addr)


def udp_server(
    data_handler_callback=None,
    max_response_bytes=MAX_UDP_RESPONSE_BYTES,
    protocol=None,
    legacy_mode=False,
):
    if not legacy_mode and protocol is None:
        configured_channel = build_udp_channel()
        protocol = configured_channel.protocol
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((BIND_IP, BIND_PORT))
    print("Waiting on port: " + str(BIND_PORT))

    while 1:
        data, addr = server.recvfrom(MAX_UDP_PAYLOAD_BYTES + 1)
        print(addr)
        dispatch_udp_payload(
            server,
            data,
            addr,
            data_handler_callback,
            max_response_bytes,
            protocol=protocol,
            legacy_mode=legacy_mode,
        )


def command_handler(command_received):
    command_received = command_received.decode("utf8")
    print("Command received")
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
        print("Executing command")

        try:
            subprocess_cmd = cmd
            subprocess_output = subprocess.check_output(subprocess_cmd, shell=True)
            subprocess_output = subprocess_output.decode("utf8")
            subprocess_output = subprocess_output.strip()
            answer = subprocess_output
        except:
            answer = "ERROR: something went wrong!!!"

    return answer


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scrolls authenticated UDP server")
    parser.add_argument("--udp-key-file")
    parser.add_argument("--udp-legacy", action="store_true")
    options = parser.parse_args(argv)
    channel_args = []
    if options.udp_key_file:
        channel_args.extend(["--udp-key-file", options.udp_key_file])
    if options.udp_legacy:
        channel_args.append("--udp-legacy")
    channel = build_udp_channel(channel_args)
    udp_server(
        command_handler,
        protocol=channel.protocol,
        legacy_mode=channel.legacy_mode,
    )


if __name__ == '__main__':
    main()
