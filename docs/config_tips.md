# Configuration Tips

The use of a Python configuration file makes this very flexible.

Most of the tips are **in the config file** but some are also addressed here.

## Paths

This will be noted elsewhere too but the sync opperation, including executing the config code, is done *in* the directory of the config.

For example, if you call

    $ syncrclone /full/path/to/sync/config.py

It is *always* executed the same as if you did

    $ cd /full/path/to/sync/
    $ syncrclone config.py
    
This is important to note when using local mode as rclone will be evaluated in the `.syncrclone` directory.


## Attribute Settings

Setting the different attributes depend largely on the remotes. These are some tips but it will likely require playing around a little bit.

For the most robust sync and clear conflicts, use hashes for everything and tag all conflicts.

    compare = 'hash'
    conflict_mode = 'tag'
    renamesA = 'hash'
    renamesB = 'hash'
    
If one or both sides are local or do not *natively* provide hashes (e.g. sftp), you can save resources by using `reuse_hashes(AB)`

In general though, I suggest using 

    compare = 'mtime'
    conflict_mode = 'newer_tag'
    
But if hashes are *easily* available
    
    renames(AB) = 'hash'

otherwise

    renames(AB) = 'mtime'

Note that renames with `mtime` also include size. And they will not work if there is more than one candidate.

If a remote does not support hashes (e.g. crypt), then (asume B is crypt)

    compare = 'mtime'
    conflict_mode = 'newer_tag'
    renamesA = 'hash'
    renamesB = 'mtime'

(assuming the underlying remote supports ModTime).

The "worst-case scenario" would be two remotes that do not support ModTime or hash. In this case, I suggest

    compare = 'size'
    conflict_mode = 'tag'
    renamesA = None
    renamesB = None

That is, *no rename tracking!*. If you *really* want to risk it, you can do

    renamesA = 'size'
    renamesB = 'size'

