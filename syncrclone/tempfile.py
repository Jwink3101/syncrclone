#!/usr/bin/env python
"""
Setting a custom path for tempfile
"""

import os
import sys
import tempfile

tempfile.tempdir = os.path.join(tempfile.gettempdir(), 'syncrclone')
if not os.path.exists(tempfile.tempdir):
    os.makedirs(tempfile.tempdir)

sys.modules[__name__] = tempfile
