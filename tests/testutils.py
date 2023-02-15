"""
Utilities for testing
"""
import random
import os, sys
import shutil
import subprocess
import io
import re
import builtins
import glob
import zlib
from pathlib import Path

PWD0 = os.path.abspath(os.path.dirname(__file__))
os.chdir(PWD0)

p = os.path.abspath("../")
if p not in sys.path:
    sys.path.insert(0, p)

# Make sure the testdirs are ignored by backup tools
testdir = Path(__file__).parent / "testdirs"
testdir.mkdir(exist_ok=True, parents=True)
(testdir / ".ignore").touch()


def call(cmd, env=None):
    if env is None:
        env = {}
    _env = os.environ.copy()
    _env.update(env)
    print("CALLING", cmd)
    subprocess.call(cmd, env=_env)


import syncrclone
import syncrclone.cli


class Tester:
    def __init__(self, name, remoteA, remoteB, seed=1):
        os.chdir(PWD0)
        syncrclone.log.clear()
        self.synclogs = []

        self.remoteA = remoteA
        self.remoteB = remoteB

        self.name = name
        self.pwd = os.path.abspath(f"testdirs/{name}")
        try:
            shutil.rmtree(self.pwd)
        except OSError:
            pass
        os.makedirs(self.pwd + "/A")

        # Will also append additional rclone???
        shutil.copy2("rclone.cfg", self.pwd + "/rclone.cfg")

        os.chdir(self.pwd)

        syncrclone.cli.cli(["--new", "config.py"])
        with open("config.py", "at") as f:
            f.write(f"\nremoteA='{remoteA}'\nremoteB='{remoteB}'")

        self.config = syncrclone.cli.Config("config.py")
        self.config.parse()
        self.config.rclone_env["RCLONE_CONFIG"] = "rclone.cfg"

        self.sftp = SFTP(os.path.join(self.pwd, "sftp"))
        if remoteA.startswith("mysftp:") or remoteB.startswith("mysftp:"):
            self.sftp.start()

        self.webdav = WEBDAV(os.path.join(self.pwd, "webdav"))
        if remoteA.startswith("mywebdav:") or remoteB.startswith("mywebdav:"):
            self.webdav.start()

    def write_config(self):
        self.config.local_log_dest = "logs/"
        with open(self.config._configpath, "wt") as file:
            for key, var in self.config._config.items():
                if key.startswith("_"):
                    continue

                file.write(f"{key} = {repr(var)}\n")
        # Use this opportunity to reset workdirs
        self.wdA = "wdA" if self.config.workdirA else "A/.syncrclone"
        self.wdB = "wdB" if self.config.workdirB else "B/.syncrclone"

    def setup(self, **kwargs):
        """Sync A --> B then A --> remoteA and B --> remoteB"""
        exe = self.config.rclone_exe
        call([exe, "sync", "A/", "B/"], env=self.config.rclone_env)  # No special flags

        if self.remoteA != "A":
            call(
                [exe, "purge"]
                + self.config.rclone_flags
                + self.config.rclone_flagsA
                + [self.remoteA],
                env=self.config.rclone_env,
            )
        if self.remoteB != "B":
            call(
                [exe, "purge"]
                + self.config.rclone_flags
                + self.config.rclone_flagsB
                + [self.remoteB],
                env=self.config.rclone_env,
            )
        if self.config.workdirA:
            call(
                [exe, "purge"]
                + self.config.rclone_flags
                + self.config.rclone_flagsA
                + [self.config.workdirA],
                env=self.config.rclone_env,
            )
        if self.config.workdirB:
            call(
                [exe, "purge"]
                + self.config.rclone_flags
                + self.config.rclone_flagsB
                + [self.config.workdirB],
                env=self.config.rclone_env,
            )

        return self.sync(**kwargs)

    def sync(self, flags=None, configpath="config.py"):
        exe = self.config.rclone_exe

        # Local to remote (push)
        if self.remoteA != "A":
            call(
                [exe, "sync"]
                + self.config.rclone_flags
                + self.config.rclone_flagsA
                + ["A/", self.remoteA],
                env=self.config.rclone_env,
            )
        if self.remoteB != "B":
            call(
                [exe, "sync"]
                + self.config.rclone_flags
                + self.config.rclone_flagsB
                + ["B/", self.remoteB],
                env=self.config.rclone_env,
            )

        # Sync
        if flags is None:
            flags = []
        syncobj = syncrclone.cli.cli(list(flags) + [configpath])

        with open("logs/" + sorted(os.listdir("logs"))[-1]) as file:
            self.synclogs.append(file.readlines())

        # remote to local (pull)

        if self.remoteA != "A":
            call(
                [exe, "sync"]
                + self.config.rclone_flags
                + self.config.rclone_flagsA
                + [self.remoteA, "A/"],
                env=self.config.rclone_env,
            )
        if self.remoteB != "B":
            call(
                [exe, "sync"]
                + self.config.rclone_flags
                + self.config.rclone_flagsB
                + [self.remoteB, "B/"],
                env=self.config.rclone_env,
            )

        if self.config.workdirA:
            call(
                [exe, "sync"]
                + self.config.rclone_flags
                + self.config.rclone_flagsA
                + [self.config.workdirA, self.wdA],
                env=self.config.rclone_env,
            )
        if self.config.workdirB:
            call(
                [exe, "sync"]
                + self.config.rclone_flags
                + self.config.rclone_flagsB
                + [self.config.workdirB, self.wdB],
                env=self.config.rclone_env,
            )

        os.chdir(self.pwd)
        return syncobj

    def write(self, path, content, mode="wt", dt=0):
        try:
            os.makedirs(os.path.dirname(path))
        except:
            pass

        with open(path, mode) as file:
            file.write(content)

        if dt:
            change_time(path, dt)

    def write_pre(self, path, content, mode="wt", dt=None):
        """Write items randomly in the past"""
        dt = dt if not None else -5 * (1 + random.random())
        if path.startswith("B"):
            raise ValueError("No pre on B")
        self.write(path, content, mode=mode, dt=dt)

    def write_post(self, path, content, mode="wt", add_dt=0):
        """
        Write items randomly in the future. Can add even more if forcing
        newer
        """
        dt = 5 * (1 + random.random()) + add_dt
        self.write(path, content, mode=mode, dt=dt)

    def read(self, path):
        with open(path, "rt") as file:
            return file.read()

    def globread(self, globpath):
        paths = glob.glob(globpath)
        if len(paths) == 0:
            raise OSError("No files matched the glob pattern")
        if len(paths) > 1:
            raise OSError(f"Too many files matched the pattern: {paths}")

        return self.read(paths[0])

    def move(self, src, dst):
        try:
            os.makedirs(os.path.dirname(dst))
        except OSError:
            pass

        shutil.move(src, dst)

    def compare_tree(self, A="A", B="B"):
        """All file systems are identical"""
        result = set()

        filesA = set(os.path.relpath(f, A) for f in tree(A))
        filesB = set(os.path.relpath(f, B) for f in tree(B))

        filesAB = filesA.union(filesB)
        for fileAB in sorted(list(filesAB)):
            fileA = os.path.join(A, fileAB)
            fileB = os.path.join(B, fileAB)
            try:
                fileAtxt = open(fileA).read()
            except IOError:
                result.add(("missing_inA", fileAB))
                continue

            try:
                fileBtxt = open(fileB).read()
            except IOError:
                result.add(("missing_inB", fileAB))
                continue

            if not fileAtxt == fileBtxt:
                result.add(("disagree", fileAB))

        return result

    def done(self):
        os.chdir(PWD0)
        self.sftp.stop()
        self.webdav.stop()


