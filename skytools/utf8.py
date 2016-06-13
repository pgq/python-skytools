r"""UTF-8 sanitizer.

Python's UTF-8 parser is quite relaxed, this creates problems when
talking with other software that uses stricter parsers.

>>> _norm(safe_utf8_decode(b"foobar"))
(True, ['f', 'o', 'o', 'b', 'a', 'r'])
>>> _norm(safe_utf8_decode(b'X\0Z'))
(False, ['X', 65533, 'Z'])
>>> _norm(safe_utf8_decode(b'OK'))
(True, ['O', 'K'])
>>> _norm(safe_utf8_decode(b'X\xF1Y'))
(False, ['X', 65533, 'Y'])

>>> _norm_str(sanitize_unicode(u'\uD801\uDC01'))
[66561]

>>> sanitize_unicode(b'qwe')
Traceback (most recent call last):
    ...
TypeError: Need unicode string
"""

## these give different results in py27 and py35
# >>> _norm(safe_utf8_decode(b'X\xed\xa0\x80Y\xed\xb0\x89Z'))
# (False, ['X', 65533, 65533, 65533, 'Y', 65533, 65533, 65533, 'Z'])
# >>> _norm(safe_utf8_decode(b'X\xed\xa0\x80\xed\xb0\x89Z'))
# (False, ['X', 65533, 65533, 65533, 65533, 65533, 65533, 'Z'])
# from __future__ import division, absolute_import, print_function

import re
import codecs

try:
    unichr
except NameError:
    unichr = chr        # noqa
    unicode = str       # noqa

def _norm_char(uchr):
    code = ord(uchr)
    if code >= 0x20 and code < 0x7f:
        return chr(code)
    return code

def _norm_str(ustr):
    return [_norm_char(c) for c in ustr]

def _norm(tup):
    flg, ustr = tup
    return (flg, _norm_str(ustr))


__all__ = ['safe_utf8_decode']

# by default, use same symbol as 'replace'
REPLACEMENT_SYMBOL = unichr(0xFFFD)   # 65533

def _fix_utf8(m):
    """Merge UTF16 surrogates, replace others"""
    u = m.group()
    if len(u) == 2:
        # merge into single symbol
        c1 = ord(u[0])
        c2 = ord(u[1])
        c = 0x10000 + ((c1 & 0x3FF) << 10) + (c2 & 0x3FF)
        return unichr(c)
    else:
        # use replacement symbol
        return REPLACEMENT_SYMBOL

_urc = None

def sanitize_unicode(u):
    """Fix invalid symbols in unicode string."""
    global _urc

    if not isinstance(u, unicode):
        raise TypeError('Need unicode string')

    # regex for finding invalid chars, works on unicode string
    if not _urc:
        rx = u"[\uD800-\uDBFF] [\uDC00-\uDFFF]? | [\0\uDC00-\uDFFF]"
        _urc = re.compile(rx, re.X)

    # now find and fix UTF16 surrogates
    m = _urc.search(u)
    if m:
        u = _urc.sub(_fix_utf8, u)
    return u

def safe_replace(exc):
    """Replace only one symbol at a time.

    Builtin .decode('xxx', 'replace') replaces several symbols
    together, which is unsafe.
    """
    c2 = REPLACEMENT_SYMBOL

    # we could assume latin1
    #if 0:
    #    c1 = exc.object[exc.start]
    #    c2 = unichr(ord(c1))

    return c2, exc.start + 1

# register, it will be globally available
codecs.register_error("safe_replace", safe_replace)

def safe_utf8_decode(s):
    """Decode UTF-8 safely.

    Acts like str.decode('utf8', 'replace') but also fixes
    UTF16 surrogates and NUL bytes, which Python's default
    decoder does not do.

    @param s: utf8-encoded byte string
    @return: tuple of (was_valid_utf8, unicode_string)
    """

    # decode with error detection
    ok = True
    try:
        # expect no errors by default
        u = s.decode('utf8')
    except UnicodeDecodeError:
        u = s.decode('utf8', 'safe_replace')
        ok = False

    u2 = sanitize_unicode(u)
    if u is not u2:
        ok = False
    return (ok, u2)

