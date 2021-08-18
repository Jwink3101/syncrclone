#!/usr/bin/env python
"""
Tests!
"""
import os,sys
import itertools
import shutil
import glob
import time
import warnings
import zlib,lzma,json

import testutils

import pytest

p = os.path.abspath('../')
if p not in sys.path:
    sys.path.insert(0,p)
from syncrclone import set_debug
import syncrclone.cli
import syncrclone.utils
import syncrclone.main

# Make it return
syncrclone.cli._RETURN = True

randstr = syncrclone.utils.random_str

def lprod(*a,**k):
    return list(itertools.product(*a,**k))

PWD0 =  os.path.abspath(os.path.dirname(__file__))
os.chdir(PWD0)

def exists(path):
    return bool(glob.glob(path))

def get_MAIN_TESTS():
    renamesA = renamesB = ('size','mtime','hash','inode') # Do not include None as we want to track them
    compares = ('size','mtime','hash')
    for renameA,renameB,compare in itertools.product(renamesA,renamesB,compares):
        yield 'A',renameA,'B',renameB,compare

MAIN_TESTS = []
MAIN_TESTS.append(['cryptA:','mtime','B','hash','mtime']) # To also test the construction of remote tests

# Adds 48 combinations. For something more reasonable,comment this out and inclde the following:
MAIN_TESTS.extend(get_MAIN_TESTS()) 
# MAIN_TESTS.extend([
#     ['A','hash','B','hash','hash'], # Most secure
#     ['A','hash','B','hash','mtime'], # Good compare when no common hash
#     ['A','size','B','size','size'], # Most easily tricked but will still work on this test
# ])
    

