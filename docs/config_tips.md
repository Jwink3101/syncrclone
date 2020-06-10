# Configuration Tips

The use of a Python configuration file makes this very flexible. Some tips are included

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

If the conifg file is in the sync directory (for example `scripts/sync.py`), the following may be helpful. Again, note the name is still set

```python
import os,subprocess
remoteA = os.path.eabspath('../')
remoteB = 'remoteB:path/to/remote'

name = subprocess.check_call(['hostname'])
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


















