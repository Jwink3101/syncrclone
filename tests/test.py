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
import re
import zlib,lzma,json,subprocess

import testutils

import pytest

p = os.path.abspath('../')
if p not in sys.path:
    sys.path.insert(0,p)
from syncrclone import set_debug
import syncrclone.cli
import syncrclone.utils
import syncrclone.main
from syncrclone.dicttable import DictTable

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
    # All combinations of compares and renames. All local
    renamesA = renamesB = ('size','mtime','hash') # Do not include None as we want to track them
    compares = ('size','mtime','hash')
    for renameA,renameB,compare in itertools.product(renamesA,renamesB,compares):
        yield ('A',renameA,None,
               'B',renameB,None,
               compare)
    
    # Now test with specified workdirs. Can just use any rename
    yield 'A','size','Awork','B','size','Bwork','size'
    yield 'A','size',None,'B','size','Bwork','size'
    yield 'A','size','Awork','B','size',None,'size'
    
    # Test with some crypts (as a test for non-local). Use mtimes
    yield 'cryptA:','mtime',None,'B','mtime',None,'size'
    yield 'A','mtime',None,'cryptB:','mtime',None,'size'
    yield 'cryptA:','mtime',None,'cryptB:','mtime',None,'size'
    
    # Crypts with specified workdirs
    yield 'cryptA:main','mtime','cryptA:wd','B','mtime',None,'size'
    yield 'A','mtime',None,'cryptB:main','mtime','cryptB:wd','size'
    yield 'cryptA:main','mtime','cryptA:wd','cryptB:main','mtime','cryptB:wd','size'
    yield 'cryptA:main','mtime','cryptB:wdA','cryptB:main','mtime','cryptA:wdB','size' # Mix ?
    
    
    
MAIN_TESTS = list(get_MAIN_TESTS()) 
# MAIN_TESTS = [ ## TODO Update
#     ['A','hash','B','hash','hash'], # Most secure
#     ['A','hash','B','hash','mtime'], # Good compare when no common hash
#     ['A','size','B','size','size'], # Most easily tricked but will still work on this test
# ])
    

@pytest.mark.parametrize(("remoteA,renamesA,workdirA,"
                          "remoteB,renamesB,workdirB,"
                          "compare"),MAIN_TESTS)
def test_main(remoteA,renamesA,workdirA,
              remoteB,renamesB,workdirB,
              compare,
              interactive=False,
              debug=False,
              ):
    """
    Main test with default settings (if the defaults change, this will need to
    be updated. A few minor changes from the defaults are also made
    
    More edge cases and specific settings are played with later
    
    """
    set_debug(debug)
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
    test.config.name='main'
    
    test.config.workdirA = workdirA
    test.config.workdirB = workdirB
    
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
    test.write_pre('A/del in dir1/del on B.txt','will delete on B')
    test.write_pre('A/del in dir2/del on A.txt','will delete on A')
    test.write_pre('A/delA modB.txt','delA but mod on B')
    test.write_pre('A/delB modA.txt','delB but mod on A')
    
    test.write_pre('A/sub d‡r/unic°de and space$.txt','UTF8')

    test.write_pre('A/common_contentAfter0.txt','abc xyz')
    test.write_pre('A/common_contentAfter1.txt','abc xy')

    test.write_pre('A/common_contentBefore0.txt','ABC XYZ')
    test.write_pre('A/common_contentBefore1.txt','ABC XYZ')

    flags = ['--debug'] if debug else []
    ## Run
    test.setup(flags=flags)

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
    
    os.remove('B/del in dir1/del on B.txt')
    os.remove('A/del in dir2/del on A.txt')

    test.write_post('A/newA.txt','New on A')
    test.write_post('B/newB.txt','New on B')
    
    test.write_post('A/newA.no','New on A and no') # use new to test exclusions too
    test.write_post('B/newB.no','New on B and no')
    test.write_post('A/yes/newA.yes.no','New on A and no but yes')
    test.write_post('B/yes/newB.yes.no','New on B and no but yes')
    
    test.write_post('B/sub d‡r/unic°de and space$.txt','works',mode='at')
    
    # These don't need to be tested other than not showing a diff
    test.write_post('A/common_contentAfter1.txt','abc xyz')
    test.write_post('B/common_contentBefore1.txt','ABC XYZW')
    
    print('-='*40)
    print('=-'*40)
    args = ['--interactive'] if interactive else []
    obj = test.sync(flags=args + flags)
    
    ## Confirm!
    print('-'*100)
    diffs = test.compare_tree()
    
    # Exclusions except when filters to allow!
    assert {('missing_inA', 'newB.no'), ('missing_inB', 'newA.no')} == diffs,diffs
    
    stdout = ''.join(test.synclogs[-1])
    # Check on A from now on!

    # Edits -- Should *NOT* tag but *should* backup
    assert test.read('A/EditOnA.txt') == 'Edit on AEdited on A',"mod did not propogate"
    assert test.read('A/EditOnB.txt') == 'Edit on BEdited on B',"mod did not propogate"
    assert not exists('A/EditOnA.txt.*'),'Should NOT have been tagged'
    assert not exists('A/EditOnB.txt.*'),'Should NOT have been tagged'
    assert test.globread(os.path.join(test.wdB,'backups/*_B/EditOnA.txt')) == 'Edit on A','not backed up'
    assert test.globread(os.path.join(test.wdA,'backups/*_A/EditOnB.txt')) == 'Edit on B','not backed up'
        
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
    
    assert exists(os.path.join(test.wdA,'backups/*_A/delB.txt')), "did not backup (delB)"
    assert exists(os.path.join(test.wdB,'backups/*_B/delA.txt')), "did not backup (delA)"

    assert exists('A/delB modA.txt') # Should not have been deleted
    assert "DELETE CONFLICT: File 'delB modA.txt' deleted on B but modified on A. Transfering" in stdout
    assert exists('A/delA modB.txt')
    assert "DELETE CONFLICT: File 'delA modB.txt' deleted on A but modified on B. Transfering" in stdout
    
    assert exists('A/newA.txt')
    assert exists('A/newB.txt')

    assert exists('A/yes/newA.yes.no')
    assert exists('A/yes/newB.yes.no')

    assert test.read('A/sub d‡r/unic°de and space$.txt') == 'UTF8works'
    assert exists(os.path.join(test.wdA,'backups/*_A/sub d‡r/unic°de and space$.txt')),'did not back up unicode'
    
    assert exists(os.path.join(test.wdA,'A-main_fl.json.xz'))
    assert exists(os.path.join(test.wdB,'B-main_fl.json.xz'))
    
    assert exists('A/.syncrclone/') is (False if workdirA else True)
    assert exists('B/.syncrclone/') is (False if workdirB else True)
    
    os.chdir(PWD0)