@pytest.mark.parametrize("remoteA,renamesA,remoteB,renamesB,compare",MAIN_TESTS)
def test_main(remoteA,renamesA,
              remoteB,renamesB,
              compare,
              interactive=False):
    """
    Main test with default settings (if the defaults change, this will need to
    be updated. A few minor changes from the defaults are also made
    
    More edge cases and specific settings are played with later
    
    """
    set_debug(False)
    print(remoteA,remoteB)
    test = testutils.Tester('main',remoteA,remoteB)
    
    ## Config
    test.config.reuse_hashesA = False # Also shouldn't compute them
    test.config.renamesA = renamesA
    
    test.config.reuse_hashesB = True
    test.config.renamesB = renamesB
    test.config.rclone_flags = ['--fast-list'] # Will be ignored if not supported but good to have otherwise
    
    test.config.filter_flags = ['--filter','+ /yes/**',
                                '--filter','- *.no']
    test.config.compare = compare
    test.config.conflict_mode = 'newer_tag' # Deprecated. Update in the future
    
    test.config.log_dest = 'logs/'    
    test.write_config()
    
    ## Initial files
    test.write_pre('A/leave_alone.txt','do not touch')
    
    # We use newer_tag so we can confirm that these are *NOT* considered
    # conflicts. They should be backed up *and*
    test.write_pre('A/EditOnA.txt','Edit on A') 
    test.write_pre('A/EditOnB.txt','Edit on B')
    
    # Give it extra so size is unique
    test.write_pre('A/MoveOnA.txt','Move on A' + randstr(52))
    test.write_pre('A/MoveOnB.txt','Move on B' + randstr(100)) 
    test.write_pre('A/MoveOnAB.txt','Move on Both' + randstr(74)) 
    
    test.write_pre('A/MoveEditOnA.txt','Move and Edit on A')
    test.write_pre('A/MoveEditOnB.txt','Move and Edit on B')
    
    test.write_pre('A/EditOnBoth_Anewer.txt','A will be newer')
    test.write_pre('A/EditOnBoth_Bnewer.txt','B will be newer')    

    test.write_pre('A/MoveEditOnBoth_Bnewer.txt','Will move and edit on both sides' + randstr(10))

    test.write_pre('A/delA.txt','delete on A')
    test.write_pre('A/delB.txt','delete on B')
    test.write_pre('A/delA modB.txt','delA but mod on B')
    test.write_pre('A/delB modA.txt','delB but mod on A')
    
    test.write_pre('A/unic°de and space$.txt','UTF8')

    test.write_pre('A/common_contentAfter0.txt','abc xyz')
    test.write_pre('A/common_contentAfter1.txt','abc xy')

    test.write_pre('A/common_contentBefore0.txt','ABC XYZ')
    test.write_pre('A/common_contentBefore1.txt','ABC XYZ')

    ## Run
    test.setup()

    ## Modify
    test.write_post('A/EditOnA.txt','Edited on A',mode='at')
    test.write_post('B/EditOnB.txt','Edited on B',mode='at')
    
    test.move('A/MoveOnA.txt','A/sub/MovedOnA.txt') # move and rename
    test.move('B/MoveOnB.txt','B/sub2/MoveOnB.txt') # just move
    test.move('A/MoveOnAB.txt','A/MovedOnAB.txt')
    test.move('B/MoveOnAB.txt','B/MovedOnAB.txt')
    
    test.move('A/MoveEditOnA.txt','A/MovedEditOnA.txt')
    test.move('B/MoveEditOnB.txt','B/MovedEditOnB.txt')
    test.write_post('A/MovedEditOnA.txt','Move and Edit on A',mode='at')
    test.write_post('B/MovedEditOnB.txt','Move and Edit on B',mode='at')

    # recall when comparing by size, When comparing by size, older --> smaller, newer --> larger
    test.write_post('A/EditOnBoth_Anewer.txt','AAAa',mode='at',add_dt=50) # larger too
    test.write_post('A/EditOnBoth_Bnewer.txt','AAA',mode='at',add_dt=0)
    test.write_post('B/EditOnBoth_Anewer.txt','BBB',mode='at',add_dt=0)
    test.write_post('B/EditOnBoth_Bnewer.txt','BBBb',mode='at',add_dt=50) # larger too
    
    test.move('A/MoveEditOnBoth_Bnewer.txt','A/MovedEditedOnBoth_Bnewer.txt')
    test.move('B/MoveEditOnBoth_Bnewer.txt','B/MovedEditedOnBoth_Bnewer.txt')
    test.write_post('A/MovedEditedOnBoth_Bnewer.txt','A', mode='at')
    test.write_post('B/MovedEditedOnBoth_Bnewer.txt','BB', mode='at',add_dt=50) # larger too
    
    os.remove('A/delA.txt')
    os.remove('B/delB.txt')
    test.write_post('A/delB modA.txt','mod on A',mode='at')
    os.remove('B/delB modA.txt')
    test.write_post('B/delA modB.txt','mod on B',mode='at')
    os.remove('A/delA modB.txt')
    
    test.write_post('A/newA.txt','New on A')
    test.write_post('B/newB.txt','New on B')
    
    test.write_post('A/newA.no','New on A and no') # use new to test exclusions too
    test.write_post('B/newB.no','New on B and no')
    test.write_post('A/yes/newA.yes.no','New on A and no but yes')
    test.write_post('B/yes/newB.yes.no','New on B and no but yes')
    
    test.write_post('B/unic°de and space$.txt','works',mode='at')
    
    # These don't need to be tested other than not showing a diff
    test.write_post('A/common_contentAfter1.txt','abc xyz')
    test.write_post('B/common_contentBefore1.txt','ABC XYZW')
    
    print('-='*40)
    print('=-'*40)
    args = ['--interactive'] if interactive else []
    obj = test.sync(args)
    
    ## Confirm!
    print('-'*100)
    diffs = test.compare_tree()
    
    # Exclusions except when filters to allow!
    assert {('missing_inA', 'newB.no'), ('missing_inB', 'newA.no')} == diffs 
    
    stdout = ''.join(test.synclogs[-1])
    # Check on A from now on!

    # Edits -- Should *NOT* tag but *should* backup
    assert test.read('A/EditOnA.txt') == 'Edit on AEdited on A',"mod did not propogate"
    assert test.read('A/EditOnB.txt') == 'Edit on BEdited on B',"mod did not propogate"
    assert not exists('A/EditOnA.txt.*'),'Should NOT have been tagged'
    assert not exists('A/EditOnB.txt.*'),'Should NOT have been tagged'
    assert test.globread('B/.syncrclone/backups/*_B/EditOnA.txt') == 'Edit on A','not backed up'
    assert test.globread('A/.syncrclone/backups/*_A/EditOnB.txt') == 'Edit on B','not backed up'
        
    # Moves w/o edit
    assert not exists('A/MoveOnB.txt')
    assert exists('A/sub2/MoveOnB.txt')
    assert "Move on A: 'MoveOnB.txt' --> 'sub2/MoveOnB.txt'" in stdout

    assert not exists('A/MoveOnA.txt')
    assert exists('A/sub/MovedOnA.txt')
    assert "Move on B: 'MoveOnA.txt' --> 'sub/MovedOnA.txt'" in stdout
    
    assert not exists('A/MoveOnAB.txt')
    assert exists('A/MovedOnAB.txt')
    assert not "move A: 'MoveOnAB.txt' --> 'MovedOnAB.txt'" in stdout
    assert not "move B: 'MoveOnAB.txt' --> 'MovedOnAB.txt'" in stdout
    
    # moves with edit -- should not have been tracked
    assert not exists('A/MoveEditOnA.txt')
    assert exists('A/MovedEditOnA.txt')
    assert 'MovedEditOnA.txt: Copied' in stdout,'Not copied. May be rclone log change'
    
    assert not exists('A/MoveEditOnB.txt')
    assert exists('A/MovedEditOnB.txt')
    assert 'MovedEditOnB.txt: Copied' in stdout,'Not copied. May be rclone log change'

    assert test.read('A/EditOnBoth_Anewer.txt') == 'A will be newerAAAa'
    assert test.read('A/EditOnBoth_Bnewer.txt') == 'B will be newerBBBb'
    assert exists('A/EditOnBoth_Anewer.*.B.txt'), "Not tagged"
    assert exists('A/EditOnBoth_Bnewer.*.A.txt'), "Not tagged"

    
    assert test.read('B/MovedEditedOnBoth_Bnewer.txt').endswith('BB')
    
    assert not exists('A/delA.txt')
    assert not exists('A/delB.txt')
    assert exists('A/.syncrclone/backups/*_A/delB.txt'), "did not backup"
    assert exists('B/.syncrclone/backups/*_B/delA.txt'), "did not backup"

    assert exists('A/delB modA.txt') # Should not have been deleted
    assert "DELETE CONFLICT: File 'delB modA.txt' deleted on B but modified on A. Transfering" in stdout
    assert exists('A/delA modB.txt')
    assert "DELETE CONFLICT: File 'delA modB.txt' deleted on A but modified on B. Transfering" in stdout
    
    assert exists('A/newA.txt')
    assert exists('A/newB.txt')

    assert exists('A/yes/newA.yes.no')
    assert exists('A/yes/newB.yes.no')

    assert test.read('A/unic°de and space$.txt') == 'UTF8works'
    assert exists('A/.syncrclone/backups/*_A/uni*.txt'),'did not back up'
    
    os.chdir(PWD0)

