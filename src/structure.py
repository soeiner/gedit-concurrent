import threading
from logging_ import log
from notifier import Notifier


class File:
    __file_counter = 0

    def __init__(self, project):
        """ :type project: Project """
        self.__project = project

        self.__rev_counter = 0
        self.__content = ""
        self.__change_lock = threading.Lock()
        self.__content_revisions = {}
        self.__revision_commands = {}

        self.change_notifier = Notifier()

        self.__id = self.__file_counter
        self.__file_counter += 1
        print("file id", self.__id)

    def get_id(self):
        return self.__id

    def change_content(self, change_command, client):
        """
        revision based file content change
        :type change_command: dict
        """
        self.__change_lock.acquire()

        try:
            base_rev_id = change_command["base_rev_id"]
            changed_index = change_command["index"]

            current_rev_id = self.__rev_counter
            revs = current_rev_id - base_rev_id  # revs = 1
            log("================")
            for i in range(1, revs + 1):
                between_rev = self.__revision_commands["rev" + str(base_rev_id + i)]
                log(between_rev)
                if between_rev["action"] == "insert":
                    if between_rev["index"] < changed_index:
                        changed_index += len(between_rev["value"])
                elif between_rev["action"] == "delete":
                    if between_rev["index"] < changed_index:
                        changed_index += between_rev["amount"]
                    elif between_rev["index"] - between_rev["amount"] < changed_index:
                        changed_index = between_rev["index"] - between_rev["amount"]
            log("::::::::::::::::")

            change_command["index"] = changed_index
            new_content = ""
            left = self.__content[:changed_index]
            right = self.__content[changed_index:]
            log(change_command)
            if change_command["action"] == "insert":
                new_content = left + change_command["value"] + right
            elif change_command["action"] == "delete":
                log(change_command["amount"])
                new_content = left[:(len(left) - change_command["amount"])] + right
            self.__content = new_content
            log(new_content)

            self.__rev_counter += 1
            self.__revision_commands["rev" + str(self.__rev_counter)] = change_command
            self.__content_revisions["rev" + str(self.__rev_counter)] = self.__content
            log("REVISION " + str(self.__rev_counter))
            log(revs)
            log("\n")
        except Exception as exc:
            log(exc)
            print("Error applying revision changes.")

        self.__change_lock.release()
        return self.__rev_counter


class Project:
    __project_counter = 0

    def __init__(self, administrator, name):
        self.administrator = administrator
        self.name = name
        self.collaborators = []
        self.files = {}

        self.__id = self.__project_counter
        self.__project_counter += 1
        print("project id", self.__id)

    def get_id(self):
        return self.__id

    def get_file_by_id(self, id: int) -> File:
        return self.files[id]

    def add_file(self, file_: File):
        self.files[file_.get_id()] = file_
