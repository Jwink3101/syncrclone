"""
syncrclone

Config File

This configuration file is read as Python so things can be customized as
desired. With few exception, any missing items will go to the defaults
already specified.

Flags should always be a list. 
Example: `--exclude myfile` will be ['--exclude','myfile']

This is *ALWAYS* evaluated from the parent of this file.

"""
## Remotes:

# Specify the remotes to be used in the rclone config. This should be the 
# root to be synchronized. If local, no need to specify a remote.
# For example:
#
#    remoteA = "/full/path/to/local"
#    remoteB = "b2:bucket/"
#
#  See docs/config_tips.md for some helpful tips and tricks
remoteA = "<<MUST SPECIFY>>"
remoteB = "<<MUST SPECIFY>>"

# (ADVANCED USAGE) Specify where to store past file lists, backups, logs, locks, etc.
# This value must be either:
#   None   : (Default) Stored internal to the remote at remote{A/B}:.syncrclone
#   string : Specify an alternative location (either same remote or not) which
#            DOES NOT OVERLAP with the remote. The only acceptable overlap is when
#            set to None.
#
# Note that overlap is tested but isn't perfect in the case of alias remotes. May cause
# issues later in the sync!  Not compatible with sync_backups
workdirA = None # <remoteA>/.syncrclone
workdirB = None # <remoteB>/.syncrclone

# Names are needed so that one directory can sync to OR from multiple
# locations. Names should be unique. The default below is randomly
# set.
name = '__RANDOM__'

## rclone flags

# Specify the path to the rclone executable.
rclone_exe = 'rclone'

# Specify FILTERING flags only. Note that if filtering flags are used later,
# it *will* cause issues. Examples of rclone filters:
#     --include --exclude 
#     --include-from --exclude-from 
#     --filter --filter-from
#
# note that ['--filter','- .syncrclone/**'] is automatically prepended.
#
# These should be specified as a list. For example, to exclude *.exc, do
# ['--exclude','*.exc']
#
# See warnings in the readme about --exclude-if-present
filter_flags = []

# General rclone flags are called every time rclone is called. This is how
# you can specify things like the conifg file.
# Remember that this config is evaluated from its parent directory.
#
# Example: ['--config','path/to/config']
#
# Note: Not all flags are compatible and may break the behavior of syncrclone
#       such as ones changing the display (`--progress`, `--log-level`)
#
#       Also, some flags may be needed for certain remotes. See
#           https://github.com/Jwink3101/syncrclone/issues/1
#       for a discussion of needing `--drive-skip-gdocs` for gdrive
#
# There is extemely minimal validation of flags. If you're uncertain, have
# a backup and test with `--dry-run`
rclone_flags = []

# The following are added to the existing environment. 
# These should NOT include any filtering!
rclone_env = {}

# Additionally, specify flags for only one side or the other.
# Examples would be things like `--fast-list`
rclone_flagsA = []
rclone_flagsB = []

## Sync Options

# How to compare files on A and B. Note that mtime also includes size.
# Hashes will be automatic based on common hashes. Will raise an error if 
# there are no common hashes. 
# Options: {'size','mtime','hash'}
#
# Notes: 
#   * if using size, can have false negatives. 
compare = 'mtime'

# When doing mtime comparisons, what is the error to allow
dt = 1.1 # seconds

# How to handle conflicts.
# Note that even if comparison is done via hash, you can still resolve via
# mod time. Be aware that not all remotes return reliable mod times and adjust
# accordingly. See https://rclone.org/overview/
#
#   'A','B'             : Always select A or B
#   'tag'               : Tag both. Makes tag_conflict irrelevant 
#
#   'older','newer'     : Select the respective file. See note below.
#   'smaller','larger'  : Select the smaller or larger file
#
# If a conflict cannot be resolved it will default to 'tag' and print a warning.
conflict_mode = 'newer'

# You can choose to tag the other file rather than overwrite it. If tagged,
# it will get renamed to have appended `.{time}.{A or B}` to the file
tag_conflict = False

# Hashes can be expensive to compute on some remotes such as local or sftp.
# As such, rather than recompute them all, the hashes of the previous state
# can be used if the filename,size,mtime all match. Then the hashes of the 
# remaining files will be computed in a second rclone call.
#
# For most other remotes (e.g. S3, B2), hashes are stored by the remote
# so there is no need to reuse them
reuse_hashesA = False
reuse_hashesB = False

# Some remotes (e.g. S3) require an additional API call to get modtimes. If you
# are comparing with 'size' of 'hash', you can forgo this API call by setting
# this to False. Future versions may be smart about this and allow for 
# server-side modtime with a cache but that is not yet possible.
always_get_mtime = True 