@pytest.mark.parametrize("attrib",('size','mtime','hash','inode',None))
def test_move_attribs(attrib):
    """
    Test moves over various conditions for each type of move tracking
    including modified sizes. 
    
    7 files: 1,2,3,C,D,4,5 all have different mtimes and are moved
    
    - 1,2 are unique content and size 
    - 3,C are unique content but same size
    - D,4 are the same content and size
    - 5 is unique content and size but it's modified
    
    See Truth Table in the code
    
    Only test with local A (as it supports inode). B doesn't matter since
    moves are only tracked on A.
    """
    remoteA = 'A'
    remoteB = 'B'
    print(attrib)
    set_debug(True)

    print(remoteA,remoteB)
    test = testutils.Tester('renames',remoteA,remoteB)

    ## Config
    test.config.reuse_hashesA = False
    test.config.renamesA = attrib
    if attrib == 'size': # Presumably we do not have mtime
        test.config.compare = 'size'
    test.config.dt = 0.001
    test.write_config()

    # Setup
    test.write_pre('A/file1.txt','1')
    test.write_pre('A/file2.txt','12')
    test.write_pre('A/file3.txt','123')
    test.write_pre('A/fileC.txt','ABC')
    
    test.write_pre('A/fileD.txt','ABCD')
    test.write_pre('A/file4.txt','ABCD')
    
    test.write_pre('A/file5.txt','12345')
    
    test.setup()

    for c in '123CD45':
        shutil.move(f'A/file{c}.txt',f'A/file{c}_moved.txt')

    test.write_post('A/file5_moved.txt','12345') # Changes mtime but same content 

    print('-='*40)
    print('=-'*40)

    test.sync()
    stdout = ''.join(test.synclogs[-1])

    ## Truth Table
    if not attrib:
        notmoved = '123CD45'
        moved = too_many = ''
    elif attrib == 'size':
        # Size alone won't care about the mod. Note that compare is 'size' for 
        # this one too since that is likely all you would have
        moved = '125' 
        too_many = '3CD4'
        notmoved = ''    
    elif attrib == 'mtime':
        moved = '1234CD'
        too_many = ''
        notmoved = '5'
    elif attrib == 'inode':
        moved = '123CD4'
        too_many = ''
        notmoved = '5'
    elif attrib == 'hash':
        moved = '123C5'
        too_many = 'D4'
        notmoved = ''    

    for c in moved:
        assert f"Move on B: 'file{c}.txt' --> 'file{c}_moved.txt'" in stdout,f"{attrib} file{c} didn't move"
    for c in too_many:
        assert f"Too many possible previous files for 'file{c}_moved.txt' on A" in stdout, f"{attrib} file{c} failed multiple"
    for c in notmoved:
        assert f"Move on B: 'file{c}.txt' --> 'file{c}_moved.txt'" not in stdout,f"{attrib} file{c} moved"

    os.chdir(PWD0)

def test_reuse_hash():
    remoteA = 'A'
    remoteB = 'B'
    set_debug(True)

    print(remoteA,remoteB)
    test = testutils.Tester('reusehash',remoteA,remoteB)

    ## Config
    test.config.reuse_hashesA = True
    test.config.reuse_hashesB = False
    test.config.compare = 'hash'
    test.config.filter_flags = ['--filter','- .*','--filter','- .**/']
    test.write_config()

    # Setup
    test.write_pre('A/file00.txt','0')
    test.setup()
    
    test.write_post('A/fileA1.txt','A1')
    test.write_post('B/fileB1.txt','B1')
    
    print('-='*40);print('=-'*40)
    test.sync(['--debug']) # Must debug to query for the msg of calling for me
    stdout = ''.join(test.synclogs[-1])
    
    assert "A: Updated 1. Fetching hashes for 1" in stdout
    assert "B: Updated 1. Fetching hashes for 1" not in stdout
    
    # Do one more test to cover the code path of not needing to get more hashes
    # such as if nothing changed from the last sync
    test.sync()    

    os.chdir(PWD0)

