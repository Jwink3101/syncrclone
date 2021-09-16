"""
Most of the rclone interfacing
"""
import json
import os
from collections import deque,defaultdict
import subprocess,shlex
import lzma
import tempfile
from concurrent.futures import ThreadPoolExecutor

from . import debug,log
from .cli import ConfigError
from .dicttable import DictTable
from . import utils

FILTER_FLAGS = {'--include', '--exclude', '--include-from', '--exclude-from', 
                '--filter', '--filter-from','--files-from'}


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
        
        self.backup_path0 = {
            f'{AB}':f'.syncrclone/backups/{config.now}_{self.config.name}_{AB}' 
                                                                 for AB in 'AB'}
        self.backup_path = {
            f'{AB}':pathjoin(getattr(config,f'remote{AB}'),self.backup_path0[AB])
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
        
    def call(self,cmd,stream=False,logstderr=True,display_error=True):
        """
        Call rclone. If streaming, will write stdout & stderr to
        log. If logstderr, will always send stderr to log (default)
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
            universal_newlines = True
        else: # Stream both stdout and stderr to files to prevent a deadlock
            stdout = tempfile.NamedTemporaryFile(delete=False)
            stderr = tempfile.NamedTemporaryFile(delete=False)
            bufsize = -1
            universal_newlines = False
            
        proc = subprocess.Popen(cmd,
                                stdout=stdout,
                                stderr=stderr,
                                universal_newlines=universal_newlines,
                                env=env,bufsize=bufsize)
        
        if stream:
            out = []
            with proc.stdout:
                for line in iter(proc.stdout.readline, ''):
                    line = line.rstrip()
                    log('rclone:',line)
                    out.append(line)
            out = '\n'.join(out)
            err = '' # Piped to stderr
        
        proc.wait()
        
        if not stream:
            stdout.close()
            stderr.close()
            with open(stdout.name,'rt') as F:
                out = F.read()
            with open(stderr.name,'rt') as F:
                err = F.read()
            if err and logstderr:
                log(' rclone stderr:',err)
        
        if proc.returncode:
            if display_error:
                log('RCLONE ERROR')
                log('CMD',cmd)
                if stream:
                    log('STDOUT and STDERR',out)
                else:
                    log('STDOUT',out.strip())
                    log('STDERR',err.strip())
            raise subprocess.CalledProcessError(proc.returncode,cmd,output=out,stderr=err)
        if not logstderr:
            out = out + '\n' + err
        return out
    
    def push_file_list(self,filelist,remote=None):        
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        dst = pathjoin(remote,'.syncrclone',f'{AB}-{self.config.name}_fl.json.xz')
        src = os.path.join(self.tmpdir,f'{AB}_curr')
        mkdir(src,isdir=False)
        
        filelist = list(filelist)
        with lzma.open(src,'wt') as file:
            json.dump(filelist,file,ensure_ascii=False)
        
        cmd = config.rclone_flags \
            + self.add_args \
            + getattr(config,f'rclone_flags{AB}') \
            +  ['copyto',src,dst]
            
        self.call(cmd)

    def pull_prev_list(self,*,remote=None):
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        src = pathjoin(remote,'.syncrclone',f'{AB}-{self.config.name}_fl.json.xz')
        dst = os.path.join(self.tmpdir,f'{AB}_prev')
        mkdir(dst,isdir=False)
        
        cmd = config.rclone_flags \
            + self.add_args \
            + getattr(config,f'rclone_flags{AB}') \
            +  ['copyto',src,dst]
        self.call(cmd)
        
        with lzma.open(dst) as file:
            return json.load(file)

    def pull_prev_listLEGACY(self,*,remote=None):
        import zlib
        HEADER = b'zipjson\x00\x00' 
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        src = pathjoin(remote,'.syncrclone',f'{AB}-{self.config.name}_fl.zipjson')
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
        prev_list_name = pathjoin('.syncrclone',f'{AB}-{self.config.name}_fl.json.xz')
        prev_list_nameLEGACY = pathjoin('.syncrclone',f'{AB}-{self.config.name}_fl.zipjson')
        cmd = ['lsjson',
               '--filter',f'+ /{prev_list_name}', # All of syncrclone's filters come first and include before exclude
               '--filter',f'+ /{prev_list_nameLEGACY}', 
               '--filter','+ /.syncrclone/LOCK/*',
               '--filter','- /.syncrclone/**']
        
        if compute_hashes and not reuse:
            cmd.append('--hash')

        if not config.always_get_mtime and \
           not (config.compare == 'mtime' or
                getattr(config,f'renames{AB}') == 'mtime' or
                config.conflict_mode in ('newer','older')):
            cmd.append('--no-modtime')
        
        # Now that my above filters, add user flags
        cmd += config.rclone_flags \
             + self.add_args \
             + getattr(config,f'rclone_flags{AB}') \
             + config.filter_flags

        cmd.extend([
            '-R',
            '--no-mimetype', # Not needed so will be faster
            ])
        
        cmd.append(remote)
                
        items = json.loads(self.call(cmd))
        
        folders = [] # Just the folder paths
        files = []
        for item in items:
            item.pop('Name',None)
            if item.pop('IsDir',False):
                item.pop('Size',None)
                item.pop('ModTime',None)
                folders.append(item)
                continue
            
            mtime = item.pop('ModTime')
            item['mtime'] = utils.RFC3339_to_unix(mtime) if mtime else None
            files.append(item)
            
        empties = get_empty_folders(folders,files)
        
        # Make them DictTables
        files = DictTable(files,fixed_attributes=['Path','Size','mtime'])
        debug(f'{AB}: Read {len(files)}')
        
        if not prev_list and {'Path':prev_list_name} in files:
            debug(f'Pulling prev list on {AB}')
            prev_list = self.pull_prev_list(remote=AB)
            files.remove({'Path':prev_list_name})
            if {'Path':prev_list_nameLEGACY} in files:
                log(f'NOTE: legacy previous list "{prev_list_nameLEGACY}" was found but NOT use on {AB}. You should remove it')
        elif not prev_list and {'Path':prev_list_nameLEGACY} in files:
            debug(f'Pulling prev list LEGACY on {AB}')
            prev_list = self.pull_prev_listLEGACY(remote=AB)
            files.remove({'Path':prev_list_nameLEGACY})
            log(f'NOTE: legacy previous list "{prev_list_nameLEGACY}" was used on {AB}. You can now remove it')
        elif not prev_list:
            debug(f'NEW prev list on {AB}')
            prev_list = []
            
        if not isinstance(prev_list,DictTable):
            prev_list = DictTable(prev_list,fixed_attributes=['Path','Size','mtime'])                
        
        # inodes if local
        if getattr(config,f'renames{AB}') == 'inode':
            debug(f'{AB}: Getting local inodes')
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
            return files,prev_list,empties
        
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
            return files,prev_list,empties
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
         

        return files,prev_list,empties

    def delete_backup_move(self,remote,dels,backups,moves):
        """
        Perform deletes, backups and moves. Same basic codes but with different
        reporting. If moves, files are (src,dest) tuples.
        """
        ## Optimization Notes
        # 
        # rclone is faster if you can do many actions at once. For example, to delete
        # files, it is faster to do `delete --files-from <list-of-files>`. However, for
        # moves, you cannot have overlapping remotes. We therefore have a few different
        # optimizations.
        #
        # NOTE: The order here is important!
        #   
        #     Delete w/ backup: Depends on the remote.
        #       If the remote supports moves:
        #           Optimize at the root subdir level so that we do not overlap with .syncrclone 
        #           but can otherwise use `move --files-from`
        #           
        #           The rootlevel ones will have to be a vanilla move. Add them.      
        #           See references below for why this can't just be one call.    
        #
        #       If the remote does not support moves: (i.e. it will internally 
        #       use copy+delete)
        #           Add the files to backup, run that first, and then delete w/o backup
        #
        #     Moves: No optimizations. One call for every file. :-( 
        #
        #     Backups:
        #       Use the `copy --files-from`
        #    
        #     Delete w/o backup
        #       Use `delete --files-from`
        #
        # References:
        #  
        # https://github.com/rclone/rclone/issues/1319
        #   Explains the issue with the quote:
        #
        #   > For a remote which doesn't it has to move each individual file which might 
        #   > fail and need a retry which is where the trouble starts...
        #
        # https://github.com/rclone/rclone/issues/1082
        #   Tracking issue. Also references https://forum.rclone.org/t/moving-the-contents-of-a-folder-to-the-root-directory/914/7
        #   
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        cmd0 =  [None] # Will get set later
        cmd0 += ['-v','--stats-one-line','--log-format','']
        # We know in all cases, the dest doesn't exists. For backups, it's totally new and
        # for moves, if it existed, it wouldn't show as a move. So never check dest, 
        # always transfer, and do not traverse
        cmd0 += ['--no-check-dest','--ignore-times','--no-traverse']
        cmd0 += config.rclone_flags + self.add_args + getattr(config,f'rclone_flags{AB}')
        
        backups = backups.copy() # Will be appended so make a new copy
        
        if config.backup:
            dels_back = dels
            dels_noback = []
        else:
            dels_back = []
            dels_noback = dels
        
        
        debug(AB,'dels_back',dels_back)
        debug(AB,'dels_noback',dels_noback)
        debug(AB,'moves',moves)
    
        ## Delete with backups
        def _move_del(root_files):
            root,files = root_files
            cmd = cmd0.copy()
            cmd[0] = 'move'
            
            tmpfile = self.tmpdir + f'/{AB}_movedel_{utils.random_str()}' 
            with open(tmpfile,'wt') as file:
                file.write('\n'.join(files))
            
            src = pathjoin(remote,root)
            dst = pathjoin(self.backup_path[AB],root)
            
            cmd += ['--files-from',tmpfile,src,dst]
            
            return '',self.call(cmd,stream=False,logstderr=False)
        
        if self.move_support(AB) and dels_back:
            rootdirs = defaultdict(list)
            for file in dels_back:
                dirpath,fname = os.path.split(file)
                dirsplit = dirpath.split('/')
                root = dirsplit[0]
                ff = os.path.join(*(list(dirsplit[1:]) + [fname]))
                rootdirs[root].append(ff)
            debug(f'rootdirs prior {AB}',dict(rootdirs))
            
            # Handle the root ones
            for file in rootdirs.pop('',[]):
                new = (file,os.path.join(self.backup_path0[AB],file))
                moves.append(new)
                debug('root-level backup as move',new)
            
            debug(f'rootdirs post {AB}',dict(rootdirs))
            
            with ThreadPoolExecutor(max_workers=int(config.action_threads)) as exe:
                for action,res in exe.map(_move_del,rootdirs.items()):
                    log(action)
                    for line in res.split('\n'):
                        line = line.strip()
                        if line: log('rclone:',line)
        elif dels_back: # Actually, could just use else here but I want to see in cov if its hit
            # Add to backup and delete without backup
            debug('Add to backup + delete',AB,dels_back)
            backups.extend(dels_back)
            dels_noback.extend(dels_back)
            
    
        ## Moves
        def _move(file):
            t = f'Move {shlex.quote(file[0])} --> {shlex.quote(file[1])}'
            src = pathjoin(remote,file[0])
            dst = pathjoin(remote,file[1])
        
            cmd = cmd0.copy()
            cmd[0] = 'moveto'
            cmd += [src,dst]
            return t,self.call(cmd,stream=False,logstderr=False)
        with ThreadPoolExecutor(max_workers=int(config.action_threads)) as exe:
            for action,res in exe.map(_move,moves):
                log(action)
                for line in res.split('\n'):
                    line = line.strip()
                    if line: log('rclone:',line) 
    
            
        ## Backups
        if backups:
            cmd = cmd0.copy()
            cmd[0] = 'copy'
            
            # we know the dest does not exists so speed it up
            cmd += ['--no-traverse','--no-check-dest','--ignore-times']
            cmd += ['--retries','4'] # Extra safe
            
            tmpfile = self.tmpdir + f'/{AB}_movedel_{utils.random_str()}' 
            with open(tmpfile,'wt') as file:
                file.write('\n'.join(backups))
            
            src = remote
            dst = self.backup_path[AB]
            
            cmd += ['--files-from',tmpfile,src,dst]
            debug('backing up',backups)
            for line in self.call(cmd,stream=False,logstderr=False).split('\n'):
                line = line.strip()
                if line: log('rclone:',line)
            
        ## Deletes w/o backup
        if dels_noback:
            tmpfile = self.tmpdir + f'/{AB}_del'
            with open(tmpfile,'wt') as file:
                file.write('\n'.join(dels))
            cmd = cmd0.copy()
            cmd += ['--files-from',tmpfile,remote]
            cmd[0] = 'delete'
            log('deleting')
            for line in self.call(cmd,stream=False,logstderr=False).split('\n'):
                line = line.strip()
                if line: log('rclone:',line)
    
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
        
        dst = pathjoin(remote,dst)
        
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

        log('')
        if not breaklock:
            log(f'Setting lock on {AB}')
            cmd[0] = 'copyto'

            lockfile = pathjoin(self.tmpdir,f'LOCK_{config.name}')
            with open(lockfile,'wt') as F:
                F.write(config.now)
        
            dst = pathjoin(remote,f'.syncrclone/LOCK/LOCK_{config.name}')

            self.call(cmd + [lockfile,dst],stream=True)
        else:
            log(f'Breaking locks on {AB}. May return errors if {AB} is not locked')
            cmd[0] = 'delete'
            dst = pathjoin(remote,f'.syncrclone/LOCK/')
            try:
                self.call(cmd + ['--retries','1',dst],stream=True,display_error=False)
            except subprocess.CalledProcessError:
                log('No locks to break. Safely ignore rclone error')

    def rmdirs(self,remote,dirlist):
        """
        Remove the directories in dirlist. dirlist is sorted so the deepest
        go first and then they are removed. Note that this is done this way
        since rclone will not delete if *anything* exists there; even files 
        we've ignored.
        """
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        # Originally, I sorted by length to get the deepest first but I can
        # actually get the root of them so that I can call rmdirs (with the `s`)
        # and let that go deep
        
        rmdirs = []
        for diritem in sorted(dirlist):
            # See if it's parent is already there. This can 100% be improved
            # since the list is sorted. See https://stackoverflow.com/q/7380629/3633154
            # for example. But it's not worth it here
            if any(diritem.startswith(f'{rmdir}/') for rmdir in rmdirs):
                continue # ^^^ Add the / so it gets child dirs only
            rmdirs.append(diritem)
        
        cmd = ['rmdirs','-v','--stats-one-line','--log-format','','--retries','1'] 
        
        def _rmdir(rmdir):
            _cmd = cmd + [pathjoin(remote,rmdir)]
            try:
                return rmdir,self.call(_cmd,stream=False,logstderr=False)
            except subprocess.CalledProcessError:
                # This is likely due to the file not existing. It is acceptable
                # for this error since even if it was something else, not 
                # properly removing empty dirs is acceptable
                return rmdir,'<< could not delete >>'
            
        with ThreadPoolExecutor(max_workers=int(config.action_threads)) as exe:
            for rmdir,res in exe.map(_rmdir,rmdirs):
                log(f'rmdirs (if possible) on {AB}: {rmdir}')
                for line in res.split('\n'):
                    line = line.strip()
                    if line: log('rclone:',line) 
    
    def move_support(self,remote):
        """
        Return whether or not the remote supports 
        
        Defaults to True since if it doesn't support them, calling rmdirs
        will just do nothing
        """
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        features = json.loads(self.call(['backend','features',remote] \
                                        + config.rclone_flags \
                                        + getattr(config,f'rclone_flags{AB}'),stream=False))
        return features.get('Features',{}).get('Move',True)
        
    
    def empty_dir_support(self,remote):
        """
        Return whether or not the remote supports 
        
        Defaults to True since if it doesn't support them, calling rmdirs
        will just do nothing
        """
        config = self.config
        AB = remote
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        features = json.loads(self.call(['backend','features',remote] \
                                        + config.rclone_flags \
                                        + getattr(config,f'rclone_flags{AB}'),stream=False))
        return features.get('Features',{}).get('CanHaveEmptyDirectories',True)
    
    def run_shell(self,pre=None):
        """Run the shell commands"""
        cmds = self.config.pre_sync_shell if pre else self.config.post_sync_shell
        if not cmds.strip():
            return
        log('')
        log('Running shell commands')
        prefix = f'{"DRY RUN " if self.config.dry_run else ""}$'
        for line in cmds.split('\n'):
            log(f'{prefix} {line}')
        
        if self.config.dry_run:
            return log('NOT RUNNING')
        proc = subprocess.Popen(cmds,
                                shell=True,
                                stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE)
        out,err = proc.communicate()
        for line in out.decode().split('\n'):
            log(f'STDOUT: {line}')
        for line in err.decode().split('\n'):
            log(f'STDERR: {line}')
        
            
    
def get_empty_folders(folders,files):
    """
    Returns the empty directories as a subset of folders
    """
    # Make a set of all parents
    parents = set()
    for file in files:
        parents.update(all_parents(os.path.dirname(file['Path'])))
    
    folders = set(folder['Path'] for folder in folders)
    return folders - parents
        
def all_parents(dirpath):
    """Yield dirpath and all parents of dirpath"""
    split = dirpath.rsplit(sep='/',maxsplit=1)
    yield dirpath
    if len(split) == 2: # Not done
        yield from all_parents(split[0])
        
        

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
        return ''.join(args)
    
    root,first,rest = args[0],args[1],args[2:]
    
    if root.endswith(':') or first.startswith('/'):
        path = root + first
    else:
        path = f'{root}/{first}' 
    
    return os.path.join(path,*rest)
     
        
        
        
        
        
        
        
        
        
        
        
        
        



