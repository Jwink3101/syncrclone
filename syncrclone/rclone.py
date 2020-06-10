"""
Most of the rclone interfacing
"""
import json
import os
import zlib
from collections import deque
import subprocess
import tempfile

from . import debug,log
from .cli import ConfigError
from .dicttable import DictTable
from . import utils


FILTER_FLAGS = {'--include', '--exclude', '--include-from', '--exclude-from', 
                '--filter', '--filter-from','--files-from'}

HEADER = b'zipjson\x00\x00' # Common header for file lists. If this changes, change docs

def mkdir(path,isdir=True):
    if not isdir:
        path = os.path.dirname(path)
    try:
        os.mkdir(path)
    except OSError:
        pass

class Rclone:
    def __init__(self,config):
        self.config = config
        self.add_args = [] # logging, etc
        self.tmpdir = tempfile.TemporaryDirectory().name
        
        try:
            os.makedirs(self.tmpdir)
        except OSError:
            pass
        
        self.validate()
        
        self.backup_path = {
            f'{AB}':os.path.join(getattr(config,f'remote{AB}'),
                                 '.syncrclone','backups',f'{AB}_{config.now}')
                            for AB in 'AB'}
        
        log('rclone version:')
        self.call(['--version'],stream=True)
        
    def validate(self):
        config = self.config
        attrs = ['rclone_flags','rclone_flagsA','rclone_flagsB']
        for attr in attrs:
            for v in getattr(config,attr):
                if v in FILTER_FLAGS:
                    raise ConfigError(f"'{attr}' cannot have '{v}' or any other filtering flags")
        
    def call(self,cmd,stream=False):
        """
        Call rclone. If streaming, will write stdout & stderr to
        log
        """
        cmd = [self.config.rclone_exe] + cmd
        debug('rclone:call',cmd)
        
        env = os.environ.copy()
        k0 = set(env)
        
        env.update(self.config.rclone_env)
        env['RCLONE_ASK_PASSWORD'] = 'false' # so that it never prompts
        
        debug_env = {k:v for k,v in env.items() if k not in k0}
        if 'RCLONE_CONFIG_PASS' in debug_env:
            debug_env['RCLONE_CONFIG_PASS'] = '**REDACTED**'
        
        debug(f'rclone: env {debug_env}')
        
        if stream:
            stdout = subprocess.PIPE
            stderr = subprocess.STDOUT
            bufsize = 1
        else:
            stdout = tempfile.NamedTemporaryFile(delete=False)
            stderr=subprocess.PIPE
            bufsize = -1
            
        proc = subprocess.Popen(cmd,
                                stdout=stdout,
                                stderr=stderr,
                                env=env,bufsize=bufsize)
        
        if stream:
            out = []
            with proc.stdout:
                for line in iter(proc.stdout.readline, b''):
                    line = line.decode().rstrip()
                    log('rclone:',line)
                    out.append(line)
            out = '\n'.join(out)
            err = ''
        
        proc.wait()
        
        if not stream:
            stdout.close()
            with open(stdout.name,'rt') as F:
                out = F.read()
            err = proc.stderr.read()
            if err:
                if isinstance(err,bytes):
                    err = err.decode()
                log(' rclone stderr:',err)
        
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode,cmd,output=out,stderr=err)
        return out
    
    def push_file_list(self,filelist,remote=None):        
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        dst = os.path.join(remote,'.syncrclone',f'{AB}-{self.config.name}_fl.zipjson')
        src = os.path.join(self.tmpdir,f'{AB}_curr')
        mkdir(src,isdir=False)
        
        filelist = list(filelist)
        with open(src,'wb') as file:
            file.write(HEADER + zlib.compress(json.dumps(filelist,ensure_ascii=False).encode('utf8')))
        
        cmd = config.rclone_flags \
            + self.add_args \
            + getattr(config,f'rclone_flags{AB}') \
            +  ['copyto',src,dst]
            
        self.call(cmd)

    def pull_prev_list(self,*,remote=None):
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        src = os.path.join(remote,'.syncrclone',f'{AB}-{self.config.name}_fl.zipjson')
        dst = os.path.join(self.tmpdir,f'{AB}_prev')
        mkdir(dst,isdir=False)
        
        cmd = config.rclone_flags \
            + self.add_args \
            + getattr(config,f'rclone_flags{AB}') \
            +  ['copyto',src,dst]
        self.call(cmd)
        
        with open(dst,'rb') as file:
            file.seek(len(HEADER)) # Skip
            return json.loads(zlib.decompress(file.read()))
        
    def file_list(self,*,prev_list=None,remote=None):
        """
        Get both current and previous file lists. If prev_list is
        set, then it is not pulled.
        
        Options:
        -------
        prev_list (list or DictTable)
            Previous file list. Specify if it is already known
        
        remote
            A or B
        
        
        It will decide if it needs hashes and whether to reuse them based
        on the config.
        """
        config = self.config
        
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        compute_hashes = 'hash' in [config.compare,getattr(config,f'renames{AB}')]
        reuse = compute_hashes and getattr(config,f'reuse_hashes{AB}')
        
        # build the command including initial filters *before* any filters set
        # by the user
        prev_list_name = os.path.join('.syncrclone',f'{AB}-{self.config.name}_fl.zipjson')
        cmd = ['lsjson',
               '--filter',f'+ /{prev_list_name}', # All of syncrclone's filters come first and include before exclude
               '--filter','+ /.syncrclone/LOCK/*',
               '--filter','- /.syncrclone/**']
        
        if compute_hashes and not reuse:
            cmd.append('--hash')
        
        # Now that my above filters, add user flags
        cmd += config.rclone_flags \
             + self.add_args \
             + getattr(config,f'rclone_flags{AB}') \
             + config.filter_flags

        cmd.extend([
            '-R',
            '--no-mimetype', # Not needed so will be faster
            '--files-only'])
        
        cmd.append(remote)
                
        files = json.loads(self.call(cmd))
        debug(f'{AB}: Read {len(files)}')
        
        for file in files:
            file.pop('IsDir',None)
            file.pop('Name',None)
            file['mtime'] = utils.RFC3339_to_unix(file.pop('ModTime'))
        
        files = DictTable(files,fixed_attributes=['Path','Size','mtime'])
        
        if not prev_list and {'Path':prev_list_name} in files:
            debug(f'Pulling prev list on {AB}')
            prev_list = self.pull_prev_list(remote=AB)
            files.remove({'Path':prev_list_name})
        elif not prev_list:
            debug(f'NEW prev list on {AB}')
            prev_list = []
            
        if not isinstance(prev_list,DictTable):
            prev_list = DictTable(prev_list,fixed_attributes=['Path','Size','mtime'])                
        
        # inodes if local
        if getattr(config,f'renames{AB}') == 'inode':
            debug('{AB}: Getting local inodes')
            if ':' in remote:
                raise ConfigError('Cannot get inodes for non-local or named remote')
            for file in files:
                localfile = os.path.join(remote,file['Path'])
                try:
                    stat = os.stat(localfile)
                except Exception as E:
                    ## TODO: Handle links
                    raise type(E)(f"Local file '{localfile}' not found. Check paths. May be a link")
                file['inode'] = stat.st_ino
            
            files.add_fixed_attribute('inode')
        
        if not compute_hashes or '--hash' in cmd:
            return files,prev_list
        
        # update with prev if possible and then get the rest
        not_hashed = []
        updated = 0
        for file in files: #size,mtime,filename
            prev = prev_list[{k:file[k] for k in ['Size','mtime','Path']}] # Will not find if no mtime not in remote
            if not prev or 'Hashes' not in prev:
                not_hashed.append(file['Path'])
                continue
            updated += 1
            file['Hashes'] = prev['Hashes']
        
        if len(not_hashed) == 0:
            debug(f'{AB}: Updated {updated}. No need to fetch more')
            return files,prev_list
        debug(f'{AB}: Updated {updated}. Fetching hashes for {len(not_hashed)}')
        
        tmpfile = self.tmpdir + f'/{AB}_update_hash'
        with open(tmpfile,'wt') as file:
            file.write('\n'.join(f for f in not_hashed))
        
        cmd = ['lsjson','--hash','--files-from',tmpfile]
        cmd += config.rclone_flags \
             + self.add_args \
             + getattr(config,f'rclone_flags{AB}')
             
        cmd.extend([
            '-R',
            '--no-mimetype', # Not needed so will be faster
            '--files-only'])
        
        cmd.append(remote)
    
        updated = json.loads(self.call(cmd))
        for file in updated:
            if 'Hashes' in file:
                files[{'Path':file['Path']}]['Hashes'] = file['Hashes']
                
        debug(f'{AB}: Updated hash on {len(updated)} files')
            
        return files,prev_list

    def delete_backup_move(self,remote,files,action):
        """
        Perform deletes, backups and moves. Same basic codes but with different
        reporting. If moves, files are (src,dest) tuples.
        """
        if not files:
            return
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        cmd =  [''] # Will get set later
        cmd += ['-v','--stats-one-line','--log-format','']
        cmd += config.rclone_flags + self.add_args + getattr(config,f'rclone_flags{AB}')
        
            
        if action == 'delete' and not config.backup: # This is the only one optimized
            # Can be done in one call.
            tmpfile = self.tmpdir + f'{AB}_del'
            with open(tmpfile,'wt') as file:
                file.write('\n'.join(files))
            cmd += ['--files-from',tmpfile,remote]
            cmd[0] = 'delete'
            self.call(cmd,stream=True)
        else:
            b = ' (w/ backup)' if action == 'delete' else ''
            # Moves have to iterated to not overlap. Also, do not need to list
            # the final dest so --no-traverse. Also add --no-check-dest since
            # no need to check the destination since we know it's (empty) state.
            # The docs suggest --retries 1 but we are *only* done a single file
            # at a time so we want it to retry on all files
            cmd += ['--no-traverse','--no-check-dest','--ignore-times']# + ['--retries','1']  
            for file in files:
                    if action in ['delete','backup']:
                        src = os.path.join(remote,file)
                        dest = os.path.join(self.backup_path[AB],file)
                        t = f"{action}{b} {AB}: '{file}'"
                    else:
                        src = os.path.join(remote,file[0])
                        dest = os.path.join(remote,file[1])
                        t = f"move {AB}: '{file[0]}' --> '{file[1]}'"
                    
                    if action in ['delete','move']:
                        cmd[0] = 'moveto' # non-backup deletes are in the original conditional
                    else:
                        cmd[0] = 'copyto' # Keep the original on delete
                    log(t)
                    self.call(cmd + [src,dest],stream=True)
                    
                    
        if action in ['delete','backup']:
            log(f"Backups for {AB} stored in '{self.backup_path[AB]}'")
    

    def transfer(self,mode,files):
        config = self.config
        if mode == 'A2B':
            src,dst = config.remoteA,config.remoteB
        elif mode == 'B2A':
            src,dst = config.remoteB,config.remoteA
        
        if not files:
            return
        
        cmd =  ['copy']
        cmd += ['-v','--stats-one-line','--log-format','']
        cmd += config.rclone_flags + self.add_args # + getattr(config,f'rclone_flags{AB}')
                                                   # ^^^ Doesn't get used here. 
                                                   # TODO: Consider using *both* as opposed to just one
                                                   # TODO: Make it more clear in the config
                                                   
        # Unlike move/delete/backup, the destination files may exist
        # so do *not* use --no-check-dest. May revisit this or make it an 
        # option. However, we want to transfer all files so --ignore-times and
        # and we know by construction that all of these files have changed so
        # include 
        #cmd += ['--no-check-dest']
        cmd += ['--ignore-times','--no-traverse']
        
        tmpfile = self.tmpdir + f'{mode}_transfer'
        with open(tmpfile,'wt') as file:
            file.write('\n'.join(files))
        cmd += ['--files-from',tmpfile]
        
        cmd += [src,dst]
        
        self.call(cmd,stream=True)
        
    def copylog(self,remote,src,dst):
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        dst = os.path.join(remote,dst)
        
        cmd = ['copyto']
        cmd += ['-v','--stats-one-line','--log-format','']
        cmd += config.rclone_flags + self.add_args + getattr(config,f'rclone_flags{AB}')
        
        cmd += ['--no-check-dest','--ignore-times','--no-traverse']

        self.call(cmd + [src,dst],stream=True)
    
    def lock(self,breaklock=False,remote='both'):
        """
        Sets or break the locks. Does *not* check for them first!
        """
        if remote == 'both':
            self.lock(breaklock=breaklock,remote='A')
            self.lock(breaklock=breaklock,remote='B')
            return
        elif remote not in 'AB':
            raise ValueError(f"Must specify remote as 'both', 'A', or 'B'. Specified {remote}")
        
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]

        cmd = [None]
        cmd += ['-v','--stats-one-line','--log-format','']
        cmd += config.rclone_flags + self.add_args + getattr(config,f'rclone_flags{AB}')
    
        cmd += ['--no-check-dest','--ignore-times','--no-traverse']

        if not breaklock:
            log(f'Setting lock on {AB}')
            cmd[0] = 'copyto'

            lockfile = os.path.join(self.tmpdir,f'LOCK_{config.name}')
            with open(lockfile,'wt') as F:
                F.write(config.now)
        
            dst = os.path.join(remote,f'.syncrclone/LOCK/LOCK_{config.name}')

            self.call(cmd + [lockfile,dst],stream=True)
        else:
            log(f'Breaking locks on {AB}. May return errors if {AB} is not locked')
            cmd[0] = 'delete'
            dst = os.path.join(remote,f'.syncrclone/LOCK/')
            try:
                self.call(cmd + ['--retries','1',dst],stream=True)
            except subprocess.CalledProcessError:
                log('No locks to break. Safely ignore rclone error')
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        