def test_no_hashes():
    remoteA = 'A'
    remoteB = 'cryptB:' # Crypt does not have hashes
    set_debug(False)

    print(remoteA,remoteB)
    test = testutils.Tester('nocommon',remoteA,remoteB)

    ## Config
    test.config.compare = 'hash'
    test.config.hash_fail_fallback = 'mtime'
    test.write_config()

    # Setup
    test.write_pre('A/file00.txt','0')
    test.setup() # This has a sync that will throw the warnings
    stdout = ''.join(test.synclogs[-1])
    
    # This will have to change if I change the verbage
    assert "WARNING No common hashes found and/or one or both remotes do not provide hashes. Falling back to 'mtime'" in stdout
    
    os.chdir(PWD0)

@pytest.mark.parametrize("conflict_mode,tag_conflict",itertools.product(('A','B','older','newer','smaller','larger','tag'),(True,False)))
def test_conflict_resolution(conflict_mode,tag_conflict):
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('conflicts',remoteA,remoteB)

    ## Config
    test.config.conflict_mode = conflict_mode
    test.config.tag_conflict = tag_conflict
    test.write_config()
    
    test.write_pre('A/file.txt','0')
    test.setup()

    test.write_post('A/file.txt','A')
    test.write_post('B/file.txt','Bb',add_dt=20) # newer and larger
    
    print('-='*40);print('=-'*40)
    test.sync(['--debug'])
    stdout = ''.join(test.synclogs[-1])

    diffs = test.compare_tree()
    assert diffs == set()
    
    files = [os.path.relpath(f,'A/') for f in testutils.tree('A/')]
    
    A = exists('A/file.txt') and test.read('A/file.txt') == 'A'
    B = exists('A/file.txt') and test.read('A/file.txt') == 'Bb'
    tA = any(file.endswith('.A.txt') for file in files)
    tB = any(file.endswith('.B.txt') for file in files)
   
    if conflict_mode in ['A','older','smaller']:
        res = (A,B) == (True,False)
        tag = (tA,tB) == (False,True) if tag_conflict else (False,False)
    elif conflict_mode in ['B','newer','larger']:
        res =  (A,B) == False,True
        tag = (tA,tB) == (True,False) if tag_conflict else (False,False)     
    elif conflict_mode in ['tag']:
        res =  (A,B) == (False,False)
        tag = (tA,tB) == (True,True)
    else:
        raise ValueError('Not studied') # Should not be here
    assert res, f'Wrong res {A,B}, mode {conflict_mode,tag_conflict}'
    assert tag, f'Wrong tag {tA,tB} mode {conflict_mode,tag_conflict}'
    os.chdir(PWD0)


@pytest.mark.parametrize("backup,sync",itertools.product((True,False,None),(True,False)))
def test_backups(backup,sync):
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('backups',remoteA,remoteB)   
    test.config.conflict_mode = 'newer'
    test.config.sync_backups = sync
    test.write_config()
    
    test.write_pre('A/ModifiedOnA.txt','A')
    test.write_pre('A/DeletedOnA.txt','A')
    
    test.write_pre('A/ModifiedOnB.txt','B')
    test.write_pre('A/DeletedOnB.txt','B')
    
    test.setup()
    
    os.remove('A/DeletedOnA.txt')
    os.remove('B/DeletedOnB.txt')
    test.write_post('A/ModifiedOnA.txt','A1')
    test.write_post('B/ModifiedOnB.txt','B1')
    
    print('-='*40);print('=-'*40)
    if backup:
        test.sync()
    elif backup is None: # Same as False but set it in the configs
        test.config.backup = False
        test.write_config()
        test.sync()
    else:
        test.sync(['--no-backup'])
    
    # Compare
    diffs = test.compare_tree()
    assert diffs == set()
    
    assert exists('A/ModifiedOnA.txt') and test.read('A/ModifiedOnA.txt') == 'A1'
    assert exists('A/ModifiedOnB.txt') and test.read('A/ModifiedOnB.txt') == 'B1'
    
    backedA = glob.glob('A/.*/backups/*_A/*') # only one level deep
    backedB = glob.glob('B/.*/backups/*_B/*')
    
    # synced backups
    backedAonB = glob.glob('B/.*/backups/*_A/*') # only one level deep
    backedBonA = glob.glob('A/.*/backups/*_B/*')
        
    if backup:
        assert len(backedA) == len(backedB) == len(backedB) == len(backedB) == 2
        
        # The B files were modified so these should all read B
        assert all(test.read(f) == 'B' for f in backedA) # not B1
        assert all(file.endswith('B.txt') for file in backedA)
    
        # The A files were modified so these should all read A
        assert all(test.read(f) == 'A' for f in backedB) # not A1
        assert all(file.endswith('A.txt') for file in backedB)
    else: # False and None
        assert  len(backedA) == \
                len(backedB) == \
                len(backedB) == \
                len(backedB) == \
                len(backedAonB) == \
                len(backedBonA) == 0
    
    if sync:
        # Hash all of the files and make sure they all agree. Use the name 
        # without A or B. Dict equality will include
        hashesA = {f[2:]:testutils.adler32(f) for f in backedA}
        hashesB = {f[2:]:testutils.adler32(f) for f in backedB}
        hashesAonB = {f[2:]:testutils.adler32(f) for f in backedAonB}
        hashesBonA = {f[2:]:testutils.adler32(f) for f in backedBonA}
        assert hashesA == hashesAonB,'backups were not synced for A'
        assert hashesB == hashesBonA,'backups were not synced for B'

        
    os.chdir(PWD0)