class SFTP:
    def __init__(self, path):
        self.pwd = path
        self.running = False

    def start(self):
        cmd = [
            "rclone",
            "serve",
            "sftp",
            self.pwd,
            "--no-auth",
            "--addr",
            "localhost:20222",
        ]
        print(f"SFTP: {cmd = }")
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.running = True
        print("START SFTP")

    def stop(self):
        if not self.running:
            return
        import signal

        self.proc.send_signal(signal.SIGKILL)
        print("END SFTP")


class WEBDAV:
    def __init__(self, path):
        self.pwd = path
        self.running = False

    def start(self):
        cmd = ["rclone", "serve", "webdav", self.pwd, "--addr", "localhost:20223"]
        print(f"WEBDAV: {cmd = }")
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.running = True
        print("START WEBDAV")

    def stop(self):
        if not self.running:
            return
        import signal

        self.proc.send_signal(signal.SIGKILL)
        print("END WEBDAV")


def adler32(filepath, blocksize=2**20):
    """
    Return the ader32 of a file as an 8-byte hex number

    `blocksize` adjusts how much of the file is read into memory at a time.
    This is useful for large files.
        2**20 = 1024 * 1024 = 1 mb
        2**12 = 4 * 1024    = 4 kb
    """
    csum = 1
    with open(filepath, "rb") as afile:
        buf = afile.read(blocksize)
        while len(buf) > 0:
            csum = zlib.adler32(buf, csum)
            buf = afile.read(blocksize)
    # From the documentation:
    #  > Changed in version 3.0: Always returns an unsigned value.
    #  > To generate the same numeric value across all Python versions and
    #  > platforms, use crc32(data) & 0xffffffff.
    csum = csum & 0xFFFFFFFF
    return ("0" * 8 + hex(csum)[2:])[-8:]  # Preceding 0s


def change_time(path, time_adj):
    """Change the time on a file path"""
    stat = os.stat(path)
    os.utime(path, (stat.st_atime + time_adj, stat.st_mtime + time_adj))


def tree(path):
    files = []
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        for d in [".syncrclone", ".git"]:
            try:
                dirnames.remove(d)
            except ValueError:
                pass

        exc = {".DS_Store"}
        files.extend(
            os.path.join(dirpath, filename)
            for filename in filenames
            if filename not in exc
        )

    return files
