import threading


class Notifier:
    def __init__(self):
        """
        A very simple implementation of the Observer pattern using functions as observers
        With this implementation, subject classes can have multiple notifiers
        :rtype: Notifier
        """
        self.__observers = []

    # add or remove state change listener functions
    def add_observer(self, function):
        self.__observers.append(function)

    def remove_observer(self, function):
        self.__observers.remove(function)

    # notify all observers
    def notify(self, event_data: dict = None, join_threads: bool = False):
        threads = []
        for (function, args) in self.__observers:
            if event_data:
                t = threading.Thread(target=function, args=event_data)
            else:
                t = threading.Thread(target=function)
            threads.append(t)
            t.start()
        if join_threads:
            for t in threads:
                t.join()