def test_avoid_relist():
    """
    Test avoiding the relist by calling test_main() with the different options and
    comparing the lists at the end. The mtimes will be off but they should agree otherwise
    """
    try: # use try/finally to ensure it is *always* reset
        syncrclone.main._TEST_AVOID_RELIST = True
        test_main('A','hash',None,'B','hash',None,'hash')
    finally:
        syncrclone.main._TEST_AVOID_RELIST = False
        
    with open('testdirs/main/relists.json') as fin:
        l = json.load(fin)
        A,B,rA,rB = [DictTable(l[k],fixed_attributes=['Path','Size','mtime']) \
                     for k in ['A', 'B', 'rA', 'rB']]
    fA = {( f['Path'],f['Size']) for f in A if not f['Path'].startswith('.syncrclone')}
    fB = {( f['Path'],f['Size']) for f in B if not f['Path'].startswith('.syncrclone')}    
    rfA = {(f['Path'],f['Size']) for f in rA if not f['Path'].startswith('.syncrclone')}    
    rfB = {(f['Path'],f['Size']) for f in rB if not f['Path'].startswith('.syncrclone')}    
    assert fA == rfA
    assert fB == rfB
    
    for Path,Size in fA:
        q = dict(Path=Path,Size=Size)
        assert abs(rA[q]['mtime'] - A[q]['mtime']) < 1
    for Path,Size in fB:
        q = dict(Path=Path,Size=Size)
        assert abs(rB[q]['mtime'] - B[q]['mtime']) < 1
    

@pytest.mark.parametrize("attrib",('size','mtime','hash',None))
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
    
    Only test with local A. B doesn't matter since
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
    remoteA = 'cryptA:Main'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('logs',remoteA,remoteB)   
    test.config.renamesA = 'mtime'
    test.config.save_logs = True
    test.config.workdirA = 'cryptA:Work'
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
    logsA = sorted(glob.glob('wdA/logs/*'))
    assert len(logsA) == 2, "should have two. setup + sync"
    
    logsB = sorted(glob.glob('B/.syncrclone/logs/*'))
    assert {os.path.basename(l) for l in logsA} == {os.path.basename(l) for l in logsB}, 'A and B are not the same'
    
    # We know from all of the other tests that stdout (above) works otherwise
    # they would fail. So just check that it's the same
    with open(logsA[-1]) as f:
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