def test_dry_run():
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('backups',remoteA,remoteB)   
    test.config.renamesA = 'mtime'
    test.write_config()
                                        # Expected conflicts
    test.write_pre('A/mod','0')         # 1
    test.write_pre('A/move','01')       # 2
    test.write_pre('A/movemod','012')   # 2
    test.write_pre('A/del','0123')      # 1
    
    test.setup()
    
    test.write_post('A/mod','A')
    shutil.move('A/move','A/moved')
    shutil.move('A/movemod','A/movedmod');test.write_post('A/movedmod','ABC')
    os.remove('A/del')
    test.write_post('A/new','01234')    # 1
    
    presync_compare = test.compare_tree()
    assert len(presync_compare)
    
    print('-='*40);print('=-'*40)
    test.sync(['--dry-run'])
    
    assert presync_compare == test.compare_tree()
    os.chdir(PWD0)
    
def test_logs():
    remoteA = 'cryptA:'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('logs',remoteA,remoteB)   
    test.config.renamesA = 'mtime'
    test.config.log_dest = 'logs'
    test.write_config()
    
    test.write_pre('A/file','0')
    
    test.setup()
    time.sleep(1.1) # To make sure we don't overwrite logs
    
    test.write_post('A/fileA','A')
    os.remove('A/file')
    test.write_post('B/fileB','BB')
    
    print('-='*40);print('=-'*40)
    test.sync()
    stdout = ''.join(test.synclogs[-1])
    
    assert test.compare_tree() == set() # Will includes logs
    logs = sorted(glob.glob('A/logs/*'))
    assert len(logs) == 2, "should have two. setup + sync"
    
    # We know from all of the other tests that stdout (above) works otherwise
    # they would fail. So just check that it's the same
    with open(logs[-1]) as f:
        f.read().strip() == stdout.strip()
    
    
    os.chdir(PWD0)

def test_three_way():
    """
    Test three way. In order to make this work within my own testing framework,
    I have to switch the configs manually as opposed to having multiple
    configurations. It isn't ideal but works for testing
    """
    set_debug(False)

    test = testutils.Tester('three','A','B')

    # Just use simple comparisons
    test.config.renamesA = test.config.renamesB = 'hash'
    test.config.name = 'AB'
    test.write_config()
    
    test.write_pre('A/file1.txt','file1')
    test.write_pre('A/file2.txt','file1')

    ## Run
    test.setup()
    
    test.write_post('A/file1.txt','mod',mode='at')
    test.write_post('B/file3.txt','file3')
    
    test.sync()
    
    # Modify it to sync A <--> C
    test.config.remoteB = 'C'
    test.config.name = 'AC'
    test.write_config()
    
    test.write_pre('C/fileC.txt','this is on C')
    
    # This *just* makes sure that we don't have a false positive and we
    # are hacking it to compare C
    assert {('missing_inA', 'fileC.txt'),
            ('missing_inB', 'file1.txt'),
            ('missing_inB', 'file2.txt'),
            ('missing_inB', 'file3.txt')} == test.compare_tree(A='A',B='C')
    
    test.sync()
    assert test.compare_tree(A='A',B='C') == set()
    assert test.compare_tree(A='A',B='B') == {('missing_inB', 'fileC.txt')} # Should still miss that
    
    test.config.remoteB = 'B'
    test.config.name = 'AB'
    test.write_config()
    
    test.sync()
    assert test.compare_tree(A='A',B='C') == set()
    assert test.compare_tree(A='A',B='B') == set()
    
    # Change it again but this time with  B <--> C
    test.config.remoteB = 'C'
    test.config.remoteA = 'B'
    test.config.name = 'BC'
    test.write_config()
    
    test.sync() # Shouldn't do anything
    
    test.write_post('B/file3.txt','file3 modified')
    
    test.sync()
    assert test.compare_tree(A='B',B='C') == set()
    assert test.read('C/file3.txt') == 'file3 modified'

    assert test.compare_tree(A='A',B='C') == {('disagree', 'file3.txt')}

    os.chdir(PWD0)
    
