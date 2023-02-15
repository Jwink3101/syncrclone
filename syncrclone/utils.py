import datetime
import random
import string
import os
from threading import Thread

from . import log, debug


def random_str(N=10):
    return "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(N)
    )


try:
    from functools import cache as memoize
except ImportError:
    # https://wiki.python.org/moin/PythonDecoratorLibrary#Memoize
    # note that this decorator ignores **kwargs
    import functools

    def memoize(obj):
        cache = obj.cache = {}

        @functools.wraps(obj)
        def memoizer(*args, **kwargs):
            if args not in cache:
                cache[args] = obj(*args, **kwargs)
            return cache[args]

        return memoizer


def RFC3339_to_unix(timestr):
    """
    Parses RFC3339 into a unix time
    """
    d, t = timestr.split("T")
    year, month, day = d.split("-")

    t = t.replace("Z", "-00:00")  # zulu time
    t = t.replace("-", ":-").replace("+", ":+")  # Add a new set
    hh, mm, ss, tzhh, tzmm = t.split(":")

    offset = -1 if tzhh.startswith("-") else +1
    tzhh = tzhh[1:]

    try:
        ss, micro = ss.split(".")
    except ValueError:
        ss = ss
        micro = "00"
    micro = micro[:6]  # Python doesn't support beyond 999999

    dt = datetime.datetime(
        int(year),
        int(month),
        int(day),
        hour=int(hh),
        minute=int(mm),
        second=int(ss),
        microsecond=int(micro),
    )
    unix = (dt - datetime.datetime(1970, 1, 1)).total_seconds()

    # Account for timezone which counts backwards so -=
    unix -= int(tzhh) * 3600 * offset
    unix -= int(tzmm) * 60 * offset
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
    # In rclone 1.56, the hash names were changed. This is an optional mapping to
    # to keep them together. It does has a slight performance penalty so I will
    # eventually remove this
    mappings = {
        # old            :new
        "MD5": "md5",
        "SHA-1": "sha1",
        "Whirlpool": "whirlpool",
        "CRC-32": "crc32",
        "DropboxHash": "dropbox",
        "MailruHash": "mailru",
        "QuickXorHash": "quickxor",
    }

    hashes_all = [set() for _ in filelists]
    for filelist, hashes in zip(filelists, hashes_all):
        # Loop through each file in case some files are missing some hashes
        for file in filelist:
            hashes.update({mappings.get(h, h) for h in file.get("Hashes", {})})

    common = set().union(*hashes_all)
    priority = ["sha1", "md5", "crc32", "whirlpool", "dropbox", "mailru", "quickxor"]
    common = sorted(common, key=lambda h: priority.index(h) if h in priority else 999)

    try:
        common = common[0]
    except IndexError:
        raise ValueError("Could not find common hash")

    for filelist in filelists:
        for file in filelist:
            hashval = file.get("Hashes", {}).get(common, None)
            if hashval:
                file["common_hash"] = hashval
        filelist.add_fixed_attribute("common_hash")


def bytes2human(byte_count, base=1024, short=True):
    """
    Return a value,label tuple
    """
    if base not in (1024, 1000):
        raise ValueError("base must be 1000 or 1024")

    labels = ["kilo", "mega", "giga", "tera", "peta", "exa", "zetta", "yotta"]
    name = "bytes"
    if short:
        labels = [l[0] for l in labels]
        name = name[0]
    labels.insert(0, "")

    best = 0
    for ii in range(len(labels)):
        if (byte_count / (base**ii * 1.0)) < 1:
            break
        best = ii

    return byte_count / (base**best * 1.0), labels[best] + name


def file_summary(files):
    N = len(files)
    s = sum(f["Size"] for f in files if f)
    s = bytes2human(s)
    return f"{N:d} files, {s[0]:0.2f} {s[1]:s}"


def unix2iso(mtime):
    if not mtime:
        return "None"
    return datetime.datetime.fromtimestamp(float(mtime)).strftime("%Y-%m-%d %H:%M:%S")


def search_upwards(pwd):
    """
    Search upwards for `.syncrclone/config.py`
    """
    pwd = pwd = os.path.abspath(pwd)
    configpwd = os.path.join(pwd, ".syncrclone", "config.py")
    debug(f"Looking for config in '{pwd}'")
    if os.path.exists(configpwd):
        return configpwd

    newpwd = os.path.dirname(pwd)  # go upwards but if this doesn't change, then break
    if newpwd == pwd:
        return
    return search_upwards(newpwd)


def time_format(dt, upper=False):
    """Format time into days (D), hours (H), minutes (M), and seconds (S)"""
    labels = [  # Label, # of sec
        ("D", 60 * 60 * 24),
        ("H", 60 * 60),
        ("M", 60),
        ("S", 1),
    ]
    res = []
    for label, sec in labels:
        val, dt = divmod(dt, sec)
        if not val and not res and label != "S":  # Do not skip if already done
            continue
        if label == "S" and dt > 0:  # Need to handle leftover
            res.append(f"{val+dt:0.2f}")
        elif label in "HMS":  # these get zero padded
            res.append(f"{int(val):02d}")
        else:  # Do not zero pad dats
            res.append(f"{int(val):d}")
        res.append(label if upper else label.lower())
    return "".join(res)


def pathjoin(*args):
    """
    This is like os.path.join but does some rclone-specific things because there could be
    a ':' in the first part.

    The second argument could be '/file', or 'file' and the first could have a colon.
        pathjoin('a','b')   # a/b
        pathjoin('a:','b')  # a:b
        pathjoin('a:','/b') # a:/b
        pathjoin('a','/b')  # a/b  NOTE that this is different
    """
    if len(args) <= 1:
        return "".join(args)

    root, first, rest = args[0], args[1], args[2:]

    if root.endswith("/"):
        root = root[:-1]

    if root.endswith(":") or first.startswith("/"):
        path = root + first
    else:
        path = f"{root}/{first}"

    path = os.path.join(path, *rest)
    return path


class ReturnThread(Thread):
    """
    Like a regular thread except when you `join`, it returns the function
    result. And .start() will return itself to enable cleaner code.

        >>> mythread = ReturnThread(...).start() # instantiate and start

    Note that target is a required keyword argument.
    """

    def __init__(self, *, target, **kwargs):
        self.target = target
        super().__init__(target=self._target, **kwargs)
        self._res = None

    def start(self, *args, **kwargs):
        super().start(*args, **kwargs)
        return self

    def _target(self, *args, **kwargs):
        self._res = self.target(*args, **kwargs)

    def join(self, *args, **kwargs):
        super().join(*args, **kwargs)
        return self._res
