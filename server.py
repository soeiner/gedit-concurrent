import threading

import time

from client_handler import ClientHandler
from communication import TCPServerSocket
from logging_ import default_logger, log


class Server:
    def __init__(self):
        self.server_socket = TCPServerSocket(1299, self.accept_connection)
        self.clients = []

        default_logger.ptc = True

        self.rev_counter = 0
        self.content = ""
        self.change_lock = threading.Lock()
        self.content_revisions = {}
        self.revision_commands = {}

    def accept_connection(self, sock, host):
        c = ClientHandler(self, sock, host)
        self.clients.append(c)

    def change_content(self, change_command):
        self.change_lock.acquire()

        try:
            changed_rev_id = change_command["rev_id"]
            changed_index = change_command["index"]

            current_rev_id = self.rev_counter
            revs = current_rev_id - changed_rev_id  # revs = 1
            print("================")
            for i in range(1, revs + 1):
                between_rev = self.revision_commands["rev" + str(changed_rev_id + i)]
                print(between_rev)
                if between_rev["action"] == "insert":
                    if between_rev["index"] < changed_index:
                        changed_index += len(between_rev["value"])
                elif between_rev["action"] == "delete":
                    if between_rev["index"] < changed_index:
                        changed_index += between_rev["amount"]
                    elif between_rev["index"] - between_rev["amount"] < changed_index:
                        changed_index = between_rev["index"] - between_rev["amount"]
            print("::::::::::::::::")

            change_command["index"] = changed_index
            new_content = ""
            left = self.content[:changed_index]
            right = self.content[changed_index:]
            print(change_command)
            if change_command["action"] == "insert":
                new_content = left + change_command["value"] + right
            elif change_command["action"] == "delete":
                print(change_command["amount"])
                new_content = left[:(len(left) - change_command["amount"])] + right
            self.content = new_content
            print(new_content)

            self.rev_counter += 1
            self.revision_commands["rev" + str(self.rev_counter)] = change_command
            self.content_revisions["rev" + str(self.rev_counter)] = self.content
            print("REVISION " + str(self.rev_counter))
            print(revs)
            print("\n")
        except Exception as exc:
            log(exc)

        self.change_lock.release()

    def broadcast(self, json_):
        for client in self.server_socket.clients:
            client.send(json_, locked=False, await_response=False)

    def stop(self):
        self.server_socket.stop()


s = Server()
try:
    while True:
        time.sleep(10000)
except KeyboardInterrupt:
    pass
except Exception as e:
    print("Stopped")
    print(e)
s.stop()
