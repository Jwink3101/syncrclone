# Changelog

This will likely get wiped when I go out of beta. 

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
