# Changelog

This will likely get wiped when I go out of beta. 

## 20200826.0.BETA

* Now allows for time-based conflict resolution even when not comparing by time. Note that this now puts the onus on the *user* to make sure the remote supports ModTime
* Better reporting of edge case errors such as comparing by mtime (which agree) but sizes do not. Final behavior (revert to tag) has not changed but the warning will be more helpful

## 20200825.0.BETA (minor) 

* Fix an O(N) dependency in DictTable. Now will be much faster for larger sync directories

## 20200814.0.BETA (minor)

* Fix buffer warning in python3.8

## 20200622.0.BETA

* No longer emit a warning for missing hashes caused by being in sync
