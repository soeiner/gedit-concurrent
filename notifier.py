# A very simple implementation of the Observer pattern using functions as observers
# With this implementation, subject classes can have multiple notifiers
import threading


class Notifier:
    def __init__(self):
        self.observers = []

    # add or remove state change listener functions
    def add_observer(self, func, *args):
        self.observers.append((func, args))

    def remove_observer(self, func, *args):
        try:
            if args:
                self.observers.remove((func, args))
            else:
                for (f, a) in self.observers:
                    if f == func:
                        self.observers.remove((f, a))
            return True
        except Exception as e:
            return False

    # notify all observers
    def notify(self):
        for (func, args) in self.observers:
            threading.Thread(None, func, None, args).start()
