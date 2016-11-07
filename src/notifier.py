import threading


class Notifier:
    def __init__(self):
        """
        A very simple implementation of the Observer pattern using functions as observers
        :rtype: Notifier
        """
        self.__observers = []

        self.notify_lock = threading.Lock()
        self.wait_completion_lock = threading.Lock()
        self.notify_event = threading.Event()

        self.last_event_data = None

    # add or remove state change listener functions
    def add_observer(self, function):
        self.__observers.append(function)

    def remove_observer(self, function):
        self.__observers.remove(function)

    # notify all observers
    def notify(self, event_data: dict = None, join_threads: bool = False):
        with self.notify_lock:
            threads = []
            for function in self.__observers:
                if event_data:
                    t = threading.Thread(target=lambda:function(event_data))
                else:
                    t = threading.Thread(target=function)
                threads.append(t)
                t.start()

            self.last_event_data = event_data
            self.notify_event.set()
            # wait for the threads that called wait()
            self.wait_completion_lock.acquire()
            self.wait_completion_lock.release()
            self.notify_event.clear()

        if join_threads:
            for t in threads:
                t.join()

    def wait(self, timeout: int = None):
        with self.wait_completion_lock:
            self.notify_event.wait(timeout=timeout)
            return self.last_event_data
