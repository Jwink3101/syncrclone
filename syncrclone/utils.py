import datetime
import random
import string
import os

from . import log,debug

def random_str(N=10):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(N))

def RFC3339_to_unix(timestr):
    """
    Parses RFC3339 into a unix time
    """
    d,t = timestr.split('T')
    year,month,day = d.split('-')
    
    t = t.replace('Z','-00:00') # zulu time
    t = t.replace('-',':-').replace('+',':+') # Add a new set
    hh,mm,ss,tzhh,tzmm = t.split(':')
    
    offset = -1 if tzhh.startswith('-') else +1
    tzhh = tzhh[1:]
    
    try:
        ss,micro = ss.split('.')
    except ValueError:
        ss = ss
        micro = '00'
    micro = micro[:6] # Python doesn't support beyond 999999
    
    dt = datetime.datetime(int(year),int(month),int(day),
                           hour=int(hh),minute=int(mm),second=int(ss),
                           microsecond=int(micro))
    unix = (dt - datetime.datetime(1970,1,1)).total_seconds()
    
    # Account for timezone which counts backwards so -=
    unix -= int(tzhh)*3600*offset
    unix -= int(tzmm)*60*offset
    return unix


def add_hash_compare_attribute(*filelists):
    """
    Tool to generate a hash attribute that accounts for choosing a
    common hash that can be queried. Needs to account for:

    * Some lists have different hashes. Maybe rclone added a new hash type
      and this is a local remote?
    
    * Not all files will have all hashes. This can happen to S3 files that
      do not get a final hash (I think. I've yet to see it)
    
    Inputs:
    ------
    filelist1,filelist2,...,filelistN
        DictTable filelists
      
    """
    # Two loops through but still O(N)
    hashnames = set()
    for filelist in filelists:
        for file in filelist:
            for hashname in file.get('Hashes',{}).keys():
                hashnames.add(hashname)
    
    for hashname in ['SHA-1','MD5','Whirlpool','CRC-32','DropboxHash','MailruHash','QuickXorHash']:
        if hashname in hashnames:
            common_hash = hashname
            break
    else:
        raise ValueError('Could not find common hash')
        
    for filelist in filelists:
        for file in filelist:
            hashval = file.get('Hashes',{}).get(common_hash,None)
            if hashval:
                file['common_hash'] = hashval
        
        filelist.add_fixed_attribute('common_hash',force=False) # Will cause it to reindex. Force stops it from mattering if it is dynamic
    
def bytes2human(byte_count,base=1024,short=True):
    """
    Return a value,label tuple
    """
    if base not in (1024,1000):
        raise ValueError('base must be 1000 or 1024')
    
    labels = ['kilo','mega','giga','tera','peta','exa','zetta','yotta']
    name = 'bytes'
    if short:
        labels = [l[0] for l in labels]
        name = name[0]
    labels.insert(0,'') 
    
    best = 0
    for ii in range(len(labels)): 
        if (byte_count / (base**ii*1.0)) < 1:
            break
        best = ii
    
    return byte_count / (base**best*1.0),labels[best] + name  

def file_summary(files):
    N = len(files)
    s = sum(f['Size'] for f in files if f)
    s = bytes2human(s)
    return f"{N:d} files, {s[0]:0.2f} {s[1]:s}"    

def unix2iso(mtime):
    if not mtime:
        return 'None'
    return datetime.datetime.fromtimestamp(float(mtime)).strftime('%Y-%m-%d %H:%M:%S')    
        
        
def search_upwards(pwd):
    """
    Search upwards for `.syncrclone/config.py`        
    """
    pwd = pwd = os.path.abspath(pwd)
    configpwd = os.path.join(pwd,'.syncrclone','config.py')
    debug(f"Looking for config in '{pwd}'")
    if os.path.exists(configpwd):
        return configpwd
    
    newpwd = os.path.dirname(pwd) # go upwards but if this doesn't change, then break
    if newpwd == pwd:
        return 
    return search_upwards(newpwd)
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
