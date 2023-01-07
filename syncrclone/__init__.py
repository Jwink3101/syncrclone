__version__ = "20230107.0.BETA"
LASTRCLONE = "1.61.1"  # This is the last version I tested with. Does *NOT* mean it won't work further.
MINRCLONE = "1.59.0"  # Will not work prior to this

import time
import io

# Global variables (not ideal but acceptable)
DEBUG = False


def set_debug(state):
    global DEBUG
    DEBUG = state


def get_debug():
    return DEBUG


# Create a global log object
class Log:
    def __init__(self):
        self.hist = []

    def log(self, *a, **k):
        """print() to the log with date"""
        debugmode = k.pop("__debug", False)

        t = time.strftime("%Y-%m-%d %H:%M:%S: ", time.localtime())
        if debugmode:
            t = t + "DEBUG: "

        k0 = k.copy()
        # We want to use print() for handing of non-str objects
        # and representation. So print to io.StringIO, read it, split at \n
        # and then recombine

        k["file"] = file = io.StringIO()
        k["end"] = ""
        print(*a, **k)

        lines = file.getvalue().split("\n")
        lines = [t + line for line in lines]

        if debugmode and not DEBUG:  # Save it in case of error but do not print
            self.hist.extend((False, line) for line in lines)
            return

        for line in lines:
            self.hist.append((True, line))
            print(line, **k0)

    __call__ = log

    def clear(self):
        self.hist.clear()

    def dump(self, path, mode="wt"):
        log("---- END OF LOG ----")
        with open(path, mode) as file:
            file.write("\n".join(line for t, line in self.hist if t))


log = Log()


def debug(*a, **k):
    k["__debug"] = True
    log(*a, **k)


from . import cli
from . import main
