# Run on Interval

This is a demo of a way to run the same call with a 30 minute interval.

Unlike crontab where you say "run every 30 minutes", with this you say "run and wait 30 minutes to run again"

## Main Script

```bash
#!/usr/bin/env bash

echo $$ > pid

while true; do
    syncrclone /path/to/config.py 1> /dev/null 2>&1
    sleep 1800
done
```

The idea being that you run syncrclone (or whatever) and then sleep for 1800 seconds (30 minutes) then run again.

Note that this example pipes everything to `/dev/null` since syncrclone can manage its own logs

## Running it

1. Copy the above into a file, maybe `myscript.sh`
2. Make executable
    ```
    $ chmod +x myscript.sh
    ```
3. Run it
    ```
    $ nohup myscript.sh 1> /dev/null 2>&1 &
    ```
4. To kill it, use the `pid` file
    ```
    $ kill $(cat pid)
    ```