def test_locks():
    """
    Tests locking and breaking the lock
    """
    remoteA,remoteB = 'A','B'
    test = testutils.Tester('locks',remoteA,remoteB)
    
    ## Config
    test.write_config()
    
    test.write_pre('A/file1.txt','file1')
    
    sync = test.setup()
    
    test.write_post('B/file1.txt','mod',mode='at')
    
    # Set the lock
    sync.rclone.lock()
    
    # Try to sync. Note this is done with --debug so it will raise
    # errors. Test this even if configured not to set a lock
    test.config.set_lock = False
    test.write_config()

    with pytest.raises(syncrclone.main.LockedRemoteError):
        test.sync(['--debug'])

    test.config.set_lock = True
    test.write_config()
    
    # break the lock on both then sync
    test.sync(['--break-lock','both','--debug'])
    test.sync(['--debug']) # SHoudl work

    # Edit the file then set the lock again. Then test breaking each one
    test.write_post('A/file1.txt','mod again',mode='at')
    
    # Set the lock
    sync.rclone.lock()    
    
    with pytest.raises(syncrclone.main.LockedRemoteError):
        test.sync(['--debug'])
    
    test.sync(['--break-lock','A','--debug'])
    with pytest.raises(syncrclone.main.LockedRemoteError):
        test.sync(['--debug'])
        
    test.sync(['--break-lock','B','--debug'])
    test.sync(['--debug']) # Should work
    
    
    # Finally, make sure the error, even with --debug, is appropriate for
    # "breaking" what isn't locked
    try:
        os.rmdir('B/.syncrclone/LOCK/')
    except OSError:
        pass
        
    test.sync(['--break-lock','B','--debug'])
    

    os.chdir(PWD0)

def test_local_mode():
    """
    Tests using local mode
    """
    test = testutils.Tester('local','A','B')
    
    # Just test creating the new one
    os.makedirs('logs') # just so the next doesn't fail
    with open('logs/bla.txt','wt') as f: f.write('bla')
    test.sync(flags=['--new'],configpath='.')

    assert exists('.syncrclone/config.py')   
    os.remove('.syncrclone/config.py') # Remove it for nwp
    
    test.config.remoteA = '../'
    test.config.remoteB = '../../B'
    test.write_config()
    
    os.makedirs('A/.syncrclone')
    shutil.move('config.py','A/.syncrclone/config.py')
    
    
    # Now make a simple test
    test.write_pre('A/file1.txt','file1')
    
    test.setup(configpath='A',flags=[]) # Specified as a dir
    
    test.write_post('A/file1.txt','append',mode='at')
    test.write_post('B/file2.txt','file2')

    print('-='*40)
    print('=-'*40)
    test.sync(configpath='A',flags=[]) # Specified
    
    assert test.compare_tree() == set()
    assert set(testutils.tree('A')) == {'A/file1.txt', 'A/file2.txt'}
    assert test.read('A/file1.txt') == 'file1append'

def test_redacted_PW_and_modules_in_config_file():
    """
    Tests that RCLONE_CONFIG_PASS is redacted in debug mode. (even though
    it isn't needed. rclone will just ignore it)
    
    Also tests when you import modules in the config since that was
    an issue and has now been fixed.
    """
    test = testutils.Tester('redact','A','B')
    
    ## Config
    test.config.rclone_env.update({'RCLONE_CONFIG_PASS':'you_cant_see_me'})
    test.write_config()
    
    # Add module imports to test a regression
    with open(test.config._configpath,'at') as file:
        print('\nimport os,sys,subprocess,math,time',file=file)

    test.write_pre('A/test','test')
    # sync with debug and then look at the log
    test.setup(flags=['--debug'])
    stdout = ''.join(test.synclogs[-1])
    
    assert 'RCLONE_CONFIG_PASS' in stdout,'not debug'
    assert '**REDACTED**' in stdout,'redacted not seen'
    assert 'you_cant_see_me' not in stdout,'I see your password!'

def test_and_demo_exclude_if_present():
    """
    The --exclude-if-present can lead to issues as the filters cannot be applied
    symmetrically to both sides and can make an exclude look like a delete
    
    Demonstrate (a) it working properly when on both sides and (b)
    the issues it can cause
    
    """
    test = testutils.Tester('exclude_present','A','B')
    
    test.config.filter_flags = ['--exclude-if-present','ignore']
    test.write_config()
    
    ## Working properly
    test.write_pre('A/file1','file1')

    test.write_pre('A/sub/file2','file2')
    test.write_pre('A/sub/ignore','')
    
    test.write_pre('A/sub2/file3','file3')
    
    test.setup()
    
    test.write_post('A/sub/onA','onA')
    test.write_post('B/sub/onB','onB')
    
    print('-='*40);print('=-'*40)
    test.sync()
    
    diffs = test.compare_tree()
    assert diffs == {('missing_inB', 'sub/onA'), ('missing_inA', 'sub/onB')},'exclude did not work'
    
    ## Demonstrate the issue
    test.write_post('B/sub2/ignore','')
    
    test.sync()
    stdout = ''.join(test.synclogs[-1])
    
    # This will cause A/sub2/file3 to be deleted on A but remain on B
    diffs = test.compare_tree()
    assert {('missing_inA', 'sub2/ignore'),  # The ignore file isn't transfered
            ('missing_inA', 'sub2/file3'),   # It was deleted on A
            ('missing_inA', 'sub/onB'),  # These were from before   
            ('missing_inB', 'sub/onA')} == diffs
    
    assert "WARNING '--exclude-if-present' can cause issues. See readme" in stdout


