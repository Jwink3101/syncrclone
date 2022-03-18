# syncrclone vs bisync (and rclonesync-v2)

## Preface

Let's be 100% clear and upfront. **I AM BIASED**. I wrote [syncrclone](https://github.com/Jwink3101/syncrclone) to fill a need not met by [bisync](https://rclone.org/bisync/) / [rclonesync-v2](https://github.com/cjnaz/rclonesync-V2). 

Additionally, both are great tools and I am not disparaching  the hard work of the various developers! The thing to remember is that bi-directional syncronization is *fundamentally* harder than mirroring because you *need* to keep the state. And therefore, it is also more opinionated.

rclone bisync is based on rclonesync-v2. So I will just say bisync even though some of this is experiance from the other

One final note: **These may be wrong**. I based it on experiance, reading, discussions, and inference from said activities. I do this in good faith but may be wrong. Please correct me!

## Algorithm Differences

Before I go into details on the differences in features, there is a fundamental difference in algorithms. It is best described as follows.

* **bisync** separately compares the current state to the past state to generate changes. It then propagates those changes and resolves conflicts.
* **syncrclone** *first* compares the current state of each machine and then uses past state to resolve conflicts and deduce needed changes.

Both theoretically result in the same final process. But the latter only implicitly needs the prior state while the former requires it to work. As such, syncrclone does not have any need to notify it that this is the first sync and only has a singular code path. 

It also explains some (but not all) of the feature differences below


## Comparisons

Again, these are in good-faith but may be wrong. Please correct them as needed

<table>
<tr>
    <th>Feature</th>
    <th>syncrclone</th>
    <th>bisync</th>
    <th>Comments</th>
</tr>
<tr>
    <th>Mode of configuration</th>
    <td>Config file (path specified implicitly or explicitly)</td>
    <td>Command line flags</td>
    <td>
    Command line is cleaner and more consistent with rclone but there is a lot of configuration that needs to be kept (e.g. filters, etc) which makes the config file really useful. Makes the sync directories more like a repo (a la git)
    </td>
</tr>
<tr>
    <th>Change Propagation</th>
    <td>Compare *current* state and use previous to resolve conflicts</td>
    <td>
    Propagate differences between current and previous to both sides, then compare
    </td>
    <td>
    *Theoretically* both should be identical but syncrclone is more robust to issues with knowing the previous state. It also removed the need for `--first-sync` type flags and other safety mechanisms. If they have never been synced before, you get the union of the two sides which is safer. No deletes. It also better matches how rclone currently does the comparison
    </td>
</tr>
<tr>
    <th>First sync mode</th>
    <td>Implicit. Same code path</td>
    <td>Explicit. Must handle differently</td>
    <td></td>
</tr>
<tr>
    <th>Filters and affects</th>
    <td>Can *safely* change filters except for `--include-if-present`</td>
    <td>Must rerun with first-sync mode. Loses some conflict detection</td>
    <td>This difference is due to the algorithm and when filters get applied</td>
</tr>
<tr>
    <th>Comparisons</th>
    <td>ModTime, size, and/or hash</td>
    <td>ModTime</td>
    <td>
    Reliance on ModTime *severely* limits which remotes can be used bisync. ModTimes can also be fragile when restoring from backups. 
    </td>
</tr>
<tr>
    <th>Previous state data</th>
    <td>
    Default: Stored inside each remote and named based on a unique name for the pair. Alternative: Can be stored on any *other* rclone remote
    <td>Global storage on the machine itself in a cache-like dir </td>
    <td>
    Saved state on the machine means that if you sync two remotes (e.g. OneDrive to Google Drive), you *need* to use the same machine. Also can lead to issues with paths and duplicates. However, saved state on the remotes leaves artifacts. Syncrclone can be configured to use a different remote but it is more complex and not default
    </td>
</tr>
<tr>
    <th>Rename/Move Tracking</th>
    <td>Optional. Settable with ModTime + size, hash, or size alone (though latter not advisable)
    </td>
    <td>None that I am aware of</td>
    <td></td>
</tr>
<tr>
    <th>Reduce re-hashing of files </th>
    <td> Optional. Can keep previous hashes. Or with new hasher remote.</td>
    <td> Hasher remote</td>
    <td> Hasher remote didn't exist when syncrclone was first made. Both should work fine, like saving the previous state, the hasher is in a cache-like dir
    </td>
</tr>
<tr>
    <th>File backups</th>
    <td>Optional. Either in the remote or a different one</td>
    <td>None</td>
    <td></td>
</tr>
<tr>
    <th>Conflict tagging</th>
    <td>Yes. Optional</td>
    <td>???</td>
    <td>i.e. keep both but rename one with a suffix</td>
</tr>
<tr>
    <th>Delete Fail Safe</th>
    <td>None (except backups)</td>
    <td> Yes. Can set a max-deletes</td>
    <td>has other protections including the default design which will not delete from mis-specified remotes</td>
</tr>
<tr>
    <th>Second file listing</th>
    <td>Yes but experimental feature to not-need</td>
    <td>Yes</td>
    <td>Syncrclone's experimental feature may soon be default. Saves a lot of time on slow-to-list remotes</td>
</tr>
<tr>
    <th>User Support</th>
    <td>Minimal</td>
    <td>Forums, Professional developers. Larger community</td>
    <td>I am a hobby developer and syncrclone is a side hobby project</td>
</tr>
<tr>
    <th>Platforms</th>
    <td>Tested on macOS and Linux. <strong>No idea if this works on windows</strong></td>
    <td>Presumably all platforms</td>
    <td>I never tested syncrclone on Windows. If it doesn't work, it very likely can be fixed to work.</td>
</tr>
<tr>
    <th>Install</th>
    <td>Must install python3. More complex</td>
    <td>None. Built in</td>
    <td></td>
</tr>

</table>












       