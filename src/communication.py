import json
import select
import socket
import threading
import time
from abc import abstractmethod

from notifier import Notifier

from logging_ import log, default_logger


def none_function(*args, **kw): pass


# library classes >>>>>>>>>
# set up a server socket
# on_connect is a function and must accept the created peer socket and it's host
class TCPServerSocket:
    def __init__(self, port, on_connect):
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("", self.port))
        self.socket.listen(1)

        self.comm_lock = threading.Lock()

        self.on_connect = on_connect
        self.running = True
        self.accept_new = True

        self.listener_thread = threading.Thread(target=self.wait_for_connection)
        self.listener_thread.start()

        self.clients = []

    def __log(self, s):
        log(s, prefix="Server Socket")

    # wait for incoming connections on the server socket
    # and accept them if accept_new == True
    def wait_for_connection(self):
        while self.running:
            x, y, z = select.select([self.socket], [], [], 1)
            if len(x) > 0 and self.accept_new:
                peer_socket, (host, port) = self.socket.accept()
                self.__log("Connection to %s:%s successful!" % (host, port))
                peer_socket_wrapper = JSONSocketWrapper(peer_socket)

                def disconnect_socket_helper():
                    self.clients.remove(peer_socket_wrapper)

                peer_socket_wrapper.on_close_notifier.add_observer(disconnect_socket_helper)
                self.clients.append(peer_socket_wrapper)
                self.on_connect(peer_socket_wrapper, peer_socket, host)

    # stop running and close socket
    def stop(self):
        self.running = False
        self.listener_thread.join()
        self.socket.close()
        for client in self.clients:
            client.stop_listening()
        return True

    # define if the server should accept incoming connections or let them wait
    def set_accepting(self, accept):
        self.accept_new = True


class SocketWrapper:
    def __init__(self, sock, prefix="SocketWrapper", start_listening=True):
        self.__prefix = prefix
        self.__socket = sock
        # socket.send() and socket.recv() don't block but throw an error or return False
        self.__socket.setblocking(False)
        self.__running = False
        self.__locks = {}

        self.on_close_notifier = Notifier()

        if start_listening:
            self.start_listening()

    def close_socket(self):
        self.on_close_notifier.notify()
        self.__socket.close()

    def __del__(self):
        self.stop_listening()
        self.close_socket()

    def _log(self, s):
        log(s, prefix=self.__prefix)

    def start_listening(self):
        self.__running = True
        threading.Thread(target=self._wait_for_data).start()

    def stop_listening(self):
        self.__running = False

    def unlock_key(self, key: str):
        try:
            self.__locks[key].release()
        except AttributeError as e:
            self._log("No such lock: " + str(key))
            self._log(e)
        except Exception as e:
            self._log(e)

    # Returns True if there is callback data, False if there isn't.
    # throws error if disconnected
    # set timeout if it differs from std timeout max_wait_timeout
    # locked=False: do not acquire lock and do not release lock
    def _send(self, data: bytes, lock_key: str = None, error_handling: bool = True):
        if lock_key:
            if lock_key not in self.__locks:
                self.__locks[lock_key] = threading.Lock()
            self.__locks[lock_key].acquire()
        try:
            self.__socket.send(data)
            self.last_send_time = time.time()
            # self.server.logger..log('Answered to %s%s' % (self.prefix,json))
        except Exception as e:
            self._log(e)
            if not error_handling:
                raise Exception("Error sending json: %s" % str(e))  # used to break the infinite wait_for_data loop
        '''
        try:
            if lock_key:
                self.__locks[lock_key].release()
        except Exception as e2:
            self._log(e2)
            if not error_handling:
                raise Exception(
                    "Error sending json (lock release): %s" % str(e2))  # used to break the infinite wait_for_data loop
        '''

    # receive from a socket as long as there is data to be received
    def _receive(self, packet_size=4096, error_handling=True):
        data = b''
        try:
            while True:
                (rlist, x, y) = select.select([self.__socket], [], [], 0)
                if len(rlist) > 0:
                    chunk = self.__socket.recv(packet_size)
                    if not chunk:
                        self._log("socket.recv is None or False")
                        self.close_socket()
                        break
                    data += chunk
                else:
                    # select poll doesn't find anything --> no more data left on socket
                    break
        except Exception as e:
            self._log(e)
            if not error_handling:
                raise e
        return data

    def _wait_for_data(self):
        self._log("Waiting for data...")
        connected = True
        while connected and self.__running:
            read_list = []
            try:
                (read_list, x, y) = select.select([self.__socket], [], [], 15)
            except Exception as e:
                self._log(e)
                self._log("Stopping wait_for_data() due to error")
                connected = False
                self.close_socket()
            if len(read_list) > 0:
                try:
                    data = self._receive(error_handling=False)
                    if data:
                        self._handle_data(data)
                except Exception as e:  # socket has been closed
                    self._log("Stopping wait_for_data()... has the socket been closed?")
                    self._log(e)
                    connected = False
                    self.close_socket()
        self.__running = False

    @abstractmethod
    def _handle_data(self, data: bytes):
        pass


