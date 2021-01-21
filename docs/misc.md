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

## Locks

syncrclone includes a locking system where a lock file is created and syncrclone won't run unless it has been removed. Note that this isn't a perfect system. Known issues are:

* Non-syncrclone usage will not set nor respect locks
* Race conditition possible if two sync jobs are started while the locks are being set

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

While this should be safe from any issues, it is suggested that you keep backups! It's even a good idea to run a backup before and after sync if you're really concerned!


## Multiple Repos

syncrclone does pair-wise sync but it can also do any pair-wise topology. The only important note is that **each pair must have a unique name**.

A star-topology is probably the easiest and most resilient to conflicts but as long at the name is changed, syncrclone can push or pull from any two remotes and keep them in sync.