LOCKTESTS = list(itertools.product(('A','cryptA:main'),(None,'cryptA:wd'),
                                   ('B','cryptB:main'),(None,'cryptB:wd')))

@pytest.mark.parametrize("remoteA,workdirA,remoteB,workdirB",LOCKTESTS)
def test_locks(remoteA,workdirA,remoteB,workdirB):
    """
    Tests locking and breaking the lock
    """
    test = testutils.Tester('locks',remoteA,remoteB)
    test.config.workdirA = workdirA
    test.config.workdirB = workdirB
    
    test.config.set_lock = True
    test.config.name='name'
    test.write_config()

    def set_lock():
        """
        Need to do it semi-manually for non A/ B/ remotes because the
        initial sync of the files will break it. ONLY do this in those cases
        """
        sync.rclone.lock()
    
        # Before testing again make sure it follows workdir settings
        # and/or set lock manually
        if test.config.workdirA: 
            assert not os.path.exists('A/.syncrclone/LOCK/LOCK_name')
        else:
            test.write_post('A/.syncrclone/LOCK/LOCK_name','man')
            
        if test.config.workdirB: 
            assert not os.path.exists('B/.syncrclone/LOCK/LOCK_name')
        else:
            test.write_post('B/.syncrclone/LOCK/LOCK_name','man')
    
    
    # setup
    test.write_pre('A/file1.txt','file1')
    
    sync = test.setup()
    
    test.write_post('B/file1.txt','mod',mode='at')
    
    # Set the lock
    set_lock()
    with pytest.raises(syncrclone.rclone.LockedRemoteError):
        test.sync(['--debug'])
    
    # break the lock on both then sync
    test.sync(['--break-lock','both','--debug'])
    test.sync(['--debug']) # Should work

    # Edit the file then set the lock again. Then test breaking each one
    test.write_post('A/file1.txt','mod again',mode='at')
    
    # Set the lock
    set_lock()    
    
    with pytest.raises(syncrclone.rclone.LockedRemoteError):
        test.sync(['--debug'])
    
    # Break it
    test.sync(['--break-lock','both','--debug'])
    test.sync(['--debug']) # Make sure can sync
    
    # Set the lock manually. Only do this for all locals
    if (remoteA,workdirA,remoteB,workdirB) == ('A', None, 'B', None):
        test.sync(['--break-lock','both','--debug'])
        
        test.write_post('A/.syncrclone/LOCK/LOCK_name','')
        with pytest.raises(syncrclone.rclone.LockedRemoteError):
            test.sync(['--debug']) 
        test.sync(['--break-lock','A','--debug'])
        test.sync(['--debug'])
        
        test.write_post('B/.syncrclone/LOCK/LOCK_name','')
        with pytest.raises(syncrclone.rclone.LockedRemoteError):
            test.sync(['--debug'])
        test.sync(['--break-lock','B','--debug'])
        test.sync(['--debug'])
        
        # Make sure breaking one doesn't break the other
        test.write_post('A/.syncrclone/LOCK/LOCK_name','')
        test.write_post('B/.syncrclone/LOCK/LOCK_name','')
        with pytest.raises(syncrclone.rclone.LockedRemoteError):
            test.sync(['--debug'])
        test.sync(['--break-lock','B','--debug'])
        with pytest.raises(syncrclone.rclone.LockedRemoteError):
            test.sync(['--debug'])
        test.sync(['--break-lock','A','--debug'])
        test.sync(['--debug'])

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

@pytest.mark.parametrize("emptyA,emptyB,avoid_relist",
                         itertools.chain(itertools.product([True,False,None],
                                                           [True,False,None],
                                                           [False]),
                                         [[True,True,True],[False,True,True],[True,False,True]]
                                         ))
def test_emptydir(emptyA,emptyB,avoid_relist):
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
    test.config.avoid_relist = avoid_relist
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

@pytest.mark.parametrize("dry",[True,False])
def test_prepost_script(dry):
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('prepost_script',remoteA,remoteB)   
    test.config.pre_sync_shell  = """\
        myvarPRE=pre-test
        echo pretest $myvarPRE
        echo eee 1>&2
        """ 
    test.config.post_sync_shell  = ['/bin/bash','-c',"""\
        myvarPOST=post-test
        echo posttest $myvarPOST"""]

    test.write_config()
    
    test.write_pre('A/fileA.txt','A')
    if dry:
        test.setup(flags=['--dry-run'])
    else: 
        test.setup()
    
    log = ''.join(test.synclogs[-1]) 

    assert '$         myvarPRE=pre-test' in log
    assert '$         echo pretest $myvarPRE' in log
    assert '$         echo eee 1>&2' in log
    assert "['/bin/bash', '-c'," in log
    
    if dry:
        assert 'STDOUT: pretest pre-test' not in log
        assert 'STDOUT: posttest post-test' not in log
        assert 'STDERR: eee' not in log
    else:
        assert 'STDOUT: pretest pre-test' in log
        assert 'STDOUT: posttest post-test' in log 
        assert 'STDERR: eee' in log    
        
    os.chdir(PWD0)

