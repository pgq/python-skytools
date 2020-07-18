"""Natural sort.

Compares numeric parts numerically.

Rules:

* String consists of numeric and non-numeric parts.
* Parts are compared pairwise, if both are numeric then numerically,
  otherwise textually.  (Only first fragment can have different type)

Extra rules for version numbers:

* In textual comparision, '~' is less than anything else, including end-of-string.
* In numeric comparision, numbers that start with '0' are compared as decimal
  fractions, thus number that starts with more zeroes is smaller.

"""

import re as _re

_rc = _re.compile(r'\d+|\D+', _re.A)

__all__ = (
    'natsort_key', 'natsort', 'natsorted',
    'natsort_key_icase', 'natsort_icase', 'natsorted_icase'
)


def natsort_key(s):
    """Returns tuple that sorts according to natsort rules.
    """
    # key consists of triplets (type:int, magnitude:int, value:str)
    key = []
    if '~' in s:
        s = s.replace('~', '\0')
    for frag in _rc.findall(s):
        if frag < '0':
            key.extend((1, 0, frag + '\1'))
        elif frag < '1':
            key.extend((2, len(frag.lstrip('0')) - len(frag), frag))
        elif frag < ':':
            key.extend((2, len(frag), frag))
        else:
            key.extend((3, 0, frag + '\1'))
    if not key or key[-3] == 2:
        key.extend((1, 0, '\1'))
    return tuple(key)


def natsort(lst):
    """Natural in-place sort, case-sensitive."""
    lst.sort(key=natsort_key)


def natsorted(lst):
    """Return copy of list, sorted in natural order, case-sensitive.
    """
    return sorted(lst, key=natsort_key)


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
    return sorted(lst, key=natsort_key_icase)

