import sys,time
tt = 0.5

sys.stdout.write('this is a test\n')
time.sleep(tt);sys.stdout.flush()
sys.stdout.buffer.write(b'line 2\n')
time.sleep(tt);sys.stdout.flush()
sys.stdout.buffer.write(b'Null>>\x00\x00<<Null\n')
time.sleep(tt);sys.stdout.flush()


sys.stderr.write('error line1\n')
time.sleep(tt);sys.stderr.flush()
sys.stderr.buffer.write(b'error line 2\n')
time.sleep(tt);sys.stdout.flush()
sys.stderr.buffer.write(b'ENull>>\x00\x00<<ENull\n')
sys.stderr.flush()