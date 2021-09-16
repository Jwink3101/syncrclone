# Miscellaneous Notes

Little bits of information about how syncrclone works.

## Reading (and modifying) file lists

Each remote stores a copy of their respective past file lists in `.syncrclone/{AB}-{name}_fl.json.xz`. This is used to detect new vs deleted, prevent deleting modified files, and is also used to speed up hashing by reusing them when possible.

The `xz` format is read and written with the `lzma` module in python. It can also be read or written outside python using the `xz` tool

To convert *from* `.json.xz` to `.json` use:

    $ xz -d --keep A-name_fl.json.xz

Where `--keep` is optional but keeps the original file around. To convert back to `.json.xz`, it is as simple as:

    $ xz A-name_fl.json

### Legacy

Pre 20210121.0, file lists were stored as a zlib-compressed json string.

The files are UTF8 encoded JSON that is then zlib compressed and given as header `b'zipjson\x00\x00'`. The following python snippet will let you read this into a list and then back out.

Read into a list called `files`

```python
import json,zlib
HEADER = b'zipjson\x00\x00'

with open('A-name_fl.zipjson','rb') as file:
    file.seek(len(HEADER))
    files = json.loads(zlib.decompress(file.read()))
```
 
To write out to the new format, use the following simple snippet

```python
import json,lzma
with lzma.open('A-name_fl.json.xz','wt') as file:
    json.dump(files,file,ensure_ascii=False)
```

## Optimized Actions

There are essentially three (or two or four depending on how you count) actions besides transfers that we have to consider.

1. Move
2. Backup (before getting overwritten)
3. Delete (with or without backup)

Since we wrap rclone and have to make a call for each one, it can get slow. This is as opposed to using the built in methods that know all of the files. So there are some optimizations that can speed it up.

First, all operations always move to a non-existing object. It wouldn't register as a move or it is a backup directory. So always use `--no-check-dest`.

Then, to speed it up, use the following logic **in order**:

- Deletes with backup: This will depend on the remote.
    - Remote supports server-side move:
        - At the first level, combine all of the deletes. They have to be at the first level so that you do not overlap (e.g. you can do `move --files-from <files> remote:subdir/ remote:.syncrclone/backups/<dated>/subdir` but you cannot do `move --files-from <files> remote: remote:.syncrclone/backups/<dated>/` since they overlap)
        - All files at the root get translated into a move to the backup dir
        - Use `move --files-from <files> remote:<subdir> remote:.syncrclone/backups/<dated>/<subdir>`
    - Remote does not support server-side move: Since rclone will do that as a copy+delete, we do the same. Add all files to backup and then delete. Note the order of backup and delete
- Moves: Has to be done one at a time. No getting around it
- Backups: Since rclone *will* allow `copy --files-from` on overlapping remotes, use that for all backups into a single call
- Delete without backup: Use `delete --files-from`

### Overlapping Remotes

Rclone is very conservative about overlaps. See [this forum post](https://forum.rclone.org/t/moving-the-contents-of-a-folder-to-the-root-directory/914/7) and [this tracking issue (1082)](https://github.com/rclone/rclone/issues/1082). For an explanation on why copy works, see [#1319](https://github.com/rclone/rclone/issues/1319):

> For a remote which doesn't [move whole directoreis] it has to move each individual file which might fail and need a retry which is where the trouble starts...

## Locks

syncrclone includes a locking system where a lock file is created and syncrclone won't run unless it has been removed. Note that this isn't a perfect system. Known issues are:

* Non-syncrclone usage will not set nor respect locks
* Race conditition possible if two sync jobs are started while the locks are being set

Locks may be removed in future versions as they are not particularly robust.

## Interruptions
 
syncrclone is **not** atomic which means it can be interrupted and left incomplete. However, it should be safe from interruptions causing real damage.

The following are the major steps of the code and below are the consequences of interruption.

Not incuded in the below list is breaking the system locks. To do that

```bash
$ syncrclone --break-lock both <config_file.py>
```

* File Listing
    * None
* File Comparison and action planning
    * None
* Pre-Sync actions including delete, backup, move
    * If interrupted during delete, you may have an extra backup copy. Or it will look like it was deleted on both sides
    * If interrupted during backups, you may have an extra backup copy
    * If interrupted during moves: A file will be moved on the next run or if already moved, will look like it was moved on both sides
* Transfers:
    * If file has not been transfered, it will be identified for transfer next time.
    * If a file was transferred, it will match on both sides and be fine
* File Listing:
    * If rerun immediately, nothing will happen as everything is in sync
    * If not rerun, files that are later deleted may be be restored upon sync since syncrclone won't know that they previously existed.
* Delete newly empty dirs (optional)
    * If it breaks here some empty directories will remain and never be automatically deleted. No data loss but minor cleanup will be required. (can use `rclone rmdirs`)

While this should be safe from any issues, it is suggested that you keep backups! It's even a good idea to run a backup before and after sync if you're really concerned!


## Multiple Repos

syncrclone does pair-wise sync but it can also do any pair-wise topology. The only important note is that **each pair must have a unique name**.

A star-topology is probably the easiest and most resilient to conflicts but as long at the name is changed, syncrclone can push or pull from any two remotes and keep them in sync.











