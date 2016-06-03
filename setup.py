#! /usr/bin/env python

from distutils.core import setup, Extension

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
    maintainer = "Marko Kreen",
    maintainer_email = "markokr@gmail.com",
    description = "SkyTools - tools for PostgreSQL",
    platforms = "POSIX, MacOS, Windows",
    packages = ['skytools'],
    ext_modules = c_modules,
)
