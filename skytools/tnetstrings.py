"""TNetStrings.

>>> def ustr(v): return repr(v).replace("u'", "'")
>>> def nstr(b): return b.decode('utf8')
>>> if isinstance('qwe', bytes): nstr = str
>>> vals = (None, False, True, 222, 333.0, "foo", u"bar")
>>> tnvals = [nstr(dumps(v)) for v in vals]
>>> tnvals
['0:~', '5:false!', '4:true!', '3:222#', '5:333.0^', '3:foo,', '3:bar,']
>>> vals2 = [[], (), {}, [1,2], {'a':'b'}]
>>> tnvals2 = [nstr(dumps(v)) for v in vals2]
>>> tnvals2
['0:]', '0:]', '0:}', '8:1:1#1:2#]', '8:1:a,1:b,}']
>>> ustr([parse(dumps(v)) for v in vals])
"[None, False, True, 222, 333.0, 'foo', 'bar']"
>>> ustr([parse(dumps(v)) for v in vals2])
"[[], [], {}, [1, 2], {'a': 'b'}]"
>>> nstr(dumps([memoryview(b'zzz'),b'qqq']))
'12:3:zzz,3:qqq,]'

Error handling:

>>> def errtest(bstr, exc):
...     try:
...         loads(bstr)
...         raise Exception('no exception')
...     except exc:
...         return None
>>> errtest(b'4:qwez!', ValueError)
>>> errtest(b'4:', ValueError)
>>> errtest(b'4:qwez', ValueError)
>>> errtest(b'4', ValueError)
>>> errtest(b'', ValueError)
>>> errtest(b'999999999999999999:z,', ValueError)
>>> errtest(u'qweqwe', TypeError)
>>> errtest(b'4:true!0:~', ValueError)
>>> errtest(b'1:X~', ValueError)
>>> errtest(b'8:1:1#1:2#}', ValueError)
>>> errtest(b'1:Xz', ValueError)

>>> dumps(divmod)
Traceback (most recent call last):
    ...
TypeError: Object type not supported: <built-in function divmod>



"""

from __future__ import division, absolute_import, print_function

import codecs

__all__ = ['loads', 'dumps']

try:
    unicode
except NameError:
    unicode = str   # noqa
    long = int      # noqa

_memstr_types = (unicode, bytes, memoryview)
_struct_types = (list, tuple, dict)
_inttypes = (int, long)

def _dumps(dst, val):
    if isinstance(val, _struct_types):
        tlenpos = len(dst)
        tlen = 0
        dst.append(None)
        if isinstance(val, dict):
            for k in val:
                tlen += _dumps(dst, k)
                tlen += _dumps(dst, val[k])
            dst.append(b'}')
        else:
            for v in val:
                tlen += _dumps(dst, v)
            dst.append(b']')
        dst[tlenpos] = b'%d:' % tlen
        return len(dst[tlenpos]) + tlen + 1
    elif isinstance(val, _memstr_types):
        if isinstance(val, unicode):
            bval = val.encode('utf8')
        elif isinstance(val, memoryview):
            bval = val.tobytes()
        else:
            bval = val
        tval = b'%d:%s,' % (len(bval), bval)
    elif isinstance(val, bool):
        tval = val and b'4:true!' or b'5:false!'
    elif isinstance(val, _inttypes):
        bval = b'%d' % val
        tval = b'%d:%s#' % (len(bval), bval)
    elif isinstance(val, float):
        bval = b'%r' % val
        tval = b'%d:%s^' % (len(bval), bval)
    elif val is None:
        tval = b'0:~'
    else:
        raise TypeError("Object type not supported: %r" % val)
    dst.append(tval)
    return len(tval)

_decode_utf8 = codecs.getdecoder('utf8')
def _loads(buf):
    pos = 0
    maxlen = min(len(buf), 9)
    while buf[pos:pos+1] != b':':
        pos += 1
        if pos > maxlen:
            raise ValueError("Too large length")
    lenbytes = buf[ : pos].tobytes()
    tlen = int(lenbytes)
    ofs = len(lenbytes) + 1
    endofs = ofs + tlen

    val = buf[ofs : endofs]
    code = buf[endofs : endofs + 1]
    rest = buf[endofs + 1:]
    if len(val) + 1 != tlen + len(code):
        raise ValueError("failed to load value, invalid length")

    if code == b',':
        return _decode_utf8(val)[0], rest
    elif code == b'#':
        return int(val.tobytes(), 10), rest
    elif code == b'^':
        return float(val.tobytes()), rest
    elif code == b']':
        listobj = []
        while val:
            elem, val = _loads(val)
            listobj.append(elem)
        return listobj, rest
    elif code == b'}':
        dictobj = {}
        while val:
            k, val = _loads(val)
            if not isinstance(k, unicode):
                raise ValueError("failed to load value, invalid key type")
            dictobj[k], val = _loads(val)
        return dictobj, rest
    elif code == b'!':
        if val == b'true':
            return True, rest
        if val == b'false':
            return False, rest
        raise ValueError("failed to load value, invalid boolean value")
    elif code == b'~':
        if val == b'':
            return None, rest
        raise ValueError("failed to load value, invalid null value")
    else:
        raise ValueError("failed to load value, invalid value code")

#
# Public API
#

def dumps(val):
    """Dump object tree as TNetString value.
    """
    dst = []
    _dumps(dst, val)
    return b''.join(dst)

def loads(binval):
    """Parse TNetstring from byte string.
    """
    if not isinstance(binval, (bytes, memoryview)):
        raise TypeError("Bytes or memoryview required")
    obj, rest = _loads(memoryview(binval))
    if rest:
        raise ValueError("Not all data processed")
    return obj

# old compat?
parse = loads
dump = dumps