class JSONSocketWrapper(SocketWrapper):
    def __init__(self, sock, prefix="JSONSocketWrapper"):
        super().__init__(sock, prefix=prefix)
        self.__json_stream = bytes()
        self.__data_handling_lock = threading.Lock()

        # is only called if the command is a response
        self.response_notifier = Notifier()
        # is only called if the command is not a response
        self.new_command_notifier = Notifier()

    def _handle_data(self, data: bytes):
        try:
            def eliminate_pings(json_):
                while True:
                    if "}PING" in json_:
                        self._send(bytes("PONG"))
                        self._log("----- received PING ------")
                        json_ = json_.replace("}PING", "}")
                    elif "PING{" in json_:
                        self._send(bytes("PONG"))
                        self._log("----- received PING ------")
                        json_ = json_.replace("PING{", "{")
                    else:
                        break
                return json_

            with self.__data_handling_lock:
                self.__json_stream += data
                json_stream_string = self.__json_stream.decode()
                json_stream_string = eliminate_pings(json_stream_string)
                index = json_stream_string.find("}{")
                if index >= 0:
                    json_package = json_stream_string[:(index + 1)]
                else:
                    json_package = json_stream_string
                try:
                    json_data = json.loads(str(json_package))
                    if index > -1:
                        self.__json_stream = self.__json_stream[(index + 1):]
                    else:
                        self.__json_stream = bytes()
                    command_type = json_data["type"]
                    if command_type[0] == "_" and command_type[-1] == "_":
                        self.response_notifier.notify(event_data=json_data)
                    else:
                        self.new_command_notifier.notify(event_data=json_data)
                except json.JSONDecodeError as e:
                    self._log("Warning: JSON could not be decoded yet.")
                    self._log(e)
                    self._log(self.__json_stream)
        except Exception as e:
            self._log(e)
            self._log("FATAL EXCEPTION IN _handle_data()")
            raise e

    def _wait_for_response(self, command_type: str, timeout: int = None):
        end_time = (time.time() + timeout) if timeout is not None else None
        response = None
        while True:
            json_command = self.response_notifier.wait(timeout=timeout)
            if "type" in json_command and json_command["type"] == "_" + command_type + "_":
                response = json_command
                break
            else:
                if end_time is not None and time.time() > end_time:
                    break
                time.sleep(0.01)
        return response

    def __json_to_bytes(self, json_command: dict):
        return json.dumps(json_command).encode("utf-8")

    def communicate_json(self, json_command: dict, lock_key: str = None, timeout: int = None):
        if lock_key is None:
            lock_key = json_command["type"]
        data = self.__json_to_bytes(json_command)
        self._send(data, lock_key=lock_key)
        self._log("sent data")
        response = self._wait_for_response(json_command["type"], timeout=timeout)
        self._log("end wait for response")
        self.unlock_key(lock_key)
        return response

    def push_json(self, json_response: dict):
        data = self.__json_to_bytes(json_response)
        self._send(data)


# a small library test
if __name__ == "__main__":
    server_wrapper = None

    global default_logger
    default_logger.ptc = True


    def on_command_server_side(cmd: dict):
        global server_wrapper
        cmd["type"] = "_" + cmd["type"] + "_"
        time.sleep(1)
        server_wrapper.push_json(cmd)


    def on_connect(wrapper: JSONSocketWrapper, s, h):
        global server_wrapper
        wrapper.new_command_notifier.add_observer(on_command_server_side)
        server_wrapper = wrapper


    def do_client_command(json_data, delay):
        time.sleep(delay)
        print("Making command: " + str(json_data))
        response = client.communicate_json(json_data)
        print(json_data, " ---> ", response)


    port = 12457

    server = TCPServerSocket(port, on_connect)

    client_socket = socket.socket()
    client_socket.connect(("localhost", port))
    client = JSONSocketWrapper(client_socket, prefix="Client")
    threading.Thread(target=lambda: do_client_command({"type": "test"}, 0)).start()
    threading.Thread(target=lambda: do_client_command({"type": "test2", "add": "test"}, 0.5)).start()
    time.sleep(10)
    client.stop_listening()
    server.stop()
