"""Setup for skytools module.
"""

import sys

from setuptools import Extension, setup

_version = None
with open("skytools/installer_config.py") as f:
    for ln in f:
        if ln.startswith("package_version"):
            _version = ln.split()[2].strip("\"'")
len(_version)

# load info
with open("README.rst") as f:
    ldesc = f.read().strip()
    sdesc = ldesc.split("\n")[0].split("-", 1)[-1].strip()

# don"t build C module on win32 as it"s unlikely to have dev env
BUILD_C_MOD = 1
if sys.platform == "win32":
    BUILD_C_MOD = 1

# check if building C is allowed
c_modules = []
if BUILD_C_MOD:
    c_modules = [
        Extension("skytools._cquoting", ["modules/cquoting.c"]),
        Extension("skytools._chashtext", ["modules/hashtext.c"]),
    ]

# run actual setup
setup(
    name="skytools",
    description="Utilities for database scripts",
    long_description=ldesc,
    version=_version,
    license="ISC",
    url="https://github.com/pgq/python-skytools",
    maintainer="Marko Kreen",
    maintainer_email="markokr@gmail.com",
    packages=["skytools"],
    ext_modules=c_modules,
    zip_safe=False,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: ISC License (ISCL)",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
        "Topic :: Database",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
    ],
)

