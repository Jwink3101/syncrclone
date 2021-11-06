* Add support for `--hash-type` on specific remotes (likely just local ones)
* Windows! I suspect it would be very easy to work on Windows if it doesn't already work now, but I have zero testing
* Currently I offer `rclone_flags` which are used with all rclone calls. Then there is `rclone_flags{AB}` for specific ones used in listing, copies, deletes, and moves. Transfers do *not* currently use them but should they?
