__version__ = '20211015.0.BETA'
LASTRCLONE = '1.56.2' # This is the last version I tested with. Does *NOT* mean it won't work further.

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
        debugmode = k.pop('__debug',False)
        
        t = time.strftime("%Y-%m-%d %H:%M:%S:", time.localtime())
        a = [t] + list(a)
        
        file0 = k.pop('file',None)
        
        file = io.StringIO()
        k['file'] = file
        print(*a,**k)
        val = file.getvalue()
        if not debugmode or DEBUG:
            self.hist.append((True,val))
        else:
            self.hist.append((False,val))
            return
        
        del k['file']
        if file0:
            k['file'] = file0
        print(*a,**k)    
    __call__ = log
    
    def clear(self):
        self.hist.clear()
 

    def dump(self,path,mode='wt'):
        log('---- END OF LOG ----')
        with open(path,mode) as file:
            file.write(''.join(line for t,line in self.hist if t))
    
log = Log()

def debug(*args,**kwargs):
    kwargs['__debug'] = True
    args = ('DEBUG:',) + args
    log(*args,**kwargs)

from . import cli
from . import main
