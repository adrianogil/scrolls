import os
import socket

BIND_IP = '0.0.0.0'
BIND_PORT = 9000


def udp_server(data_handler_callback=None):
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((BIND_IP, BIND_PORT))
    print("Waiting on port: " + str(BIND_PORT))

    while 1:
        data, addr = server.recvfrom(1024)
        print(addr)
        answer = 'ACK'
        if data_handler_callback is not None:
            answer = data_handler_callback(data)

        server.sendto(answer.encode(), addr)


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

    return answer



if __name__ == '__main__':
    udp_server(command_handler)
