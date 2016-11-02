import time

from communication import TCPServerSocket
from src.logging_ import default_logger
from client import Client
from structure import Project


class Server:
    def __init__(self):
        self.server_socket = TCPServerSocket(1299, self.__accept_connection)
        self.clients = []
        self.__projects = {}

        default_logger.ptc = True

    def __accept_connection(self, sock, host):
        c = Client(self, sock, host)
        self.clients.append(c)
        c.socket.on_close_notifier.add_observer(self.__remove_client)

    def __remove_client(self, client: Client):
        self.clients.remove(client)

    def broadcast(self, json_):
        for client in self.server_socket.clients:
            client.send(json_, locked=False, await_response=False)

    def stop(self):
        self.server_socket.stop()

    def add_project(self, project:Project):
        self.__projects[project.get_id()] = project

    def get_project_by_id(self, id):
        return self.__projects[id]


if __name__ == "__main__":
    s = Server()
    try:
        while True:
            time.sleep(10000)
    except KeyboardInterrupt:
        pass
    s.stop()
