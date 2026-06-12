"""Setup for skytools module.
"""

from typing import Tuple
from setuptools import Extension, setup, __version__ as st_version

import sysconfig

try:
    from setuptools.command.bdist_wheel import bdist_wheel

    class bdist_wheel_abi3(bdist_wheel):
        def get_tag(self) -> Tuple[str, str, str]:
            python, abi, plat = super().get_tag()
            if python.startswith("cp") and LIMITED_API:
                return CP_VER, "abi3", plat
            return python, abi, plat

    cmdclass = {"bdist_wheel": bdist_wheel_abi3}
except ImportError:
    cmdclass = {}

if sysconfig.get_config_var("Py_GIL_DISABLED"):
    CP_VER = 'unused'
    MACROS = []
    LIMITED_API = False
else:
    CP_VER = "cp310"
    MACROS = [('Py_LIMITED_API', '0x030a0000')]
    LIMITED_API = True

setup(
    cmdclass = cmdclass,
    ext_modules = [
        Extension("skytools._cquoting", ["modules/cquoting.c"],
                  define_macros=MACROS, py_limited_api=LIMITED_API),
        Extension("skytools._chashtext", ["modules/hashtext.c"],
                  define_macros=MACROS, py_limited_api=LIMITED_API),
    ]
)

