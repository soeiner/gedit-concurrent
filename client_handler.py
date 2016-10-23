import json

from communication import SocketHelper


class ClientHandler:
    def __init__(self, server, raw_socket, host):
        self.server = server
        self.raw_socket = raw_socket
        self.host = host
        self.socket = SocketHelper(raw_socket)
        self.socket.wait_for_data(self.on_receive)

    def on_receive(self, data):
        type_ = data["type"]
        if type_ == "change":
            self.server.change_content(data)
            return False
        elif type_ == "get_content":
            return json.dumps({
                "type": "_get_content_",
                "content": self.server.content
            })
        # no callback to be send

