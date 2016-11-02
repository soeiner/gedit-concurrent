import json

from communication import SocketHelper
from structure import Project


class Client:
    def __init__(self, server, raw_socket, host):
        self.server = server
        self.host = host
        self.raw_socket = raw_socket
        self.socket = SocketHelper(raw_socket)

        self.socket.wait_for_data(self.__on_receive)

    def __del__(self):
        del self.socket

    def __change_file(self, project_id: int, file_id: int, data: dict):
        project = self.server.get_project_by_id(project_id)
        file_ = project.get_file_by_id(file_id)
        return file_.change_content(data, self)

    def __on_receive(self, data):
        type_ = data["type"]
        if type_ == "create_project":
            name = data["name"]
            self.server.add_project(Project(self, name))
            return True
        if type_ == "change":
            project_id = data["project_id"]
            file_id = data["file_id"]
            rev_id = self.__change_file(project_id, file_id, data)
            answer = {"type": "_change_"}
            if rev_id:
                answer["rev_id"] = rev_id
            return answer
        elif type_ == "get_content":
            return json.dumps({
                "type": "_get_content_",
                "content": self.server.content
            })
            # no callback to be send
