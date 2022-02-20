"""
Most of the rclone interfacing
"""
import json
import os
from collections import deque,defaultdict
import subprocess,shlex
import lzma
import time
from concurrent.futures import ThreadPoolExecutor

from . import debug,log
from .cli import ConfigError
from .dicttable import DictTable
from . import utils
from . import tempfile

FILTER_FLAGS = {'--include', '--exclude', '--include-from', '--exclude-from', 
                '--filter', '--filter-from','--files-from'}
                
def mkdir(path,isdir=True):
    if not isdir:
        path = os.path.dirname(path)
    try:
        os.mkdir(path)
    except OSError:
        pass
        
class LockedRemoteError(ValueError):
    pass
    
class Rclone:
    def __init__(self,config):
        self.config = config
        self.add_args = [] # logging, etc
        self.tmpdir = tempfile.TemporaryDirectory().name
        
        self.rclonetime = 0.0
        
        try:
            os.makedirs(self.tmpdir)
        except OSError:
            pass
        
        self.validate()
        
        self.backup_path,self.backup_path0 = {},{}
        for AB in 'AB':
            self.backup_path0[AB] = f'backups/{config.now}_{self.config.name}_{AB}' # really only used for top level non-workdir backups with delete       
            self.backup_path[AB] = utils.pathjoin(getattr(config,f'workdir{AB}'),self.backup_path0[AB])
        
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
        cmd = shlex.split(self.config.rclone_exe) + cmd
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
        else: # Stream both stdout and stderr to files to prevent a deadlock
            stdout = tempfile.NamedTemporaryFile(delete=False)
            stderr = tempfile.NamedTemporaryFile(delete=False)

        
        t0 = time.time()
        proc = subprocess.Popen(cmd,
                                stdout=stdout,
                                stderr=stderr,
                                env=env)
        
        if stream:
            out = []
            with proc.stdout:
                for line in iter(proc.stdout.readline, b''):
                    line = line.decode(errors="backslashreplace") # Allow for bad decoding. See https://github.com/Jwink3101/syncrclone/issues/16
                    line = line.rstrip()
                    log('rclone:',line)
                    out.append(line)
            out = '\n'.join(out)
            err = '' # Piped to stderr
        
        proc.wait()
        self.rclonetime += time.time() - t0
        
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
        remote = getattr(config,f'remote{AB}')
        workdir = getattr(config,f'workdir{AB}')

        dst = utils.pathjoin(workdir,f'{AB}-{self.config.name}_fl.json.xz')
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
        remote = getattr(config,f'remote{AB}')
        workdir = getattr(config,f'workdir{AB}')
        src = utils.pathjoin(workdir,f'{AB}-{self.config.name}_fl.json.xz')
        dst = os.path.join(self.tmpdir,f'{AB}_prev')
        mkdir(dst,isdir=False)
        
        cmd = config.rclone_flags \
            + self.add_args \
            + getattr(config,f'rclone_flags{AB}') \
            +  ['--retries','1','copyto',src,dst]
        try:
            self.call(cmd,display_error=False,logstderr=False)
        except subprocess.CalledProcessError as err:
            # Codes (https://rclone.org/docs/#exit-code) 3,4 are expected if there is no list
            if err.returncode in {3,4}:
                log(f'No previous list on {AB}. Reset state')
                return [] 
        
        with lzma.open(dst) as file:
            return json.load(file)

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
        remote = getattr(config,f'remote{AB}')
        
        compute_hashes = 'hash' in [config.compare,getattr(config,f'renames{AB}')]
        reuse = compute_hashes and getattr(config,f'reuse_hashes{AB}')
        
        # build the command including initial filters *before* any filters set
        # by the user
        cmd = ['lsjson',
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
            '--files-only',
            ])
        
        cmd.append(remote)
        files = json.loads(self.call(cmd))
        debug(f'{AB}: Read {len(files)}')
        for file in files:
            for key in ['IsDir','Name','ID','Tier']: # Things we do not need. There may be others but it doesn't hurt
                file.pop(key,None)
            mtime = file.pop('ModTime',None)
            file['mtime'] = utils.RFC3339_to_unix(mtime) if mtime else None
        
        # Make them DictTables
        files = DictTable(files,fixed_attributes=['Path','Size','mtime'])
        debug(f'{AB}: Read {len(files)}')
        
        if config.reset_state:
            debug(f'Reset state on {AB}')
            prev_list = []
        else:
            prev_list = self.pull_prev_list(remote=AB)

        if not isinstance(prev_list,DictTable):
            prev_list = DictTable(prev_list,fixed_attributes=['Path','Size','mtime'])                
        
        if not compute_hashes or '--hash' in cmd:
            return files,prev_list
        
        # update with prev if possible and then get the rest
        not_hashed = []
        updated = 0
        for file in files: #size,mtime,filename
            prev = prev_list[{k:file[k] for k in ['Size','mtime','Path']}] # Will not find if no mtime not in remote
            if not prev or 'Hashes' not in prev or not prev.get('mtime',None): # or '_copied' in prev: # Do not reuse a copied hash in case of incompatability
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
        #     Delete w/ backup: Depends on the remote and the workdir settings
        #     (a) If a workdir is specified, *just* use `move --files-from`
        #
        #     (b) If the remote supports moves:
        #         Optimize at the root subdir level so that we do not overlap with .syncrclone 
        #         but can otherwise use `move --files-from`
        #           
        #         The rootlevel ones will have to be a vanilla move. Add them.      
        #         See references below for why this can't just be one call.    
        #
        #     (c) If the remote does not support moves: (i.e. it will internally 
        #         use copy+delete)
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
        remote = getattr(config,f'remote{AB}')
        
        
        
        cmd0 =  [None] # Will get set later
        cmd0 += ['-v','--stats-one-line','--log-format','']
        # We know in all cases, the dest doesn't exists. For backups, it's totally new and
        # for moves, if it existed, it wouldn't show as a move. So never check dest, 
        # always transfer, and do not traverse
        cmd0 += ['--no-check-dest','--ignore-times','--no-traverse']
        cmd0 += config.rclone_flags + self.add_args + getattr(config,f'rclone_flags{AB}')
        
        dels = dels.copy()
        moves = moves.copy()
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
            
            src = utils.pathjoin(remote,root)
            dst = utils.pathjoin(self.backup_path[AB],root)
            
            cmd += ['--files-from',tmpfile,src,dst]
            
            return '',self.call(cmd,stream=False,logstderr=False)
        
        if getattr(config,f'workdir0{AB}'): # Specified workdir. Not .syncrlcone
            cmd = cmd0.copy() # This is copied directly from below with minor changes. Probably could clean it up and use the same code path
            cmd[0] = 'move'
            
            # we know the dest does not exists so speed it up
            cmd += ['--no-traverse','--no-check-dest','--ignore-times']
            cmd += ['--retries','4'] # Extra safe
            
            tmpfile = self.tmpdir + f'/{AB}_movedel_{utils.random_str()}' 
            with open(tmpfile,'wt') as file:
                file.write('\n'.join(dels_back))
            
            src = remote
            dst = self.backup_path[AB]
            
            cmd += ['--files-from',tmpfile,src,dst]
            debug('Delete w/ backup',dels_back)
            for line in self.call(cmd,stream=False,logstderr=False).split('\n'):
                line = line.strip()
                if line: log('rclone:',line)
            
        elif self.move_support(AB) and dels_back:
            rootdirs = defaultdict(list)
            for file in dels_back:
                dirpath,fname = os.path.split(file)
                dirsplit = dirpath.split('/')
                root = dirsplit[0] 
                ff = os.path.join(*(list(dirsplit[1:]) + [fname]))
                rootdirs[root].append(ff)
            debug(f'rootdirs prior {AB}',dict(rootdirs))
            
            # Handle the root ones as vanilla moves
            for file in rootdirs.pop('',[]):
                new = (file,os.path.join('.syncrclone',self.backup_path0[AB],file))
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
            src = utils.pathjoin(remote,file[0])
            dst = utils.pathjoin(remote,file[1])
        
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
        # option. 
        #cmd.append('--no-check-dest')
        
        # We used to also use --ignore-times to *always* transfer but this can cause retries to
        # of EVERYTHING when only some things fail. The files includes should always be modified by
        # design so this is harmless
        # cmd.append('--ignore-times')
        
        # This flags is not *really* needed but based on the docs (https://rclone.org/docs/#no-traverse),
        # it is likely the case that only a few files will be transfers. This number is a WAG. May change 
        # the future
        if len(files) <= 100:
            cmd.append('--no-traverse')
        
        tmpfile = self.tmpdir + f'{mode}_transfer'
        with open(tmpfile,'wt') as file:
            file.write('\n'.join(files))
        cmd += ['--files-from',tmpfile]
        
        cmd += [src,dst]
        
        self.call(cmd,stream=True)
        
    def copylog(self,remote,srcfile,logname):
        config = self.config
        AB = remote
        
        dst = utils.pathjoin(getattr(config,f'workdir{AB}'),'logs',logname)
        
        cmd = ['copyto']
        cmd += ['-v','--stats-one-line','--log-format','']
        cmd += config.rclone_flags + self.add_args + getattr(config,f'rclone_flags{AB}')
        
        cmd += ['--no-check-dest','--ignore-times','--no-traverse']
        self.call(cmd + [srcfile,dst],stream=True)
    
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
        remote = getattr(config,f'remote{AB}')
        workdir = getattr(config,f'workdir{AB}')

        cmd = [None]
        cmd += ['-v','--stats-one-line','--log-format','']
        cmd += config.rclone_flags + self.add_args + getattr(config,f'rclone_flags{AB}')
    
        cmd += ['--ignore-times','--no-traverse']
        
        lockdest = utils.pathjoin(workdir,f'LOCK/LOCK_{config.name}')

        log('')
        if not breaklock:
            log(f'Setting lock on {AB}')
            cmd[0] = 'copyto'

            lockfile = utils.pathjoin(self.tmpdir,f'LOCK_{config.name}')
            with open(lockfile,'wt') as F:
                F.write(config.now)
            self.call(cmd + [lockfile,lockdest],stream=True)
        else:
            log(f'Breaking locks on {AB}. May return errors if {AB} is not locked')
            cmd[0] = 'delete'
            try:
                self.call(cmd + ['--retries','1',lockdest],stream=True,display_error=False)
            except subprocess.CalledProcessError:
                log('No locks to break. Safely ignore rclone error')
    
    def check_lock(self,remote='both'):
        if remote == 'both':
            self.check_lock('A')
            self.check_lock('B')
            return

        config = self.config
        AB = remote
        workdir = getattr(config,f'workdir{AB}')
        lockdest = utils.pathjoin(workdir,f'LOCK/LOCK_{config.name}')
        
        cmd = config.rclone_flags \
            + self.add_args \
            + getattr(config,f'rclone_flags{AB}') \
            +  ['--retries','1','lsf',lockdest]
        
        try:
            self.call(cmd,display_error=False,logstderr=False)
        except subprocess.CalledProcessError as err:
            # Codes (https://rclone.org/docs/#exit-code) 3,4 are expected if there is no file
            if err.returncode in {3,4}:
                return True
            else:
                raise
        
        raise LockedRemoteError(f'Locked on {AB}, {lockdest}')
    
            
    def rmdirs(self,remote,dirlist):
        """
        Remove the directories in dirlist. dirlist is sorted so the deepest
        go first and then they are removed. Note that this is done this way
        since rclone will not delete if *anything* exists there; even files 
        we've ignored.
        """
        config = self.config
        AB = remote
        remote = getattr(config,f'remote{AB}')
        
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
        
        cmd = config.rclone_flags + self.add_args + getattr(config,f'rclone_flags{AB}')
        cmd += ['rmdirs','-v','--stats-one-line','--log-format','','--retries','1'] 
        
        def _rmdir(rmdir):
            _cmd = cmd + [utils.pathjoin(remote,rmdir)]
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
        remote = getattr(config,f'remote{AB}')
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
        remote = getattr(config,f'remote{AB}')
        features = json.loads(self.call(['backend','features',remote] \
                                        + config.rclone_flags \
                                        + getattr(config,f'rclone_flags{AB}'),stream=False))
        return features.get('Features',{}).get('CanHaveEmptyDirectories',True)
    


     
        
        
        
        
        
        
        
        
        
        
        
        
        



