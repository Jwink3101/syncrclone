__version__ = '20210720.0.BETA'

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
    
    def log(self,*a,**k):
        t = time.strftime("%Y-%m-%d %H:%M:%S:", time.localtime())
        a = [t] + list(a)
        
        file0 = k.pop('file',None)
        
        file = io.StringIO()
        k['file'] = file
        print(*a,**k)
        self.hist.append(file.getvalue())
        
        del k['file']
        if file0:
            k['file'] = file0
        print(*a,**k)    
    __call__ = log
    
    def clear(self):
        self.hist = []

    def dump(self,path,mode='wt'):
        log('---- END OF LOG ----')
        with open(path,mode) as file:
            file.write(''.join(self.hist))
    
log = Log()

def debug(*args,**kwargs):
    if not DEBUG:
        return
    args = ('DEBUG:',) + args
    log(*args,**kwargs)

from . import cli
from . import main