@pytest.mark.parametrize("stop_on_shell_error",[True,False])
def test_prepost_error(stop_on_shell_error):
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('prepost_error',remoteA,remoteB)   
    test.config.stop_on_shell_error = False
    test.write_config()
    
    test.write_pre('A/fileA.txt','A')
    test.setup()
    test.write_pre('A/new.txt','new')
    
    # We can't use the built in logging since it will break from the system exit
    # so out shells write out. 
    
    test.config.pre_sync_shell  = """\
        echo "test" > tmp.txt
        exit 4
        """ 
    
    test.config.stop_on_shell_error = stop_on_shell_error
    test.write_config()
    try:
        test.sync()
    except SystemExit:
        pass

    assert exists('tmp.txt')
    with open('tmp.txt') as f: 
        assert f.read().strip() == 'test'
    
    diffs = test.compare_tree()
    if stop_on_shell_error:
        assert diffs == {('missing_inB', 'new.txt')}
    else:
        assert diffs == set()
      
    os.chdir(PWD0)

@pytest.mark.parametrize("nomovesA,nomovesB",[(0,0),(1,0),(0,1),(1,1),(None,None)])
def test_disable_moves(nomovesA,nomovesB):
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('test_disabled_moves',remoteA,remoteB)   
    
    if nomovesA is None and nomovesB is None:
        test.config.rclone_flags += ['--disable','move']
        nomovesA = nomovesB = True # since I will test this later
    else:
        if nomovesA:
            test.config.rclone_flagsA += ['--disable','move']
        if nomovesB:
            test.config.rclone_flagsB += ['--disable','move']
    
    test.write_config()
    
    test.write_pre('A/delA.txt','')
    test.write_pre('A/subdirA/delAA.txt','')
    test.write_pre('A/subdirA/del2A.txt','')
    test.write_pre('A/delB.txt','')
    test.write_pre('A/subdirB/delBB.txt','')
    test.write_pre('A/subdirB/del2B.txt','')
    
    test.setup()
    
    os.remove('A/delA.txt')
    os.remove('A/subdirA/delAA.txt')
    os.remove('A/subdirA/del2A.txt')
    os.remove('B/delB.txt')
    os.remove('B/subdirB/delBB.txt')
    os.remove('B/subdirB/del2B.txt')
    
    obj = test.sync(['--debug'])
    
    assert test.compare_tree() == set()
    assert exists('A/.syncrclone/backups/*_A/delB.txt')
    assert exists('A/.syncrclone/backups/*_A/subdirB/delBB.txt')
    assert exists('A/.syncrclone/backups/*_A/subdirB/del2B.txt')
    assert exists('B/.syncrclone/backups/*_B/delA.txt')
    assert exists('B/.syncrclone/backups/*_B/subdirA/delAA.txt')
    assert exists('B/.syncrclone/backups/*_B/subdirA/del2A.txt')
    
    stdout = ''.join(test.synclogs[-1])
    
    linesA = [
        ('DEBUG: Add to backup + delete A [',nomovesA),
        ("rootdirs prior A",not nomovesA),
        ("root-level backup as move ('delB.txt',",not nomovesA),   
        ("rootdirs post A",not nomovesA)]
    for lineA,tt in linesA:
        assert (lineA in stdout) == tt,(lineA,tt)
        
    linesB = [
        ('DEBUG: Add to backup + delete B [',nomovesB),
        ("rootdirs prior B",not nomovesB),
        ("root-level backup as move ('delA.txt',",not nomovesB),   
        ("rootdirs post B",not nomovesB)]
    for lineB,tt in linesB:
        assert (lineB in stdout) == tt,(lineB,tt)
        
    os.chdir(PWD0)

def test_cli_override():
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('cli_override',remoteA,remoteB)   
    
    # Use pre_sync_shell as an easy tester
    test.config.pre_sync_shell  = """\
        echo aaa > tmp""" 

    test.write_config()
    
    test.write_pre('A/fileA.txt','A')
    test.setup()
    
    with open('tmp') as f:
        assert f.read().strip() == 'aaa'
    
    test.sync(flags=['--override','pre_sync_shell = "echo bbb > tmp"'])
    with open('tmp') as f:
        assert f.read().strip() == 'bbb'