version_tests = ['20200826.0.BETA',None]
@pytest.mark.parametrize("version",version_tests)
def test_version_warning(version):
    """
    This is to test version warnings or even errors (eventually)
    """
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)

    print(remoteA,remoteB)
    test = testutils.Tester('ver',remoteA,remoteB)

    ## Config
    if version:
        test.config._syncrclone_version = version
    test.write_config()

    # Setup
    test.write_pre('A/file00.txt','0')
    test.setup() # This has a sync that will throw the warnings
    stdout = ''.join(test.synclogs[-1])
    
    if version and version.startswith('20200825.0'):
        assert 'WARNING Previous behavior of conflict_mode changed. Please update your config' in stdout
    else:
        assert 'WARNING Previous behavior of conflict_mode changed. Please update your config' not in stdout
    
    # if different_version_match
    os.chdir(PWD0)

@pytest.mark.parametrize("legA,legB",((0,1),(1,0),(1,1)))
def test_legacy_filelist(legA,legB):
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('legacy_list',remoteA,remoteB)   
    test.config.name = 'legacytest'
    test.write_config()
    
    test.write_pre('A/fileADEL.txt','ADEL')
    test.write_pre('A/fileSTAY.txt','STAY')
    test.write_pre('A/fileBDEL.txt','BDEL')
    
    test.setup()
    
    os.remove('A/fileADEL.txt') # If we do not have the previous list, then it will copy back!
    os.remove('B/fileBDEL.txt') # If we do not have the previous list, then it will copy back!
    
    # Convert the lists
    def xz2zipjson(xz,zj):
        HEADER = b'zipjson\x00\x00' 
        with lzma.open(xz) as file:
            files = json.load(file)
        with open(zj,'wb') as file:
            file.write(HEADER + zlib.compress(json.dumps(files,ensure_ascii=False).encode('utf8')))
        os.unlink(xz)
    
    if legA:
        xz2zipjson('A/.syncrclone/A-legacytest_fl.json.xz','A/.syncrclone/A-legacytest_fl.zipjson')
    if legB:
        xz2zipjson('B/.syncrclone/B-legacytest_fl.json.xz','B/.syncrclone/B-legacytest_fl.zipjson')    
    
    print('-='*40);print('=-'*40)
    test.sync()
    
    # Compare
    diffs = test.compare_tree()
    assert not diffs
    assert not exists('A/fileADEL.txt')
    assert not exists('B/fileBDEL.txt')
    
    #test.sync() # Just to see if the log changed in manual testing
    os.chdir(PWD0)

@pytest.mark.parametrize("emptyA,emptyB",itertools.product([True,False,None],[True,False,None]))
def test_emptydir(emptyA,emptyB):
    # Because of the nature of how I set up the tests with any other remote,
    # they can't be tested directly since it is compared against another sync
    # of the files.
    #
    # While not idea, the removal of empty directories is pretty minor...
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('empty_dir',remoteA,remoteB)   
    test.config.filter_flags = ['--filter','- *.no']
    test.config.cleanup_empty_dirsA = emptyA
    test.config.cleanup_empty_dirsB = emptyB
    test.write_config()
    
    test.write_pre('A/move/move.txt','A') # Parents should delete
    test.write_pre('A/deep/deeper/deepest/dddeep.txt','DEEP') # parents should delete
    test.write_pre('A/del/del.txt','A') # parents should delete
    
    test.write_pre('A/delfilter/del2.txt','del2')
    
    os.makedirs('A/emptypre') # should remain
    os.makedirs('A/emptypre_deep/deeppre') # should remain
    
    test.setup()
    
    # remove the stuff and also newly empty dirs
    shutil.rmtree('A/del') # 1
    
    test.move('B/move','B/moved') # 2
    
    test.move('A/deep/deeper/deepest/dddeep.txt','A/shallow.txt') # 3
    shutil.rmtree('A/deep')
    
    shutil.rmtree('A/delfilter/') # 4: Removed on A but an ignored...
    test.write('B/delfilter/me.no','ignore') # ...file is still present
    
    os.makedirs('A/emptypostA/deeperpostA') # should remain
    os.makedirs('B/emptypostB') # should remain
    
    test.sync()
    
    # Compare
    diffs = test.compare_tree()
    assert diffs == {('missing_inA', 'delfilter/me.no')}

    # Previously empty and still should be there. Note that empty dirs
    # do not sync so do not check on each side. Also, only need to 
    # check the deepest since that implies the others are still there
    assert os.path.exists('A/emptypre')
    assert os.path.exists('A/emptypre_deep/deeppre') 
    assert os.path.exists('A/emptypostA/deeperpostA')
    
    assert os.path.exists('B/emptypostB')
    
    assert os.path.exists('B/delfilter/me.no') # 4 Make sure this was *not* deleted
    
    # These should be deleted on BOTH
    if emptyA or emptyA is None:
        assert not os.path.exists('A/move') # 2
    else:
        assert os.path.exists('A/move')

    if emptyB or emptyB is None:
        assert not os.path.exists('B/del') #1
        assert not os.path.exists('B/deep/deeper/deepest') # 3
    else:
        assert os.path.exists('B/del') #1
        assert os.path.exists('B/deep/deeper/deepest') # 3
    
    os.chdir(PWD0)

