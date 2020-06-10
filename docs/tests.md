
## Test Process

Most, though not all, functionality is formally tested and with different backends. The way tests are done is 

* Build Test starting point *locally* on A only. Randomize mtimes in the *past*
* Use rclone to push the local copy of A to the remote (for non-local A or B)
* Use syncrclone to sync A <--> B. This will be less efficient since B is empty but it's also a good test
* Pull remote B to local B
* Make changes on A & B as needed
    * Any edits will set the mtime randomly in the *future*
* Push changes with rclone to A & B
* This syncrclone to sync A <--> B. This is the real test
* Pull remote A and B to local A and B
* Compare

## Testing other remotes

The beauty of rclone is that it is works on one remote that has similar features, it should work on others. So when a test is done using only size comparisons (for move tracking and for comparison), it *should* work. With that said, the following have not been rigorously tested

* Missing hash in a remote that *otherwise* has it (e.g. S3)
* One or both remotes not supporting modtime.

At the moment, there is no *automated* way to test other remotes besides `A`, `B`, `cryptA:`, `cryptB:`. In order to test others, add them to the `tests/rclone.cfg` and then add them to the appropriate test. Not all tests can handle all remotes by design (e.g. you won't try to test hashes if your remote doesn't support it) but the `test_main` should take any remote type and associated attributes

### Manually Tested

These are ones I have manually tested by following the above steps:

* B2
* WebDAV (see below)
* sftp (via `localhost` using macOS remote login)

#### WebDAV via rclone

To test these, for example, I run a server with:

```bash
rclone serve webdav             \
    -v --vfs-cache-mode writes  \
    --no-modtime                \
    --addr localhost:8080       \
    --user g --pass p .
```
Then have the following in the config
```ini
[test]
type = webdav
url = http://localhost:8080
vendor = other
user = g
pass = zPWIrpgPau25I-H66JwYVkw
```
And run the `test_main()


## Tests

This is not exhaustive. The `test_main` is the primary test that will consider reasonable settings for conflict resolution but compare different attributes. This is the main test that needs to pass for testing on a different remote.

Some (again, not necessarily exhaustive) explanation of the other tests:

* `move_attribs`: Test different (edge) cases of tracking moves with certain attributes.
* `reuse_hash`: Make sure the hash is being reused if possible when set
* `no_hashes`: Test how to handle hash compare without hashes.
* `conflict resolution`: Make sure tagging and moves are handled as expected
* `backups`: Make sure backups are done
* `dry_run`: Make sure dry-run doesn't do anything
* `logs`: Make sure logs get pushed properly
* `three_way`: Test for more than one remote, etc
* `locks`: Make sure locking works
* `local_mode`: Test when called from local mode (i.e. the config file is found with an implicit name)

## Missing Tests

* While I think the case is accounted for, I do not have a test where a remote *usually* has a hash but may not for some files (e.g. some S3 large uploads)