but be aware that a deleted file may look like a rename. This is especially true for smaller files where they are less likely to have unique sizes. It is still safe to use `size` for `compare` since it checks filename and size (though can still have a false-negative if a change doesn't alter the size)

## Dynamic remote directories

If for example, the same sync config is used on more than one machine, you can set dynamic directories. 

**NOTE**: you *must* also specify a unique name. In all examples, that is set dynamically

```python
import os,subprocess
remoteA = os.path.expanduser('~/syndirs/documents')
remoteB = 'remoteB:path/to/remote'

# use hostname for a unique name
name = subprocess.check_output(['hostname']).decode().strip()
```

Or specific for each one

```python
import subprocess
hostname = subprocess.check_output(['hostname']).decode().strip()
if hostname == 'machine1':
    remoteA = '/path/to/machine1/documents'
elif hostname == 'machine2':
    remoteA = '/different/path/to/documents'
else:
    raise ValueError(f"Unrecognized host {hostname}")
    
remoteB = 'remoteB:path/to/remote'

name = hostname
```

Or when in local mode (i.e. the config is in `.syncrclone/config.py` and you don't specify its path), you may just want to change the name.

```python
import os,subprocess
name = subprocess.check_output(['hostname']).decode().strip()
```

Or you can use `socket` for a (potentially) slightly different answer (depending on setup)

```python
import socket
name = socket.getfqdn()
```

You can also do something like specify the name in your `.bashrc`:

    export SYNCRCLONE_NAME="my_computer_name"

then in your config

```python
import os
name = os.environ['SYNCRCLONE_NAME']
```

## Rclone config passwords

rclone can be passed the config password as an environment variable. The following is an example of asking it just once from the user

```python
from getpass import getpass
rclone_env = {'RCLONE_CONFIG_PASS':getpass('Password: ')}
```

Note that if used with `--debug`, the password is redacted from the debug listing.

## Filters

Recall syncrclone *directly* applies rclone's filtering and is set via `filter_flags`. There is a lot more detail on [rclone's site](https://rclone.org/filtering/) but in general, the most robust way to set filters is with `--filter` and *not* `--include` or `--exclude`. The way that filters work is they are all tested against the file name until one meets an include or exclude filter. If a file doesn't match a filter, it is included. So, for example, to exclude all files ending in `.exc` except a few, you would do

```python
filter_flags = ['--filter','+ *.keep.exc',
                '--filter','- *.exc']
```
The first filter will keep anything ending in `*.keep.exc` and be matched before the second filter. The second filter will exclude everything else with `*.exc`.

### Suggested Filters

These are some suggestions of things to exclude.     

    .DocumentRevisions-V100/**
    .DS_Store
    .fseventsd/**
    .Spotlight-V100/**
    .TemporaryItems/**
    .Trashes/**


### Git Filters

There are much better solutions for syncing files along with git repos such as git-annex or git-lfs. However, syncrclone can be used to sync anything *not* tracked in git. This assumes that the "A" remote is local and it is set up in local-mode (though it can be modified otherwise).

```python
remoteA = "../" # set automatically

# ...
# Set up all of your main filters FIRST!
filter_flags = [] #

import subprocess
topdir = subprocess.check_output(['git','rev-parse','--show-toplevel'])
topdir = topdir.decode().strip()

with open('git-files.txt','wt') as file:
    subprocess.call(['git','ls-files'],cwd=topdir,stdout=file)

filter_flags.extend(['--exclue-from','.syncrclone/git-files.txt'])
```

Now, all files that are tracked in git will *not* be synced but all others will be. 

**NOTE**: This method has some very real issues and should be used carefully. For example, it is best if the git repos are up to date with each other before calling syncrclone on any of them! And be careful about un-tracking a file as syncrclone could think it is a deletion.

## rclone flags

You can set flags for rclone to use in all functions calls. Examples that may be useful are flags such as `--transfers` to control the number of files transfered at a time. Or `--config` to set a config path, etc.

However, some flags may break syncrclone, especially ones that modify the output behavior. See [Issue #1][1] for an example of how `--progress` may break syncrclone.

Also, some flags may be needed if the two remotes "see" different files. For example, as also noted in [#1][1], `--drive-skip-gdocs` may be needed on Google Drive since Google Drive can translate to and from docx and Google Docs.

Using `--dry-run` should illuminate any issues but if you're uncertain, make a backup before messing with flags.

[1]:https://github.com/Jwink3101/syncrclone/issues/1


## Removing empty dirs

As noted in the config, syncrclone can remove directories that are *made empty* by syncrclone (e.g. deleted or moved entire directory). It will not try to delete other empty directories.

This is only useful if the remote even supports empty directories. If it does not (e.g. B2, S3, other object stores), then there is no reason to have this on.

Leave on `None` to let syncrclone decide based on whether or not the remote supports them.

This may not work if there are filtered files in the directory. It will keep working and raise a warning.

## Reducing Relisting (EXPERIMENTAL)

As noted in the config file, syncrclone can avoid re-listing the remotes at the end by apply the actions to the file lists. This feature *should* work but it is experimental and likely has some untested edge cases. One know issue is that if using remotes with incompatible hashes and reusing hashing and tracking moves via hash, the move will not be able to be tracked on that remote. The end result is still a proper sync; just without move tracking.

I do think this is the way to go in the future as it really is more efficient (even though there are some edge cases with file hashes). This is currently *not* the default but will be eventually barring some major revelation of a problem.

## Overriding Configs

Settings can also be overwritten for a given call with the `--override` flag. This is useful in cases where you may want to change a setting for this run *only*. For example,
if you usually have `reuse_hashesB = True` but you want to refresh them all, you can do:

    $ syncrclone --override "reuse_hashesB = False" 

and it will change the setting for this run only

## Updating configs

New versions may introduce new configuration options. They always have a sensible default but you may want to take advantage of them. The following is the process I follow to updat the configs. It is certainly not the *only* process.

Let your config be at `/path/to/config/config.py`

    $ cd /path/to/config/ 
    $ syncrclone --new tmpnew.py
    
Then I open `config.py` and `tmpnew.py` side by side. I copy relevant sections *from* `config.py` to `tmpnew.py` and update the new config as needed. Then:

    $ mv config.py config.py.BAK
    $ mv tmpnew.py config.py
    

