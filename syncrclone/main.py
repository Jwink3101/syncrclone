import copy
import time
import sys,os,shutil
import warnings
import tempfile

from . import debug,log
from . import utils
from .rclone import Rclone

class LockedRemoteError(ValueError):
    pass

class SyncRClone:
    def __init__(self,config,break_lock=None):
        """
        Main sync object. If break_lock is not None, will *just* break the
        locks
        """
        self.now = time.strftime("%Y-%m-%dT%H%M%S", time.localtime())
        self.now_compact = self.now.replace('-','')
        
        self.config = config
        self.config.now = self.now # Set it there to be used elsewhere
        self.rclone = Rclone(self.config)

        if break_lock:
            if self.config.dry_run:
                log('DRY RUN lock break')
                return
            self.rclone.lock(breaklock=True,remote=break_lock)
            return

        # Get file lists
        log(f"Refreshing file list on A '{config.remoteA}'")
        self.currA,self.prevA = self.rclone.file_list(remote='A')
        log(utils.file_summary(self.currA))
        
        log(f"Refreshing file list on B '{config.remoteB}'")
        self.currB,self.prevB = self.rclone.file_list(remote='B')
        log(utils.file_summary(self.currB))

        self.check_lock()
        if self.config.set_lock and not config.dry_run: # no lock for dry-run since we won't change anything
            self.rclone.lock()
        
        # Store the original "curr" list as the prev list for speeding
        # up the hashes. Also used to tag checking.
        # This makes a copy but keeps the items
        self.currA0 = self.currA.copy()
        self.currB0 = self.currB.copy()
        
        self.remove_common_files()
        self.process_non_common() # builds new,del,tag,backup,trans,move lists
        
        self.echo_queues('Initial')
        
        # Track moves from new and del lists. Adds to moves list()
        self.track_moves('A')
        self.track_moves('B') 
        
        self.echo_queues('After tracking moves')
    
        # Apply moves and transfers from the new and tag lists.
        # After this, we only care about del, backup, and move lists
        self.process_new_tags('A') 
        self.process_new_tags('B')
        
        self.echo_queues('After processing new and tags')
        
        if config.dry_run:
            self.dry_run()
            self.dump_logs()
            return
        
        # Perform deletes, backups, and moves
        self.rclone.delete_backup_move('A',self.delA,'delete')
        if config.backup: self.rclone.delete_backup_move('A',self.backupA,'backup')
        self.rclone.delete_backup_move('A',self.movesA,'move')
        
        self.rclone.delete_backup_move('B',self.delB,'delete')
        if config.backup: self.rclone.delete_backup_move('B',self.backupB,'backup')
        self.rclone.delete_backup_move('B',self.movesB,'move')
        
        # Perform final transfers
        sumA = utils.file_summary([self.currA.query_one(Path=f) for f in self.transA2B])
        log(f'A >>> B {sumA}')
        self.rclone.transfer('A2B',self.transA2B)
        
        sumB = utils.file_summary([self.currB.query_one(Path=f) for f in self.transB2A])
        log(f'B >>> A {sumB}')
        self.rclone.transfer('B2A',self.transB2A)

        # Update lists if needed
        if self.delA or self.backupA or self.movesA or self.transB2A:
            log('Refreshing file list on A')
            new_listA,_ = self.rclone.file_list(remote='A',prev_list=self.currA0)
            log(utils.file_summary(new_listA))
            self.rclone.push_file_list(new_listA,remote='A')
        else:
            log('No need to refresh file list on A. Updating current state')
            # We still push this in case new things were hashed
            self.rclone.push_file_list(self.currA0,remote='A')
        
        if self.delB or self.backupB or self.movesB or self.transA2B:
            log('Refreshing file list on B')
            new_listB,_ = self.rclone.file_list(remote='B',prev_list=self.currB0)
            log(utils.file_summary(new_listB))
            self.rclone.push_file_list(new_listB,remote='B')
        else:
            log('No need to refresh file list on B. Updating current state')
            # We still push this in case new things were hashed
            self.rclone.push_file_list(self.currB0,remote='B')
        
        if self.config.set_lock: # There shouldn't be a lock since we didn't set it so save the rclone call
            self.rclone.lock(breaklock=True)
            
        self.dump_logs()
    
    def dump_logs(self):
        if not self.config.local_log_dest and not self.config.log_dest:
            log('Logs are not being saved')
            return
        
        logname = f"{self.config.name}_{self.now}.log"
        
        # log these before dumping
        if self.config.local_log_dest:
            log(f"Logs will be saved locally to '{os.path.join(self.config.local_log_dest,logname)}'")
        if self.config.log_dest:
            log(f"Logs will be saved on remotes to '{os.path.join(self.config.log_dest,logname)}'")
        
        tfile =  os.path.join(self.rclone.tmpdir,'log')
        log.dump(tfile)
        
        if self.config.local_log_dest:
            dest = os.path.join(self.config.local_log_dest,logname)
            try: os.makedirs(os.path.dirname(dest))
            except OSError: pass
            shutil.copy2(tfile,dest)
        
        if self.config.log_dest:
            self.rclone.copylog('A',tfile,os.path.join(self.config.log_dest,logname))
            self.rclone.copylog('B',tfile,os.path.join(self.config.log_dest,logname))
                
    def dry_run(self):
        log('(DRY RUN)')
        for AB in 'AB':
            for attr in ['del','backup','moves']:
                for file in getattr(self,f'{attr}{AB}'):
                    if attr == 'moves':
                        log(f"(DRY RUN) on {AB}: move '{file[0]}' --> '{file[1]}'")
                    else:
                        log(f"(DRY RUN) on {AB}: {attr} '{file}'")
        sumA = utils.file_summary([self.currA.query_one(Path=f) for f in self.transA2B])
        log(f'(DRY RUN) A >>> B {sumA}')
        sumB = utils.file_summary([self.currB.query_one(Path=f) for f in self.transB2A])
        for file in self.transA2B:
            log(f"(DRY RUN) Transfer A >>> B: '{file}'")
        log(f'(DRY RUN) B >>> A {sumB}')
        for file in self.transB2A:
            log(f"(DRY RUN) Transfer B >>> A: '{file}'")
            
    def echo_queues(self,descr=''):
        debug(f'Printing Queueus {descr}')
        for attr in ['new','del','tag','backup','trans','moves']:
            for AB in 'AB':
                BA = list(set('AB')- set(AB))[0]
                if attr == 'trans':
                    pa = f'{attr}{AB}2{BA}'
                else:
                    pa = f'{attr}{AB}'
                debug('   ',pa,getattr(self,pa))
    
    def remove_common_files(self):
        """
        Removes files common in the curr list from the curr lists and,
        if present, the prev lists
        """
        config = self.config
        commonPaths = set(file['Path'] for file in self.currA)
        commonPaths.intersection_update(file['Path'] for file in self.currB)

        c = 0
        for path in commonPaths:
            q = {'Path':path}
            # We KNOW they exists for both
            fileA,fileB = self.currA[q],self.currB[q]
            if not self.compare(fileA,fileB):
                continue
            
            # Remove it from all lists
            for obj in [self.currA,self.prevA,self.currB,self.prevB]:
                try:
                    obj.remove(q)
                except ValueError: # not in a prev list
                    continue
            
            c += 1
        debug(f'Found {len(commonPaths)} common paths with {c} matching files')

    def process_non_common(self):
        """
        Create action lists (some need more processing) and then populate 
        with all remaining files
        """
        config = self.config    
        
        # These are for classifying only. They are *later* translated
        # into actions
        self.newA,self.newB = list(),list() # Will be moved to transfer
        self.delA,self.delB = list(),list() # Action but may be modified by move tracking later
        self.tagA,self.tagB = list(),list() # Will be tagged (moved) then transfer
        
        # These will not need be modified further. 
        self.backupA,self.backupB = list(),list()
        self.transA2B,self.transB2A = list(),list()
        self.movesA,self.movesB = list(),list() # Not used here but created for use elsewhere
        
        # All paths. Note that common paths with equal files have been cut
        allPaths = set(file['Path'] for file in self.currA)
        allPaths.update(file['Path'] for file in self.currB)

        # NOTE: Final actions will be done in the following order
        # * Delete
        # * Backup -- Always assign but don't perform if --no-backup
        # * Move (including tag)
        # * Transfer
        for path in allPaths:
            fileA = self.currA[{'Path':path}]
            fileB = self.currB[{'Path':path}]
            fileBp = self.prevB[{'Path':path}]
            fileAp = self.prevA[{'Path':path}]

            if fileA is None: # fileB *must* exist
                if not fileBp:
                    debug(f"File '{path}' is new on B")
                    self.newB.append(path) # B is new
                elif self.compare(fileB,fileBp):
                    debug(f"File '{path}' deleted on A")
                    self.delB.append(path) # B must have been deleted on A
                else:
                    log(f"DELETE CONFLICT: File '{path}' deleted on A but modified on B. Transfering")
                    self.transB2A.append(path)
                continue
                    
            if fileB is None: # fileA *must* exist
                if not fileAp:
                    debug(f"File '{path}' is new on A")
                    self.newA.append(path) # A is new
                elif self.compare(fileA,fileAp):
                    debug(f"File '{path}' deleted on A")
                    self.delA.append(path) # A must have been deleted on B
                else:
                    log(f"DELETE CONFLICT: File '{path}' deleted on B but modified on A. Transfering")
                    self.transA2B.append(path)
                continue
                  
            # We *know* they do not agree since this common ones were removed.
            # Now must decide if this is a conflict or just one was modified
            compA = self.compare(fileA,fileAp)
            compB = self.compare(fileB,fileBp)
            
            if compA and compB:
                # This really shouldn't happen but if it does, just move on to
                # conflict resolution
                debug(f"'{path}': Both A and B compare to prev but do not agree. This is ODD.")
            elif not compA and not compB:
                # Do nothing but note it. Deal with conflict below
                debug(f"'{path}': Neither compare. Both modified or both new")
            elif compA and not compB: # B is modified, A is not
                debug(f"'{path}': Modified on B only")
                self.transB2A.append(path)
                self.backupA.append(path)  
                continue
            elif not compA and compB: # A is modified, B is not
                debug(f"'{path}': Modified on A only")
                self.transA2B.append(path)
                self.backupB.append(path)  
                continue
            
            # They conflict!
            
            mA,mB = None,None
            if config.compare == 'mtime':
                mA = fileA.get('mtime',None)
                mB = fileB.get('mtime',None)
                txtA = utils.unix2iso(mA)
                txtB = utils.unix2iso(mB)
                if not mA or not mB:
                    warning.warn('No mtime found. Resorting to size')
                        
            if not mA or not mB: # Either never set for non-mtime compare or no mtime listed
                mA = fileA['Size']
                mB = fileB['Size']
                txtA = '{:0.2g} {:s}'.format(*utils.bytes2human(mA,short=False))
                txtB = '{:0.2g} {:s}'.format(*utils.bytes2human(mB,short=False))
            
            txt = (f"CONFLICT '{path}'. "
                   f"A: {txtA}, B: {txtB}. "
                   f"Resolving with mode '{config.conflict_mode}' ")
            
            if config.conflict_mode == 'A':
                self.transA2B.append(path)
                self.backupB.append(path)
            elif config.conflict_mode == 'B':
                self.transB2A.append(path)
                self.backupA.append(path)
            elif config.conflict_mode == 'tag' \
            or not mA \
            or not mB \
            or mA == mB:
                self.tagA.append(path) # Tags will *later* be added to transfer queue
                self.tagB.append(path)
            elif mA > mB:
                if config.conflict_mode == 'newer':
                    self.transA2B.append(path)
                    self.backupB.append(path)
                    txt += '(keep A)'
                elif config.conflict_mode == 'older':
                    self.transB2A.append(path)
                    self.backupA.append(path)
                    txt += '(keep B)'
                elif config.conflict_mode == 'newer_tag':
                    self.transA2B.append(path)
                    self.tagB.append(path)
                    txt += '(keep A)'
            elif mA < mB:
                if config.conflict_mode == 'newer':
                    self.transB2A.append(path)
                    self.backupA.append(path)
                    txt += '(keep B)'
                elif config.conflict_mode == 'older':
                    self.transA2B.append(path)
                    self.backupB.append(path)
                    txt += '(keep A)'
                elif config.conflict_mode == 'newer_tag':
                    self.transB2A.append(path)
                    self.tagA.append(path)
                    txt += '(keep B)'
            else:
                raise ValueError('Comparison Failed. Please report to developer') # Should not be here
            log(txt)
                                
    def track_moves(self,remote):
        config = self.config
        AB = remote
        BA = list(set('AB')- set(AB))[0]
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]      
        
        rename_attrib = getattr(config,f'renames{AB}')
        if not rename_attrib:
            return
        
        # A file move is *only* tracked if it marked
        # (1) Marked as new
        # (2) Can be matched via renames(A/B) to a remaining file in prev
        # (3) The same file is marked for deletion (No need to check anything 
        #     since a file is *only* deleted if it was present in the last sync
        #     and unmodified. So it is safe to move it
        
        new = getattr(self,f'new{AB}') # on remote -- list
        
        curr = getattr(self,f'curr{AB}') # on remote -- DictTable
        prev = getattr(self,f'prev{AB}') # on remote -- DictTable
        
        delOther = getattr(self,f'del{BA}') # On OTHER side -- list
        moveOther = getattr(self,f'moves{BA}') # on OTHER side - list

        if rename_attrib == 'hash':
            try:
                # Note that this will not add it to all files but it isn't
                # getting saved
                utils.add_hash_compare_attribute(curr,prev)
            except ValueError:
                log(f'WARNING: Could not track moves on {AB} due to missing hashes')
                return
        elif rename_attrib == 'inode': # In case they were not indexed
            curr.add_fixed_attribute('inode')
            prev.add_fixed_attribute('inode')
        
        for path in new[:]: # (1) Marked as new. Make sure to iterate a copy
            debug(f"Looking for moves on {AB}: '{path}'")
            currfile = curr[{'Path':path}]
            
            if rename_attrib == 'hash':
                query = {'common_hash':currfile.get('common_hash',None)}
            else: # All the rest
                query = {'Size':currfile['Size']}
                if rename_attrib == 'inode':
                    query['inode'] = currfile['inode']
            prevfiles = list(prev.query(query))
            
            if rename_attrib in ['mtime','inode']: # comapre with tol
                prevfiles = [f for f in prevfiles if abs(f['mtime'] - currfile['mtime']) < config.dt]
            
            if not prevfiles:
                debug(f"No matches for '{path}' on {AB}")
                continue
                
            if len(prevfiles) > 1: # TOTEST
                log(f"Too many possible previous files for '{path}' on {AB}")
                for f in prevfiles:
                    log(f"   '{f['Path']}'")
                continue
            prevpath = prevfiles[0]['Path'] # (2) Previous file
            
            if prevpath not in delOther:
                debug(f"File '{path}' moved from '{prevpath}' on {AB} but modified")
                continue
            
            # Move it instead
            new.remove(path)
            delOther.remove(prevpath)
            moveOther.append((prevpath,path))
            debug(f"Move found: on {BA}: '{prevpath}' --> '{path}'")
    
    def process_new_tags(self,remote):
        """Process new into transfers and tags into moves"""
        config = self.config
        AB = remote
        BA = list(set('AB')- set(AB))[0]
        remote = {'A':config.remoteA,'B':config.remoteB}[remote]
        
        new = getattr(self,f'new{AB}')
        tag = getattr(self,f'tag{AB}')
        trans = getattr(self,f'trans{AB}2{BA}')
        moves =  getattr(self,f'moves{AB}')

        for file in tag:
            dest = f'{file}.{self.now_compact}.{AB}'
            moves.append((file,dest))
            debug(f"Added '{file}' --> '{dest}'")
            
            trans.append(dest) # moves happen before transfers!
        
        trans.extend(new)
    
    def check_lock(self,remote='both',error=True):
       # import ipdb;ipdb.set_trace()
        AB = remote
        if remote == 'both':
            locks = [] # Get BOTH before errors
            locks.extend(self.check_lock(remote='A',error=False))
            locks.extend(self.check_lock(remote='B',error=False))
        else:        
            curr = getattr(self,f'curr{AB}')
            locks = curr.query(curr.Q.filter(lambda a:a['Path'].startswith('.syncrclone/LOCK')))
            locks = [f'{AB}:{os.path.relpath(l["Path"],".syncrclone/LOCK/")}' for l in locks]
    
        if not error:
            return locks
        
        if locks:
            msg = ['Remote(s) locked:']
            for lock in locks:
                msg.append(f'  {lock}')
            raise LockedRemoteError('\n'.join(msg))
            
    
    def compare(self,file1,file2):
        """Compare file1 and file2 (may be A or B or curr and prev)"""
        config = self.config
        compare = config.compare # Make a copy as it may get reset (str is immutable so no need to copy)
                
        if not file1:
            return False
        if not file2:
            return False
        
    
        if compare == 'hash':
            h1 = file1.get('Hashes',{})
            h2 = file2.get('Hashes',{})
            
            # Just because there are common hashes, does *not* mean they are
            # all populated. e.g, it could be a blank string
            common = set(h1).intersection(h2)
            all1 = all(h1[k] for k in common)
            all2 = all(h2[k] for k in common)

            if common and all1 and all2:
                return all(h1[k] == h2[k] for k in common)
            
            if not common: 
                msg = 'No common hashes found and/or one or both remotes do not provide hashes'
            else:
                msg = 'One or both remotes are missing hashes'
            
            if config.hash_fail_fallback:
                msg += f". Falling back to '{config.hash_fail_fallback}'"        
                warnings.warn(msg)
                compare = config.hash_fail_fallback
            else:
                raise ValueError(msg)
        
        # Check size either way
        if file1['Size'] != file2['Size']:
            return False
        
        if compare == 'size': # No need to compare mtime
            return True
        
        if 'mtime' not in file1 or 'mtime' not in file2:
            warnings.warn(f"File do not have mtime. Using only size")
            return True # Only got here size is equal
        
        return abs(file1['mtime'] - file2['mtime']) <= config.dt