@pytest.mark.parametrize("always,compare,renamesA,renamesB,conflict_mode",itertools.product([True,False],
                                                                                            ['mtime','size'],
                                                                                            ['mtime',None],
                                                                                            ['mtime',None],
                                                                                            ['newer','larger']))
def test_no_modtime(always,compare,renamesA,renamesB,conflict_mode):
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('nomodtime',remoteA,remoteB)   
    
    test.config.name = 'mmm' # so that it isn't random
    test.config.always_get_mtime = always
    test.config.compare = compare
    test.config.renamesA = renamesA
    test.config.renamesB = renamesB
    test.config.conflict_mode = conflict_mode
    
    test.write_config()
    
    test.write_pre('A/fileA.txt','A')
    test.write_pre('A/fileB.txt','B')
    test.write_pre('A/fileMod.txt','AB')
    
    
    test.setup()
    
    test.write_post('A/fileMod.txt','AAA',add_dt=50) # newer and larger
    test.write_post('B/fileMod.txt','BB',add_dt=0) #
    
    # We do not actually care if it follows the moves or not. Just whether
    # it gets the mtime to try to do it. Move the file so it has to try
    test.move('A/fileA.txt','A/fileAA.txt')
    test.move('A/fileB.txt','A/fileBB.txt')
    
    test.sync()
    
    # Compare to make sure the sync worked
    assert not test.compare_tree()
    assert exists('A/fileAA.txt')
    assert not exists('A/fileA.txt')
    assert test.read('A/fileMod.txt') == 'AAA'
    
    # Now check the file listings to see if they have mtime stored
    with lzma.open('A/.syncrclone/A-mmm_fl.json.xz') as fA, lzma.open('B/.syncrclone/B-mmm_fl.json.xz') as fB:
        filesA,filesB = json.load(fA),json.load(fB)
    mtimeA = all(f['mtime'] for f in filesA)
    mtimeB = all(f['mtime'] for f in filesB)
    
    assert mtimeA == (always or compare == 'mtime' or renamesA == 'mtime' or conflict_mode == 'newer')
    assert mtimeB == (always or compare == 'mtime' or renamesB == 'mtime' or conflict_mode == 'newer')
        
    os.chdir(PWD0)

if __name__ == '__main__':
    test_main('A','mtime','B','hash','size') # Vanilla test covered below
   
#     test_main('A','inode','cryptB:','mtime','mtime')
#     test_main('cryptA:','size','cryptB:','mtime','mtime')
#     for remoteA,renamesA,remoteB,renamesB,compare in MAIN_TESTS:
#         test_main(remoteA,renamesA,remoteB,renamesB,compare)        
#     for attrib in ('size','mtime','hash','inode',None):
#         test_move_attribs(attrib)
#     test_reuse_hash()    
#     test_no_hashes()
#     for conflict_mode,tag_conflict in itertools.product(('A','B','older','newer','smaller','larger','tag'),(True,False)):
#         test_conflict_resolution(conflict_mode,tag_conflict)
#     for backup,sync in itertools.product((True,False,None),(True,False)):
#         test_backups(backup,sync)
#     test_dry_run()
#     test_logs()
#     test_three_way()
#     test_locks()
#     test_local_mode()
#     test_redacted_PW_and_modules_in_config_file()
#     test_and_demo_exclude_if_present()
#     for version in version_tests:
#         test_version_warning(version)
#     for legA,legB in ((0,1),(1,0),(1,1)):
#         test_legacy_filelist(legA,legB)
#     for emptyA,emptyB in itertools.product([True,False,None],[True,False,None]):    
#         test_emptydir(emptyA,emptyB) 
#     for always,compare,renamesA,renamesB,conflict_mode in itertools.product([True,False],
#                                                                             ['mtime','size'],
#                                                                             ['mtime',None],
#                                                                             ['mtime',None],
#                                                                             ['newer','larger']):
#         
#         test_no_modtime(always,compare,renamesA,renamesB,conflict_mode)
        
        
    # hacked together parser. This is used to manually test whether the interactive
    # mode is working
    if len(sys.argv) > 1 and sys.argv[1] == '-i':
        test_main('A','hash','B','hash','mtime',interactive=True)
# 

    print('*'*80)
    print(' ALL PASSED')


























