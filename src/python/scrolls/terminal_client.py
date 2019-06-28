import sys
import socket


HOST = '127.0.0.1'
PORT = 9000
DATA = 'AAAAAAAAAA'


def udp_client(command_to_send):
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.sendto(command_to_send.encode(), (HOST, PORT))
    data, addr = client.recvfrom(4096)
    print("%s %s" % (data, addr))


if __name__ == '__main__':
    command_to_send = DATA
    if len(sys.argv) > 1:
        command_to_send = sys.argv[1]

    udp_client(command_to_send)
