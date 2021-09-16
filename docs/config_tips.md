# Configuration Tips

The use of a Python configuration file makes this very flexible.

Most of the tips are **in the config file** but some are also addressed here.

## Paths

This will be noted elsewhere too but the sync opperation, including executing the config code, is done *in* the directory of the config.

For example, if you call

    $ syncrclone /full/path/to/sync/config.py

It is *alwasy* executed the same as if you did

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
    
then if hashes are easily available
    
    renames(AB) = 'hash'

otherwise if a remote is local and support inodes:

    renames(AB) = 'inode'

otherwise

    renames(AB) = 'mtime'

If a remote does not support hashes (e.g. crypt), then (asume B is crypt

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

but be aware that a deleted file may look like a rename. This is especially true for smaller files where they are less likely to have unique sizes.

## Dynamic remote directories

If for example, the same sync config is used on more than one machine, you can set dynamic directories. 

**NOTE**: you *must* also specify a unique name. In all examples, that is set dynamically

```python
import os,subprocess
remoteA = os.path.expanduser('~/syndirs/documents')
remoteB = 'remoteB:path/to/remote'

name = subprocess.check_call(['hostname'])
```

Or specific for each one

```python
import subprocess
hostname = subprocess.check_call(['hostname'])
if hostname == 'machine1':
    remoteA = '/path/to/machine1/documents'
elif hostname = 'machine2':
    remoteA = '/different/path/to/documents'
else:
    raise ValueError(f"Unrecognized host {hostname}")
    
remoteB = 'remoteB:path/to/remote'

name = hostname
```

If the config file is in the sync directory (for example `scripts/sync.py`), the following may be helpful. Again, note the name is still set

```python
import os,subprocess
remoteA = os.path.eabspath('../')
remoteB = 'remoteB:path/to/remote'

name = subprocess.check_output(['hostname']).decode().strip()
```

Or you can use `socket` for a slightly different answer (depending on setup)

```python
import socket
hostname = socket.getfqdn()
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
The firt filter will keep anything ending in `*.keep.exc` and be matched before the second filter. The second filter will exclude everything else with `*.exc`.

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






