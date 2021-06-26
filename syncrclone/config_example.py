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
# remaining files will be computed is a second rclone call.
#
# For most other remotes (e.g. S3, B2), hashes are stored by the remote
# so there is no need to reuse them
reuse_hashesA = False
reuse_hashesB = False

# When backups are set, all overwrites or deletes will instead be backed up.
# The only reason this should be disabled is if you plan to use some backup
# built into BOTH remotes
backup = True

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
# can be disabled. Note even if setting locks if disabled, syncrclone will
# still respect them!
set_lock = True

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
#   'inode'   : inode (plus mtime and size) of the file. See below for
#               getting inodes. Can only be used if local and will raise issues
#               otherwise
#    None     : Disable rename tracking
renamesA = None
renamesB = None

## Logs
# All output is printed to stdout and stderr but this can also be saved and
# uploaded to a remote. Note that the last upload step will not be in the logs
# themselves. The log name is fixed as '{name}_{date}.log' but the path
# can be set. Note that the `.syncrclone` folder is always excluded if you do not
# wish to also track the logs, though it can be helpful. Especially if there
# is more than one syncpair
#
# Can also specify a local location. Useful if both remotes are remote. Recall
# that the paths are relative to this file
log_dest = '' # Relative to root of each remote
local_log_dest = ''





#######
# This should only be changed by the user when migrating from an older config 
# to a newer one. Just because the current version of syncrclone and the version
# below do not match, it does not mean the sync won't work.
_syncrclone_version = '__VERSION__'


