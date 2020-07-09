"""Utilities for tests.
"""

from __future__ import absolute_import, division, print_function

from collections import OrderedDict


def ordered_dict(d):
    """Return OrderedDict with sorted keys.

    >>> OrderedDict(dict(a=1,b=2,c=3))
    x
    """
    return OrderedDict(sorted(d.items()))

