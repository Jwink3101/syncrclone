# Changelog

This will likely get wiped when I go out of beta. 

## 20210818.0.BETA

- Adds `always_get_mtime` (default `True`) option so that for remotes such as S3 that require extra API calls for ModTime, can skip it if not needed (i.e. not used for comparison, tracking, or conflict resolution)

## 20210723.0.BETA

- Fixes hash-based move tracking for rclone 1.56 which changed the hash names. Not only is it fixed but it is now more robust to this happening again. Will also map old names to new ones


## 20210720.0.BETA

- Bug Fix related to reusing hashes but not needing more. Missed a return block. Tests updated to catch this


## 20210719.0.BETA

- Adds support for removing empty directories that were not empty before sync. This way if a directory is moved, the old directory name will not stick around. Note that it does *not* include optimizations for moving whole directories; just files. But makes the end result cleaner.
    - Default is based on whether the remote even supports empty directories. Also settable.

## 20210718.0.BETA

- Performs move, deletes, and backups with multiple threads. This setting is *independant* of `--transfers` or `--checkers` in rclone config settings. It is controlled by the new `action_threads` option 
    - defaults to `__CPU_COUNT__ // 1.5`

## 20210716.0.BETA

- Adds the `sync_backups` option where backups on each side are also kept in sync. Defaults to False
- Backups are now stored in `{date}_{name}_{AorB}` rather than the old system
- Changes default config to not set a lock and to always save the logs
- Fix for erroneously *reporting* backup even when turned off (even though they correctly were not done)

## 20210626.0.BETA

- Changes the conflict resolution naming to keep the extension the same for easier inspection. 
    - Example: It used to be `MovedEditedOnBoth_Bnewer.txt.20210626T155458.A` and is now `MovedEditedOnBoth_Bnewer.20210626T155458.A.txt`
    - Updated tests for new name

## 20210419.0.BETA

* Adds `tag_conflict` option and allows it with any other conflict mode. The use of modes likes `newer_tag` are deprecated but will continue to work...for now.

## 20210222.0.BETA

* Fixed a bug where the `stderr` buffer could cause a deadlock on file listing (such as if there are a lot of errors)

## 20210121.0.BETA

* Changed the format for storing the previous lists from using `lzma` so that they can be read and extracted with `xz`. This will support (and test) reading the prior format so that it can pull either but only create the new xz format. That support may *eventually* be removed but there is no clear timeline. Note that the `zipjson` list will stick around but won't be used anymore

## 20201215.0.BETA

* Fixes and closes #2 where using `backup=False` in the config will not be respected. Adds to the backup tests to ensure this is the case
* (minor) Do not log backups if there weren't any

## 20201125.0.BETA

(minor)

* Adds `--interactive` mode which prompts you if you want to continue. Saves having to first call `--dry-run` and then call again
* Fixes some of the logging updates in the last version. Very minor

## 20201107.0.BETA

* Adds documentation about additional flags and how they can break syncrclone
    * References and closes #1 which also has more info on some grive flags
* Updates logging to (a) put identified actions in one place and (b) add spacing to make parsing easier

## 20200826.0.BETA

* Now allows for time-based conflict resolution even when not comparing by time. Note that this now puts the onus on the *user* to make sure the remote supports ModTime
* Better reporting of edge case errors such as comparing by mtime (which agree) but sizes do not. Final behavior (revert to tag) has not changed but the warning will be more helpful

## 20200825.0.BETA (minor) 

* Fix an O(N) dependency in DictTable. Now will be much faster for larger sync directories

## 20200814.0.BETA (minor)

* Fix buffer warning in python3.8

## 20200622.0.BETA

* No longer emit a warning for missing hashes caused by being in sync