# When backups are set, all overwrites or deletes will instead be backed up (moved into
# the workdir folder)
backup = True

# Specify whether to also sync the backed up files between A and B. If True,
# both remotes will have all of the backups. If False, each remote will only
# have what it backed up on the respective side.
#
# Not compatible with specified workdirs
sync_backups = False

# Some remotes do not support hashes at all (e.g crypt) while others do not 
# always return a hash for all files (e.g. S3). When this is encountered,
# syncrclone can fall back to another `compare` or `renames{AB}` attribute.
# Specify as None (default) to instead throw an error.
hash_fail_fallback = None # {'size','mtime',None}

# By default, syncrclone will set a lock to prevent other sync jobs from 
# working at the same time. Note that other tools will not respect these
# locks. They are only for syncrclone.
#
# They are not strictly needed and require extra rclone calls. As such, they 
# can be disabled. If disabled, will also NOT respect them from other calls
set_lock = False

# While transfers will follow the respective rclone flags  (e.g. ['--transfers','10'], 
# delete, backup, and move actions need more calls. There is some optimization but it
# still may need more than one call. This allows it to happen in separate rclone calls. 
action_threads = 1 # Some remotes do not like concurrent rclone calls so this is the default
# action_threads = __CPU_COUNT__ // 1.5
# action_threads = 4

# syncrclone does not transfer empty directories however if a directory is
# empty after a sync and it was NOT empty before (e.g. the directory was moved 
# or deleted), then it can remove them. Note that (a) this only removes 
# directories that were *made* empty by syncrclone, and (b) if files still 
# exist in the directory (e.g. they were excluded), it will *not* delete them.
#
# This settings doesn't make sense for some remotes. Leave as None to set
# automatically based on whether the remote supports empty directories.
cleanup_empty_dirsA = None
cleanup_empty_dirsB = None

# By design, syncrclone needs to list all of the files on the remotes AFTER a run as well. 
# This can be slow on some remotes so syncrclone can try to reduce relisting at the end by
# using the original. Note that this feature is EXPERIMENTAL. There may be some edge
# cases not considered; especially with regards to move tracking and hashes.
#
# However, for most use cases, this will improve performance and may become the default 
# in the future
avoid_relist = False

## Rename Tracking

# Renames can be tracked if the file is unmodified on both sides and only
# renamed on one side (if it is renamed to the same on both sides, it won't 
# do anything). Will not track if a rename cannot be uniquely identified
#
# Tracking is done via the following. Note that the pool of considered
# files are *only* those that have been identified as new.
#
#   'size'    : Size of the file only. VERY UNSAFE
#   'mtime'   : mtime and size. Slightly safer than size but still risky
#   'hash'    : Hash of the files
#    None     : Disable rename tracking
#
# Because moving files has to be done with individual rclone calls, it is often more
# efficient to disable rename tracking as a delete and copy can be more efficient for
# lots of files. It also doesn't make sense to use renames on A or B if the remote B or A 
# doesn't support server-side copy or move.
renamesA = None
renamesB = None

## Logs

# All output is printed to stdout and stderr but this can also be saved and
# uploaded to a remote. Note that the last upload step will not be in the logs
# themselves. The log name is fixed as '{name}_{date}.log' 
#
# Can also specify a local location. Useful if both remotes are remote. Recall
# that the paths are relative to this file. If blank, will not save logs
save_logs = True
local_log_dest = '' # NOT on a remote

## Pre- and Post-run
# Specify shell code to be evaluated before and/or after running syncrclone. Note
# these are all run from the directory of this config (as with everything else).
# STDOUT and STDERR will be captured. Note that there is no validation or 
# security of the inputs. These are not actually called if using dry-run.
#
# If specified as a list, will run directly with subprocess. Otherwise uses shell=True
pre_sync_shell = ""

# The _post_ shell call also has "$STATS" defined which prints the run statistics and
# "$LOGNAME" which is the defined log name '{name}_{date}.log' 
# The timing will be different than that of the final log as it is run sooner.
post_sync_shell = ""

# Be default, even if the shell commands had an error, syncrclone out continue. 
# This setting can make it so that it will exit. Note that it ONLY applies to the 
# pre_sync_shell script as the only thing to break afterwards is relisting
stop_on_shell_error = False



#######
# This should only be changed by the user when migrating from an older config 
# to a newer one. Just because the current version of syncrclone and the version
# below do not match, it does not mean the sync won't work.
_syncrclone_version = '__VERSION__'


