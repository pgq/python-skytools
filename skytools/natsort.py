"""Natural sort.

Compares numeric parts numerically.
"""

import re as _re

# Based on idea at http://code.activestate.com/recipes/285264/
# Works with both Python 2.x and 3.x
# Ignores leading zeroes: 001 and 01 are considered equal

_rc = _re.compile(r'\d+|\D+')

__all__ = (
    'natsort_key', 'natsort', 'natsorted',
    'natsort_key_icase', 'natsort_icase', 'natsorted_icase'
)


def natsort_key(s):
    """Split string to numeric and non-numeric fragments."""
    return [not f[0].isdigit() and f or int(f, 10) for f in _rc.findall(s)]


def natsort(lst):
    """Natural in-place sort, case-sensitive."""
    lst.sort(key=natsort_key)


def natsorted(lst):
    """Return copy of list, sorted in natural order, case-sensitive.
    """
    lst = lst[:]
    natsort(lst)
    return lst


# case-insensitive api

def natsort_key_icase(s):
    """Split string to numeric and non-numeric fragments."""
    return natsort_key(s.lower())


def natsort_icase(lst):
    """Natural in-place sort, case-sensitive."""
    lst.sort(key=natsort_key_icase)


def natsorted_icase(lst):
    """Return copy of list, sorted in natural order, case-sensitive.
    """
    lst = lst[:]
    natsort_icase(lst)
    return lst

