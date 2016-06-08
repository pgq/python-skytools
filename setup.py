#! /usr/bin/env python

from setuptools import setup, Extension

import sys

# don't build C module on win32 as it's unlikely to have dev env
BUILD_C_MOD = 1
if sys.platform == 'win32':
    BUILD_C_MOD = 0

# check if building C is allowed
c_modules = []
if BUILD_C_MOD:
    c_modules = [
        Extension("skytools._cquoting", ['modules/cquoting.c']),
        Extension("skytools._chashtext", ['modules/hashtext.c']),
    ]

# run actual setup
setup(
    name = "skytools",
    license = "ISC",
    version = '3.3',
    url = "https://github.com/pgq/python-skytools",
    maintainer = "Marko Kreen",
    maintainer_email = "markokr@gmail.com",
    description = "SkyTools - tools for PostgreSQL",
    packages = ['skytools'],
    ext_modules = c_modules,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: ISC License (ISCL)",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Topic :: Database",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
    ],
)
