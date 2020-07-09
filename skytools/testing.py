"""Utilities for tests.
"""


from collections import OrderedDict


def ordered_dict(d):
    """Return OrderedDict with sorted keys.
    """
    return OrderedDict(sorted(d.items()))

