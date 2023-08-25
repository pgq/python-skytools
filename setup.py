"""Setup for skytools module.
"""

from typing import Tuple
from setuptools import Extension, setup

try:
    from wheel.bdist_wheel import bdist_wheel
    class bdist_wheel_abi3(bdist_wheel):
        def get_tag(self) -> Tuple[str, str, str]:
            python, abi, plat = super().get_tag()
            if python.startswith("cp"):
                return CP_VER, "abi3", plat
            return python, abi, plat
    cmdclass = {"bdist_wheel": bdist_wheel_abi3}
except ImportError:
    cmdclass = {}

CP_VER = "cp37"
API_VER = ('Py_LIMITED_API', '0x03070000')

setup(
    cmdclass = cmdclass,
    ext_modules = [
        Extension("skytools._cquoting", ["modules/cquoting.c"],
                  define_macros=[API_VER], py_limited_api=True),
        Extension("skytools._chashtext", ["modules/hashtext.c"],
                  define_macros=[API_VER], py_limited_api=True),
    ]
)

