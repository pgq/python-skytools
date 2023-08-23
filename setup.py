"""Setup for skytools module.
"""

from setuptools import Extension, setup

# use only stable abi
define_macros = [('Py_LIMITED_API', '0x03070000')]
py_limited_api = True

# run actual setup
setup(
    ext_modules = [
        Extension("skytools._cquoting", ["modules/cquoting.c"],
                  define_macros=define_macros, py_limited_api=py_limited_api),
        Extension("skytools._chashtext", ["modules/hashtext.c"],
                  define_macros=define_macros, py_limited_api=py_limited_api),
    ]
)

