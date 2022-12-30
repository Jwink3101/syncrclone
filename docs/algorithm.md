# Bi-Direction Sync Algorithm

This discusses the sync algorithm and some design decisions. Note that all queries use DictTable, an in-memory, O(1) noSQL-like object store. Therefore they can be done efficiently.

Note that `filename` is the path relative to the root.

## Summary:

The algorithm is summarized as follows:

## File Listing

Use rclone to download the older list. This is based on config `name` so that multiple syncs can be set up. 

Use rclone to list files for both remotes for the current list. If config `compare` or `renames{A/B}` has `hash` attribute, need to also get file hashes. Alternatively, if `reuse_-_hashes{A/B}`, use `size,mtime,filename` to get the previous hash value. Then call rclone again with `--files-from` to get the hash of the remaining files.

## Initial Comparison

Generate a list of all filenames in both current lists for A and B. For each file compare (`filename`,`size`,`compare` attribute) between A and B:

* A == B: 
	* Remove from *both* current and previous lists
	* Compare by filename and one of the following:
	    * hash (must have a common hash)
	    * mtime *and* size
	    * size alone

Do all of the above first. Then determine new, modified, and deleted. In practice, new and modified are treated the same but it is nice to have them separate for move tracking

* A is missing:
	* if B is not in the previous list, B is new
	* if B is in the previous list and UNMODIFIED, B has been deleted by A
	* if B is in the previous list and MODIFIED, B has been deleted by A but modified by B
* B is missing:
	* See above
* A != B: Modified file or conflict
    * Look for past files of A or B. 
        * If only one compares true (no prev also means it compares False), the other is modified. Backup and sync. 
        * If both compare False, (didn't exist means both are new. Both exist but don't compare means both are modified)
        * Both compare true -- This is VERY odd and should not happen but allow it anyway.
    * Resolution is based on what you set. `A` or `B` are always those remotes. `tag` is renaming both. Older, newer, newer_tag are based on mtime. However, if compare is hash or size, older means smaller and newer means larger.
    
## Move Tracking

Moves are only tracked if `renames{A/B}` is set. Options are `{size,mtime,hash}` where the following are checked:

| Attribute | Actually compared |
|-----------|-------------------|
| size      | size              |
| mtime     | size,mtime        |
| hash      | size,hash         |

Hash doesn't really need size but it makes the comparison faster because of the loop needed to find common hashes amongst remotes.

The move tracking algorithm *only* tracks if there have been no changes to the file (since unlike and rsync based tool, this one always does a full transfer). 

For example, on side A, a rename is tracked if the following are *all* true:

1. A file is marked as new on side A: `new`
2. The `renamesA` attribute is matched to a `prev` file marked as delete on side A: `old`
    * This is why the old list is pruned of matches to make sure they do not hang around on this one
3. A file named `old` on B marked to be deleted matches the `--compare` attribute

If all three conditions are met, the file `new` is no longer considered for transfer, and the file `old` on side B is marked to be moved.

## Transfer & Update

This is all really an implementation detail but:

* Files marked as deleted are either delete `--no-backup` or moved to `.syncrclone/backups/{date}-{name}/`
* Files that are marked to be overwritten are also backed up to `.syncrclone/backups/{date}-{name}/`

Then the transfers happen

## Relisting

If *anything* was changed or transfered to a side, a list is remade. The same hash process above is performed

* Perform a current listing of each remote
* Download the previous listing of each remote
* Remove (from *both* old and current) any files that have the same `filename` and `--compare` attribute. Removing from the old list is

### Avoiding Relisting

Theatrically, you could avoid re-listing since you can propagate the same changes to the file lists that you do in practice. But this is fragile and introduces many edge cases; especially around hashes and tracking. <del>This may be considered in the future but not at the moment.</del>

## Other Notes

### Backups

Pre 20221230.0 (or thereabouts), backups were done as `copy` before uploading. The problem is, on remotes that do not support server-side copy, this is horribly inefficient as rclone downloads then uploads the file. But if a remote supports, server-side move, this is risky because an interruption could cause problems.

Instead, now, backups are done via `copy --backup-dir` in the transfer. This can still have an interruption problem but is handled within rclone and is less likely since it will move on a file-by-file basis, unlike if syncrclone did it all first.
