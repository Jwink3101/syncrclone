# Tests

Tests are done mostly with local remotes though a few can also be done with other remotes. Especially the main test that does core features.

In order to be general, tests are always done as follows:

## Process

* Init
    * Delete the folders
    * Write the config (maybe with changes?)
    
* Pre
    * Files are initially created in a local `A/` folder
    * Config is set as needed and written
* setup
    * Files are `rclone sync A/ B/`
* Sync
    * `A/` and `B/` are pushed to the respective remote. If local, this is `Aremote` and `Bremote`.
    * Sync is done on the remotes. This is now the baseline
    * Files are pulled back
* Build
    * Changes are made for the tests in `A/` and `B/` then pushed with rclone
* Sync
    * `A/` and `B/` are pushed to the respective remote. If local, this is `Aremote` and `Bremote`.
    * Sync is done on the remotes. This is now the baseline
    * Files are pulled back
* Compare

## Writing files:

All files pre-baseline are written with a mod time that is randomly between -5 and -10 minutes of now. All files written post baseline are given a mod-time of +5 to +10 and can be shifted even more! The random number generator is seeded to make this consistent from run to run

