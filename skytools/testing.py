"""Utilities for tests.
"""

from collections import OrderedDict

def ordered_dict(d):
    """Return OrderedDict with sorted keys.

    >>> OrderedDict(dict(a=1,b=2,c=3))
    x
    """
    return OrderedDict(sorted(d.items()))

if __name__ == '__main__':
    import doctest
    doctest.testmod()
