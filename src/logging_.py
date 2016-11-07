import sys
import threading
import time

from notifier import Notifier

g_log_file = None
g_logger_content = ""


# The Monitoring Console for the user in the monitoring frame
class Monitor:
    def __init__(self):
        self.log_notifier = Notifier()
        self.last_line = ""
        self.line = 1
        self.buffer_ = ""
        self.log_function = None  # the function that displays or sends the logged string. Must accept a string

        self.log_lock = threading.Lock()

    def log(self, s):
        self.log_lock.acquire()
        s += "<br>"
        self.last_line = s
        # self.buffer_ += s
        threading.Thread(target=lambda: self.call_log_function(s)).start()
        self.log_notifier.notify()
        self.log_lock.release()
        return self.line

    def call_log_function(self, s):
        if self.log_function:
            try:
                self.log_function(s)
            except Exception as e:
                print("Logging Error: %s " % e)

    def get_last_line(self):
        return self.last_line

    def markup_log(self, s, tag):
        self.log("<span style='font-weight:bold;'>%s</span><span class='%s'>&nbsp;%s</span>" % (
            time.strftime("%H:%M:%S"), tag, s))

    def err_log(self, s):
        self.markup_log(s, "err_log")

    def suc_log(self, s):
        self.markup_log(s, "suc_log")

    def warn_log(self, s):
        self.markup_log(s, "warn_log")

    def info_log(self, s):
        self.markup_log(s, "info_log")

    def get_from_logger(self, logger):
        self.log(logger.last_line)


# A Debugging logger to replace the print calls - possibility to turn them off by setting Logger.ptc to False
class Logger:
    def __init__(self):
        self.ptc = False  # whether to output logging to the console
        if '--debug' in sys.argv[1:]:
            self.ptc = True
        self.log_notifier = Notifier()
        self.last_line = ""

    def get(self):
        global g_logger_content
        return g_logger_content

    def reset(self):
        pass

    def log(self, s, prefix=""):
        global g_logger_content
        global g_log_file
        prefix = str(prefix)
        if len(prefix) > 0:
            prefix = "[" + str(prefix) + "] "
        if isinstance(s, BaseException):
            e_type, e_value, e_traceback = sys.exc_info()
            traceback = {
                'type': e_type.__name__,
                'file': e_traceback.tb_frame.f_code.co_filename,
                'line': e_traceback.tb_lineno,
                'name': e_traceback.tb_frame.f_code.co_name,
            }
            del (e_type, e_value, e_traceback)
            s = str(str(traceback["file"]).split("/")[-1]) + " " + str(traceback["line"]) + ": " + str(s)
        try:
            s = time.strftime("[%H:%M:%S] ") + prefix + str(s)
            self.last_line = s
            g_logger_content += s + '\r\n'
            if self.ptc:
                print(s)
            self.log_notifier.notify()
            if g_log_file:
                f = open(g_log_file, "a")
                f.write("\r\n" + s)
                f.close()
        except Exception as e:
            print("Error in Logger.log()")
            print(e)

    def get_from_monitor(self, monitor):
        self.log(monitor.last_line)


def set_global_log_file(file_):
    global g_log_file
    g_log_file = file_


default_logger = Logger()


def log(s, prefix=""):
    default_logger.log(s, prefix=prefix)
