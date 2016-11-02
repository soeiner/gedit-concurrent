import json
import select
import socket
import threading
import time

from notifier import Notifier

from src.logging_ import Logger, log


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

    # wait for incoming connections on the server socket
    # and accept them if accept_new == True
    def wait_for_connection(self):
        while self.running:
            x, y, z = select.select([self.socket], [], [], 1)
            if len(x) > 0 and self.accept_new:
                peer_socket, (host, port) = self.socket.accept()
                print("Connection to %s:%s successful!" % (host, port))
                peer_socket_helper = SocketHelper(peer_socket)

                def disconnect_socket_helper():
                    self.clients.remove(peer_socket_helper)

                peer_socket_helper.on_close_notifier.add_observer(disconnect_socket_helper)
                self.clients.append(peer_socket_helper)
                self.on_connect(peer_socket, host)

    # stop running and close socket
    def stop(self):
        self.running = False
        self.listener_thread.join()
        self.socket.close()
        for client in self.clients:
            client.socket.close()
        return True

    # define if the server should accept incoming connections or let them wait
    def set_accepting(self, accept):
        self.accept_new = True


# manages error handling, logging and lock for a socket
# can be used on both master and slave ends of a socket
class SocketHelper:
    def __init__(self, socket, retry_count=0, prefix="SocketHelper", logger=None, max_select_timeout=5):
        if logger is None:
            self.logger = Logger()
        else:
            self.logger = logger
            # self.server.logger. = logger
        self.prefix = prefix  # Logging prefix for console output
        self.retry_count = retry_count  # sending retry count
        self.socket = socket
        self.socket.setblocking(False)  # socket.send() and socket.recv() don't block but throw an error or return False
        self.lock = threading.Lock()
        self.default_select_timeout = self.max_select_timeout = max_select_timeout

        self.on_close_notifier = Notifier()
        self.unresponsive_notifier = Notifier()

        self.responsive = True
        self.unresponsive_times = 0
        self.waiting = False

        self.last_send_time = 0

        # self.server.logger..log("%s created."%self.prefix)

    def __del__(self):
        self.stop_waiting_for_data()
        self.socket.close()

    def log(self, s):
        log(s, prefix=self.prefix)

    # receive from a socket as long as there is data to be received
    def read_(self, packet_size=4096, error_handling=True):
        data = b''
        try:
            while True:
                (rlist, x, y) = select.select([self.socket], [], [], 0)
                if len(rlist) > 0:
                    chunk = self.socket.recv(packet_size)
                    if not chunk:
                        self.log("socket.recv is None or False")
                        self.on_close_notifier.notify()
                        self.socket.close()
                        break
                    data += chunk
                else:
                    # select poll doesn't find anything --> no more data left on socket
                    break
        except Exception as e:
            self.log("read_ error")
            self.log(e)
            if error_handling:
                return False
            else:
                raise e
        return data.decode("utf-8")

    # puts send() and receive() cleanly together in one communication operation
    # try to use communicate() in every case, instead of send() + receive()
    # Sends json to the peer, returns received data or True or False
    # response timeout in seconds, default:self.max_wait_timeout
    def communicate(self, json_string, timeout=None):
        for i in range(self.retry_count + 1):
            try:
                send_successful = self.send(json_string, tmt=timeout)
            except Exception as e:
                self.log(e)
                self.log("apparently DISCONNECTED")
                self.on_close_notifier.notify()
                send_successful = False
            if send_successful:
                cb = self.process_callback(self.receive())
                if cb:
                    # the client regains responsivity when it responses one time after not responding for many times
                    self.unresponsive_times = 0
                    self.responsive = True
                    self.max_select_timeout = self.default_select_timeout
                    return cb
            else:
                self.log(" did not respond at: " + str(json_string))
                if self.responsive:
                    self.unresponsive_times += 1
                    # means that the client did not response at 3 different commands --> unresponsive
                    if self.unresponsive_times > (2.5 * self.retry_count):
                        self.responsive = False
                        self.log(" unresponsive!!!")
                        self.unresponsive_notifier.notify()
                else:
                    return False
        return False

    # infinite loop listening on the socket via select
    # on_receive: handler function, must accept json data
    def wait_for_data(self, on_receive):
        self.log("Waiting for data...")
        try:
            self.lock.release()
        except Exception as e:
            self.logger.log("[SocketHelper.wait_for_data] " + str(e))
            pass
        connected = True
        self.waiting = True
        while connected and self.waiting:
            self.lock.acquire()
            rlist = []
            try:
                (rlist, x, y) = select.select([self.socket], [], [], 15)
            except Exception as e:
                self.log(e)
                self.log("Stopping wait_for_data() due to error")
                connected = False
                self.on_close_notifier.notify()
            if len(rlist) > 0:
                try:
                    data = self.receive(locked=False)
                    if data and on_receive:
                        response = on_receive(data)
                        if isinstance(response, bool):
                            answer = {"type": "_" + data["type"] + "_", "success": response}
                            self.send(answer, locked=False, await_response=False)
                        elif response:
                            self.send(response, locked=False, await_response=False)
                except Exception as e:  # --> socket has been closed --> break
                    self.on_close_notifier.notify()
                    self.log("Stopping wait_for_data() due to error 2")
                    self.log(e)
                    connected = False
            self.lock.release()
        self.waiting = False

    def stop_waiting_for_data(self):
        self.waiting = False

    # Returns True if there is callback data, False if there isn't.
    # throws error if disconnected
    # set timeout if it differs from std timeout max_wait_timeout
    # locked=False: do not acquire lock and do not release lock
    def send(self, json, tmt=None, locked=True, await_response=True):
        if locked:
            self.lock.acquire()
        self.read_()  # clear socket
        try:
            self.socket.send(json)
            self.last_send_time = time.time()
            # self.server.logger..log('Answered to %s%s' % (self.prefix,json))
        except Exception as e:
            self.log(e)
            try:
                if locked:
                    self.lock.release()
            except Exception as e2:
                self.log(e2)
            raise Exception("Error sending json: %s" % str(e))  # used to break the infinite wait_for_data loop
        if await_response:
            # wait for callback info, tmt seconds
            if not tmt:
                tmt = self.max_select_timeout
            (sread, x, y) = select.select([self.socket], [], [], tmt)
            if len(sread) > 0:
                # self.server.logger..log('%sresponses...' % self.prefix)
                # received callback from the client. NOT releasing lock, maybe data must be received first
                return True
            else:
                self.log('%s Timeout expired, did not response...' % self.prefix)
                # received no callback info after self.max_wait_timeout seconds
                try:
                    if locked:
                        self.lock.release()
                except Exception as e:
                    self.logger.log(e)
                    pass
                return False
        else:
            return True

    # used in combination with self.send() and self.process_callback(), receives everything and decodes it
    # returns True, False or data
    # locked=False: do not release lock
    def receive(self, locked=True):
        def eliminate_pings(json_):
            while True:
                if "}PING" in json_:
                    self.send("PONG", locked=False, await_response=False)
                    self.logger.log("----- received PING ------")
                    json_ = json_.replace("}PING", "}")
                if "PING{" in json_:
                    self.send("PONG", locked=False, await_response=False)
                    self.logger.log("----- received PING ------")
                    json_ = json_.replace("PING{", "{")
                else:
                    break
            return json_

        def cut_last_message(json_):
            if isinstance(json_, str) and "}{" in json_:
                self.log("FATAL FATAL FATAL FATAL FATAL FATAL FATAL FATAL FATAL")
                self.log("}{ was found in json_, which means that we tried sending"
                         " two commands too close to each other (locking failure).")
                while True:
                    self.logger.log("while in decode_json")
                    index = json_.find("}{")
                    if index > -1:
                        # json__ = json_[:(index + 1)]
                        # cb = self.process_callback(json__)
                        json_ = json_[(index + 1):]
                    else:
                        # cb = self.process_callback(json_)
                        break
            return json_

        decoding = True
        data = None
        j = ""
        while decoding:
            select.select([self.socket], [], [], 1)
            chunk = self.read_()
            if chunk:
                j += chunk
            else:
                self.log("empty chunk --> break while")
                decoding = False
            if '"' not in j:
                j.replace("'", '"')
            if len(j) > 0:
                try:
                    data = json.loads(j)
                    decoding = False
                except Exception as e:
                    self.log("JSON not yet decodable")
                    j = eliminate_pings(j)
                    self.log(e)
                    try:
                        j = cut_last_message(j)
                    except Exception as e:
                        self.log("Error '}{' in recv_from_client, cut_last_message")
                        self.log(e)
                        decoding = False
        if locked:
            # Releasing lock, got all the data, just processing it from now on
            try:
                self.lock.release()
            except Exception as e:
                log("release lock in socket_helper.receive() error")
                log(e)
                pass
        return data

    def process_callback(self, info):
        try:
            # process callback info
            type_ = info[u'type']
            if type_ == u'callb':
                callb = info[u'callb'][u'value']
                # self.server.logger..log('%sresponded: %s' % (self.prefix, callb))
                if callb == u'ok':
                    return True
                else:
                    return False
            if type_ == u'data':
                data = info[u'data'][u'value']
                # self.server.logger..log('%sresponded: %s' % (self.prefix, data))
                return data
            if type_ == u'error':
                c = info[u'error'][u'code']
                print("Error Code " + c)
                return False
                # add other callback types to be processed here
        except Exception as e:
            self.logger.log(e)
            # self.server.logger..log(self.prefix + "(communication.receive) Error processing callback: " + str(e))
            pass

        # Return False, not able to handle the data that was returned by the peer socket
        return False