#     
    os.chdir(PWD0)

def test_reset_state():
    """
    If the prior state was held, this would not be a conflict. But because it is
    (on the second sync), we see a tag
    """
    remoteA = 'A'
    remoteB = 'B'
    set_debug(False)   
    
    test = testutils.Tester('reset_state',remoteA,remoteB)  
    test.config.conflict_mode = 'tag' 
    test.write_config()
    
    test.write_pre('A/fileA.txt','A')
    test.write_pre('A/fileB.txt','B')
    
    test.setup()
    
    test.write_post('A/newA.txt','newA')
    test.write_post('B/fileB.txt','modB',mode='at')
    
    test.sync()
    assert test.compare_tree() == set() # Agree
    assert not exists('A/fileB.*.B.txt') # Not tagged
    assert not exists('A/fileB.*.A.txt')
    assert exists('A/fileB.txt')
    
    # Same changes again but this time reset the state
    test.write_post('A/newerA.txt','newA')
    test.write_post('B/fileB.txt','modB again',mode='at')
    
    test.sync(['--reset-state'])
    
    assert test.compare_tree() == set() # Agree    
    assert exists('A/fileB.*.B.txt')
    assert exists('A/fileB.*.A.txt')
    assert not exists('A/fileB.txt')
    assert test.globread('A/fileB.*.A.txt') == 'BmodB'
    assert test.globread('A/fileB.*.B.txt') == 'BmodBmodB again'
          
    os.chdir(PWD0)

def test_workdir_overlap():
    # Just call main on some test cases
    
    # This should be caught internally and raise ConfigError.
    with pytest.raises(syncrclone.cli.ConfigError):
        test_main('aliasA1:','mtime','aliasA1:aa',
                  'B','size',None,
                  'size',debug=True) 
                  
    # This will NOT be caught as the aliases hide the true remotes from syncrclone
    with pytest.raises(subprocess.CalledProcessError) as cc:    
        test_main('aliasA1:','mtime','aliasA2:',
                  'B','size',None,
                  'size',debug=True) 
    assert cc.value.returncode == 7,"wrong err type" # https://rclone.org/docs/#exit-code



if __name__ == '__main__':
#     test_main('A','mtime',None,
#           'B','hash',None,
#           'size') # Vanilla test covered below


#     test_main('cryptA:AA','mtime','cryptA:A',
#               'B','hash',None,
#               'size') # Vanilla test covered below
#     test_main('cryptA:AA','mtime','cryptB:Aw',
#               'cryptB:BB','size','cryptA:Bw',
#               'size') # Vanilla test covered below
# 
#     for (remoteA,renamesA,workdirA,
#          remoteB,renamesB,workdirB,
#          compare) in MAIN_TESTS:
#         test_main(remoteA,renamesA,workdirA,remoteB,renamesB,workdirB,compare)        
#     test_avoid_relist()
#     for attrib in ('size','mtime','hash',None):
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
#     for remoteA,workdirA,remoteB,workdirB in LOCKTESTS:
#         test_locks(remoteA,workdirA,remoteB,workdirB)
#     test_local_mode()
#     test_redacted_PW_and_modules_in_config_file()
#     test_and_demo_exclude_if_present()
#     for version in version_tests:
#         test_version_warning(version)
#     for emptyA,emptyB,avoid_relist in itertools.chain(itertools.product([True,False,None],
#                                                                         [True,False,None],
#                                                                         [False]),
#                                                       [[True,True,True],[False,True,True],[True,False,True]]
#                                                       ):    
#         test_emptydir(emptyA,emptyB,avoid_relist) 
#     for always,compare,renamesA,renamesB,conflict_mode in itertools.product([True,False],
#                                                                             ['mtime','size'],
#                                                                             ['mtime',None],
#                                                                             ['mtime',None],
#                                                                             ['newer','larger']):
#         
#         test_no_modtime(always,compare,renamesA,renamesB,conflict_mode)
#     test_prepost_script(False)
#     test_prepost_script(True)
#     test_prepost_error(True)
#     test_prepost_error(False)
#     for nomovesA,nomovesB in [(0,0),(1,0),(0,1),(1,1),(None,None)]:
#         test_disable_moves(nomovesA,nomovesB)
#     test_cli_override()
#     test_reset_state()
#     test_workdir_overlap()
    
    # hacked together parser. This is used to manually test whether the interactive
    # mode is working
    if len(sys.argv) > 1 and sys.argv[1] == '-i':
        test_main('A','hash','B','hash','mtime',interactive=True)


    print('*'*80)
    print(' ALL PASSED')


























