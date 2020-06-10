#!/usr/bin/env python
import sys

# This shouldn't be needed since I have python_requires set but just in case:
if sys.version_info < (3,6):
    raise ValueError('Must use python >= 3.6')

import syncrclone

from setuptools import setup

setup(
    name='syncrclone',
    packages=['syncrclone'],
    long_description=open('readme.md').read(),
    entry_points = {
        'console_scripts': ['syncrclone=syncrclone.cli:cli'],
    },
    version=syncrclone.__version__,
    description='Python-based bi-direction sync tool for rclone',
    url='https://github.com/Jwink3101/syncrclone',
    author="Justin Winokur",
    author_email='Jwink3101@@users.noreply.github.com',
    license='MIT',
    python_requires='>=3.6'
)
