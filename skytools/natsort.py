"""Natural sort.

Compares numeric parts numerically.

Rules:

* String consists of numeric and non-numeric parts.
* Parts are compared pairwise, if both are numeric then numerically,
  otherwise textually.  (Only first fragment can have different type)
* If strings are different, they should compare differnet in natsort.

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
    """Returns string that sorts according to natsort rules.
    """
    # generates four types of fragments:
    # 1) strings < "0", stay as-is
    # 2) numbers starting with 0, fragment starts with "A".."Z"
    # 3) numbers starting with 1..9, fragment starts with "a".."z"
    # 4) strings > "9", fragment starts with "|"
    if "~" in s:
        s = s.replace("~", "\0")
    key = []
    key_append = key.append
    for frag in _rc.findall(s):
        if frag < "0":
            key_append(frag)
            key_append("\1")
        elif frag < "1":
            nzeros = len(frag) - len(frag.lstrip('0'))
            mag = str(nzeros)
            mag = str(10**len(mag) - nzeros)
            key_append(chr(0x5B - len(mag)))    # Z, Y, X, ...
            key_append(mag)
            key_append(frag)
        elif frag < ":":
            mag = str(len(frag))
            key_append(chr(0x60 + len(mag)))    # a, b, c, ...
            key_append(mag)
            key_append(frag)
        else:
            key_append("|")
            key_append(frag)
            key_append("\1")
    if not (key and key[-1] == "\1"):
        key_append("\1")
    return "".join(key)


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

