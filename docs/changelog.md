# Changelog

This will likely get wiped when I go out of beta. 

## 20220228.0.BETA

- Adds the optional `tempdir` config option to specify where temp files should go. Most users will not need this but may be useful to try to avoid writes on some drives. Note, this is **independent** of rclone's temp directoru settings (see `--temp-dir` in [the docs]) *and* there is very little that needs to be written! Closes #18 and closes #20

## 20220204.0.BETA

Minor fixes and improvements.

- Changes handling of rclone response during transfer in case of errant bytes. See #16
- Adds `log()` (and makes `print() = log()`) and `debug()` to the config environment

## 20220103.1.BETA

- Add `$LOGNAME` to the shell variables and an example of using a notification

## 20220103.0.BETA

Minor 

- Fixed stats reporting that was off from changing internal lists.
- Corrected date for version (it's January, not February).

## 20220202.0.BETA

- Adds stats to the final log and populates the `$STATS` environment variable in the post shell. Useful for setting up notifications or the like.

## 20211229.0.BETA

* Adds the (experimental) option to specify different (non-overlapping) locations to store backups, logs, and previous state (`workdir`). This allows for remotes to not show `.syncrclone` if desired and to store filelists locally or on a different cloud remote.
    * See [config tips](config_tips.md) for caveats and where it doesn't work.
    * See #6 for other ideas
* Changed `log_dest` to `save_logs` and will put them in the respective workdir
* Locks are still around but are *only* checked with also being set.
* Change to file-transfer flags to minimize transferring everything again on any single failure. This *shouldn't* change anything (and all tests still pass) but please let me know of any cases where that doesn't work.
* Allow the specification of a list for pre/post shell. This gives more control to specify commands without escaping, etc.

## 20211014.0.BETA

This includes a lot including some breaking changes. Starting to feel like this may not be "beta" much longer. See the new section in [config tips](config_tips.md) for how to update.

- Option to avoid re-listing a remote at the end of a sync. Since listing the remote can be a bottleneck, this is a big improvement. It is tested in some case but should be considered **experimental**. There are some untested edge cases and can break move tracking with `reuse_hashes`. Default is off! 
    - May become default in the future.
- Introduce a `--reset-state` flag to reset all file lists. This makes the sync look like a new one so it is better to run after a regular sync.
- Empty directory cleanup added in `20210719.0.BETA` is reimplemented with a different algorithm that supports relisting. Still works but may have more cases where it *thinks* the directory is empty but it isn't. That will just not delete.
- **Breaking Changes**:
    - Removed inode support. It was a blocker to avoiding relisting and I think it isn't worth having since it is so outside of rclone.
    - Removed legacy file list support. If you haven't run it in this long, it is worth using the new `--reset-state` anyway.

## 20210930.0.BETA

- Adds the option to stop if there is an error in the pre/post shell script calls. 
- Fixes a bug where rclone flags are not using in rmdirs

## 20210928.0.BETA

- Fixes joining paths with `//`. Hopefully fixes #11

## 20210924.0.BETA

- Adds `--override` CLI flag. Includes updated tests

## 20210916.0.BETA

- Mostly documentation fixes. Closes #8

## 20210830.0.BETA

- Major optimization for actions to minimize rclone calls. Especially useful with lots of files to backup. See [misc](misc.md) for discussion
- When there is an error, the full debug log is dumped to a temp location. 

## 20210819.0.BETA

- Adds `pre_sync_shell` and `post_sync_shell` options. Tests.

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
