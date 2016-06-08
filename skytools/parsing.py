
"""Various parsers for Postgres-specific data formats."""

from __future__ import division, absolute_import, print_function

import re
import skytools

__all__ = [
    "parse_pgarray", "parse_logtriga_sql", "parse_tabbed_table",
    "parse_statements", 'sql_tokenizer', 'parse_sqltriga_sql',
    "parse_acl", "dedent", "hsize_to_bytes",
    "parse_connect_string", "merge_connect_string"]

_rc_listelem = re.compile(r'( [^,"}]+ | ["] ( [^"\\]+ | [\\]. )* ["] )', re.X)

def parse_pgarray(array):
    r"""Parse Postgres array and return list of items inside it.

    Examples:
    >>> parse_pgarray('{}')
    []
    >>> parse_pgarray('{a,b,null,"null"}')
    ['a', 'b', None, 'null']
    >>> parse_pgarray(r'{"a,a","b\"b","c\\c"}')
    ['a,a', 'b"b', 'c\\c']
    >>> parse_pgarray("[0,3]={1,2,3}")
    ['1', '2', '3']
    >>> parse_pgarray(None) is None
    True
    >>> from nose.tools import *
    >>> assert_raises(ValueError, parse_pgarray, '}{')
    >>> assert_raises(ValueError, parse_pgarray, '[1]=}')
    >>> assert_raises(ValueError, parse_pgarray, '{"..." , }')

    """
    if array is None:
        return None
    if not array or array[0] not in ("{", "[") or array[-1] != '}':
        raise ValueError("bad array format: must be surrounded with {}")
    res = []
    pos = 1
    # skip optional dimensions descriptor "[a,b]={...}"
    if array[0] == "[":
        pos = array.find('{') + 1
        if pos < 1:
            raise ValueError("bad array format 2: must be surrounded with {}")
    while 1:
        m = _rc_listelem.search(array, pos)
        if not m:
            break
        pos2 = m.end()
        item = array[pos:pos2]
        if len(item) == 4 and item.upper() == "NULL":
            val = None
        else:
            if len(item) > 0 and item[0] == '"':
                if len(item) == 1 or item[-1] != '"':
                    raise ValueError("bad array format: broken '\"'")
                item = item[1:-1]
            val = skytools.unescape(item)
        res.append(val)

        pos = pos2 + 1
        if array[pos2] == "}":
            break
        elif array[pos2] != ",":
            raise ValueError("bad array format: expected ,} got " + repr(array[pos2]))
    if pos < len(array) - 1:
        raise ValueError("bad array format: failed to parse completely (pos=%d len=%d)" % (pos, len(array)))
    return res

#
# parse logtriga partial sql
#

class _logtriga_parser(object):
    """Parses logtriga/sqltriga partial SQL to values."""
    pklist = None
    def tokenizer(self, sql):
        """Token generator."""
        for ___typ, tok in sql_tokenizer(sql, ignore_whitespace=True):
            yield tok

    def parse_insert(self, tk, fields, values, key_fields, key_values):
        """Handler for inserts."""
        # (col1, col2) values ('data', null)
        if next(tk) != "(":
            raise Exception("syntax error")
        while 1:
            fields.append(next(tk))
            t = next(tk)
            if t == ")":
                break
            elif t != ",":
                raise Exception("syntax error")
        if next(tk).lower() != "values":
            raise Exception("syntax error, expected VALUES")
        if next(tk) != "(":
            raise Exception("syntax error, expected (")
        while 1:
            values.append(next(tk))
            t = next(tk)
            if t == ")":
                break
            if t == ",":
                continue
            raise Exception("expected , or ) got "+t)
        t = next(tk)
        raise Exception("expected EOF, got " + repr(t))

    def parse_update(self, tk, fields, values, key_fields, key_values):
        """Handler for updates."""
        # col1 = 'data1', col2 = null where pk1 = 'pk1' and pk2 = 'pk2'
        while 1:
            fields.append(next(tk))
            if next(tk) != "=":
                raise Exception("syntax error")
            values.append(next(tk))
            t = next(tk)
            if t == ",":
                continue
            elif t.lower() == "where":
                break
            else:
                raise Exception("syntax error, expected WHERE or , got "+repr(t))
        while 1:
            fld = next(tk)
            key_fields.append(fld)
            self.pklist.append(fld)
            if next(tk) != "=":
                raise Exception("syntax error")
            key_values.append(next(tk))
            t = next(tk)
            if t.lower() != "and":
                raise Exception("syntax error, expected AND got "+repr(t))

    def parse_delete(self, tk, fields, values, key_fields, key_values):
        """Handler for deletes."""
        # pk1 = 'pk1' and pk2 = 'pk2'
        while 1:
            fld = next(tk)
            key_fields.append(fld)
            self.pklist.append(fld)
            if next(tk) != "=":
                raise Exception("syntax error")
            key_values.append(next(tk))
            t = next(tk)
            if t.lower() != "and":
                raise Exception("syntax error, expected AND, got "+repr(t))

    def _create_dbdict(self, fields, values):
        fields = [skytools.unquote_ident(f) for f in fields]
        values = [skytools.unquote_literal(f) for f in values]
        return skytools.dbdict(zip(fields, values))

    def parse_sql(self, op, sql, pklist=None, splitkeys=False):
        """Main entry point."""
        if pklist is None:
            self.pklist = []
        else:
            self.pklist = pklist
        tk = self.tokenizer(sql)
        fields = []
        values = []
        key_fields = []
        key_values = []
        try:
            if op == "I":
                self.parse_insert(tk, fields, values, key_fields, key_values)
            elif op == "U":
                self.parse_update(tk, fields, values, key_fields, key_values)
            elif op == "D":
                self.parse_delete(tk, fields, values, key_fields, key_values)
            raise Exception("syntax error")
        except StopIteration:
            # last sanity check
            if (len(fields) + len(key_fields) == 0 or
                len(fields) != len(values) or
                len(key_fields) != len(key_values)):
                raise Exception("syntax error, fields do not match values")
        if splitkeys:
            return (self._create_dbdict(key_fields, key_values),
                    self._create_dbdict(fields, values))
        return self._create_dbdict(fields + key_fields, values + key_values)

def parse_logtriga_sql(op, sql, splitkeys=False):
    return parse_sqltriga_sql(op, sql, splitkeys=splitkeys)

def parse_sqltriga_sql(op, sql, pklist=None, splitkeys=False):
    """Parse partial SQL used by pgq.sqltriga() back to data values.

    Parser has following limitations:
     - Expects standard_quoted_strings = off
     - Does not support dollar quoting.
     - Does not support complex expressions anywhere. (hashtext(col1) = hashtext(val1))
     - WHERE expression must not contain IS (NOT) NULL
     - Does not support updating pk value, unless you use the splitkeys parameter.

    Returns dict of col->data pairs.

    >>> from skytools.testing import ordered_dict

    Insert event:
    >>> row = parse_logtriga_sql('I', '(id, data) values (1, null)')
    >>> ordered_dict(row)
    OrderedDict([('data', None), ('id', '1')])

    Update event:
    >>> row = parse_logtriga_sql('U', "data='foo' where id = 1")
    >>> ordered_dict(row)
    OrderedDict([('data', 'foo'), ('id', '1')])

    Delete event:
    >>> row = parse_logtriga_sql('D', "id = 1 and id2 = 'str''val'")
    >>> ordered_dict(row)
    OrderedDict([('id', '1'), ('id2', "str'val")])

    If you set the splitkeys parameter, it will return two dicts, one for key
    fields and one for data fields.

    Insert event:
    >>> keys, row = parse_logtriga_sql('I', '(id, data) values (1, null)', splitkeys=True)
    >>> keys, ordered_dict(row)
    ({}, OrderedDict([('data', None), ('id', '1')]))

    Update event:
    >>> parse_logtriga_sql('U', "data='foo' where id = 1", splitkeys=True)
    ({'id': '1'}, {'data': 'foo'})

    Delete event:
    >>> keys, row = parse_logtriga_sql('D', "id = 1 and id2 = 'str''val'", splitkeys=True)
    >>> (ordered_dict(keys), row)
    (OrderedDict([('id', '1'), ('id2', "str'val")]), {})

    """
    return _logtriga_parser().parse_sql(op, sql, pklist, splitkeys=splitkeys)


def parse_tabbed_table(txt):
    r"""Parse a tab-separated table into list of dicts.

    Expect first row to be column names.

    Very primitive.

    Test:
    >>> from skytools.testing import ordered_dict
    >>> [ordered_dict(d) for d in parse_tabbed_table('col1\tcol2\nval1\tval2\n')]
    [OrderedDict([('col1', 'val1'), ('col2', 'val2')])]
    """

    txt = txt.replace("\r\n", "\n")
    fields = None
    data = []
    for ln in txt.split("\n"):
        if not ln:
            continue
        if not fields:
            fields = ln.split("\t")
            continue
        cols = ln.split("\t")
        if len(cols) != len(fields):
            continue
        row = dict(zip(fields, cols))
        data.append(row)
    return data


_extstr = r""" ['] (?: [^'\\]+ | \\. | [']['] )* ['] """
_stdstr = r""" ['] (?: [^']+ | [']['] )* ['] """
_name = r""" (?: [a-z_][a-z0-9_$]* | " (?: [^"]+ | "" )* " ) """

_ident = r""" (?P<ident> %s ) """ % _name
_fqident = r""" (?P<ident> %s (?: \. %s )* ) """ % (_name, _name)

_base_sql = r"""
      (?P<dolq>   (?P<dname> [$] (?: [_a-z][_a-z0-9]*)? [$] )
                  .*?
                  (?P=dname) )
    | (?P<num>    [0-9][0-9.e]* )
    | (?P<numarg> [$] [0-9]+ )
    | (?P<pyold>  [%][(] [a-z_][a-z0-9_]* [)] [s] )
    | (?P<pynew>  [{] [^{}]+ [}] )
    | (?P<ws>     (?: \s+ | [/][*] .*? [*][/] | [-][-][^\n]* )+ )
    | (?P<sym>    (?: [-+*~!@#^&|?/%<>=]+ | [,()\[\].:;] ) )
    | (?P<error>  . )"""

_base_sql_fq = r"%s | %s" % (_fqident, _base_sql)
_base_sql = r"%s | %s" % (_ident, _base_sql)

_std_sql = r"""(?: (?P<str> [E] %s | %s ) | %s )""" % (_extstr, _stdstr, _base_sql)
_std_sql_fq = r"""(?: (?P<str> [E] %s | %s ) | %s )""" % (_extstr, _stdstr, _base_sql_fq)
_ext_sql = r"""(?: (?P<str> [E]? %s ) | %s )""" % (_extstr, _base_sql)
_ext_sql_fq = r"""(?: (?P<str> [E]? %s ) | %s )""" % (_extstr, _base_sql_fq)
_std_sql_rc = _ext_sql_rc = None
_std_sql_fq_rc = _ext_sql_fq_rc = None

def sql_tokenizer(sql, standard_quoting=False, ignore_whitespace=False,
                  fqident=False, show_location=False):
    r"""Parser SQL to tokens.

    Iterator, returns (toktype, tokstr) tuples.

    Example
    >>> [x for x in sql_tokenizer("select * from a.b", ignore_whitespace=True)]
    [('ident', 'select'), ('sym', '*'), ('ident', 'from'), ('ident', 'a'), ('sym', '.'), ('ident', 'b')]
    >>> [x for x in sql_tokenizer("\"c olumn\",'str''val'")]
    [('ident', '"c olumn"'), ('sym', ','), ('str', "'str''val'")]
    >>> list(sql_tokenizer('a.b a."b "" c" a.1', fqident=True, ignore_whitespace=True))
    [('ident', 'a.b'), ('ident', 'a."b "" c"'), ('ident', 'a'), ('sym', '.'), ('num', '1')]
    >>> list(sql_tokenizer(r"set 'a''\' + E'\''", standard_quoting=True, ignore_whitespace=True))
    [('ident', 'set'), ('str', "'a''\\'"), ('sym', '+'), ('str', "E'\\''")]
    >>> list(sql_tokenizer('a.b a."b "" c" a.1', fqident=True, standard_quoting=True, ignore_whitespace=True))
    [('ident', 'a.b'), ('ident', 'a."b "" c"'), ('ident', 'a'), ('sym', '.'), ('num', '1')]
    >>> list(sql_tokenizer('a.b\nc;', show_location=True, ignore_whitespace=True))
    [('ident', 'a', 1), ('sym', '.', 2), ('ident', 'b', 3), ('ident', 'c', 5), ('sym', ';', 6)]

    """
    global _std_sql_rc, _ext_sql_rc, _std_sql_fq_rc, _ext_sql_fq_rc
    if not _std_sql_rc:
        _std_sql_rc = re.compile(_std_sql, re.X | re.I | re.S)
        _ext_sql_rc = re.compile(_ext_sql, re.X | re.I | re.S)
        _std_sql_fq_rc = re.compile(_std_sql_fq, re.X | re.I | re.S)
        _ext_sql_fq_rc = re.compile(_ext_sql_fq, re.X | re.I | re.S)

    if standard_quoting:
        if fqident:
            rc = _std_sql_fq_rc
        else:
            rc = _std_sql_rc
    else:
        if fqident:
            rc = _ext_sql_fq_rc
        else:
            rc = _ext_sql_rc

    pos = 0
    while 1:
        m = rc.match(sql, pos)
        if not m:
            break
        pos = m.end()
        typ = m.lastgroup
        if ignore_whitespace and typ == "ws":
            continue
        tk = m.group()
        if show_location:
            yield (typ, tk, pos)
        else:
            yield (typ, tk)

_copy_from_stdin_re = r"copy.*from\s+stdin"
_copy_from_stdin_rc = None
def parse_statements(sql, standard_quoting=False):
    """Parse multi-statement string into separate statements.

    Returns list of statements.

    >>> [sql for sql in parse_statements("begin; select 1; select 'foo'; end;")]
    ['begin;', 'select 1;', "select 'foo';", 'end;']
    >>> [sql for sql in parse_statements("select (select 2+(select 3;);) ; select 4;")]
    ['select (select 2+(select 3;);) ;', 'select 4;']

    >>> [sql for sql in parse_statements('select ());')]
    Traceback (most recent call last):
        ...
    ValueError: syntax error - unbalanced parenthesis
    >>> [sql for sql in parse_statements('copy from stdin;')]
    Traceback (most recent call last):
        ...
    ValueError: copy from stdin not supported

    """

    global _copy_from_stdin_rc
    if not _copy_from_stdin_rc:
        _copy_from_stdin_rc = re.compile(_copy_from_stdin_re, re.X | re.I)
    tokens = []
    pcount = 0 # '(' level
    for typ, t in sql_tokenizer(sql, standard_quoting=standard_quoting):
        # skip whitespace and comments before statement
        if len(tokens) == 0 and typ == "ws":
            continue
        # keep the rest
        tokens.append(t)
        if t == "(":
            pcount += 1
        elif t == ")":
            pcount -= 1
        elif t == ";" and pcount == 0:
            sql = "".join(tokens)
            if _copy_from_stdin_rc.match(sql):
                raise ValueError("copy from stdin not supported")
            yield "".join(tokens)
            tokens = []
    if len(tokens) > 0:
        yield "".join(tokens)
    if pcount != 0:
        raise ValueError("syntax error - unbalanced parenthesis")

_acl_name = r'(?: [0-9a-z_]+ | " (?: [^"]+ | "" )* " )'
_acl_re = r'''
    \s* (?: group \s+ | user \s+ )?
    (?P<tgt> %s )?
    (?P<perm> = [a-z*]*  )?
    (?P<owner> / %s )?
    \s* $
    ''' % (_acl_name, _acl_name)
_acl_rc = None

def parse_acl(acl):
    """Parse ACL entry.

    >>> parse_acl('user=rwx/owner')
    ('user', 'rwx', 'owner')
    >>> parse_acl('" ""user"=rwx/" ""owner"')
    (' "user', 'rwx', ' "owner')
    >>> parse_acl('user=rwx')
    ('user', 'rwx', None)
    >>> parse_acl('=/f')
    (None, '', 'f')

    On error (is this ok?):
    >>> parse_acl('?') is None
    True

    """
    global _acl_rc
    if not _acl_rc:
        _acl_rc = re.compile(_acl_re, re.I | re.X)

    m = _acl_rc.match(acl)
    if not m:
        return None

    target = m.group('tgt')
    perm = m.group('perm')
    owner = m.group('owner')

    if target:
        target = skytools.unquote_ident(target)
    if perm:
        perm = perm[1:]
    if owner:
        owner = skytools.unquote_ident(owner[1:])

    return (target, perm, owner)


def dedent(doc):
    r"""Relaxed dedent.

    - takes whitespace to be removed from first indented line.
    - allows empty or non-indented lines at the start
    - allows first line to be unindented
    - skips empty lines at the start
    - ignores indent of empty lines
    - if line does not match common indent, is stays unchanged

    >>> dedent('  Line1:\n    Line 2\n')
    'Line1:\n  Line 2\n'
    >>> dedent('  \nLine1:\n  Line 2\n Line 3\n    Line 4')
    'Line1:\nLine 2\n Line 3\n  Line 4\n'
    """
    pfx = None
    res = []
    for ln in doc.splitlines():
        ln = ln.rstrip()
        if not pfx and len(res) < 2:
            if not ln:
                continue
            wslen = len(ln) - len(ln.lstrip())
            pfx = ln[ : wslen]
        if pfx:
            if ln.startswith(pfx):
                ln = ln[len(pfx):]
        res.append(ln)
    res.append('')
    return '\n'.join(res)


def hsize_to_bytes(input_str):
    """ Convert sizes from human format to bytes (string to integer)

    >>> hsize_to_bytes('10G'), hsize_to_bytes('12k')
    (10737418240, 12288)
    """

    m = re.match(r"^([0-9]+) *([KMGTPEZY]?)B?$", input_str.strip(), re.IGNORECASE)
    if not m:
        raise ValueError("cannot parse: %s" % input_str)
    units = ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']
    nbytes = int(m.group(1)) * 1024 ** units.index(m.group(2).upper())
    return nbytes

#
# Connect string parsing
#

_cstr_rx = r""" \s* (\w+) \s* = \s* ( ' ( \\.| [^'\\] )* ' | \S+ ) \s* """
_cstr_unesc_rx = r"\\(.)"
_cstr_badval_rx = r"[\s'\\]"
_cstr_rc = None
_cstr_unesc_rc = None
_cstr_badval_rc = None

def parse_connect_string(cstr):
    r"""Parse Postgres connect string.

    >>> parse_connect_string("host=foo")
    [('host', 'foo')]
    >>> parse_connect_string(r" host = foo password = ' f\\\o\'o ' ")
    [('host', 'foo'), ('password', "' f\\o'o '")]
    >>> parse_connect_string(r" host = ")
    Traceback (most recent call last):
        ...
    ValueError: Invalid connect string

    """
    global _cstr_rc, _cstr_unesc_rc
    if not _cstr_rc:
        _cstr_rc = re.compile(_cstr_rx, re.X)
        _cstr_unesc_rc = re.compile(_cstr_unesc_rx)
    pos = 0
    res = []
    while pos < len(cstr):
        m = _cstr_rc.match(cstr, pos)
        if not m:
            raise ValueError('Invalid connect string')
        pos = m.end()
        k = m.group(1)
        v = m.group(2)
        if v[0] == "'":
            v = _cstr_unesc_rc.sub(r"\1", v)
        res.append((k, v))
    return res

def merge_connect_string(cstr_arg_list):
    """Put fragments back together.

    >>> merge_connect_string([('host', 'ip'), ('pass', ''), ('x', ' ')])
    "host=ip pass='' x=' '"
    """
    global _cstr_badval_rc
    if not _cstr_badval_rc:
        _cstr_badval_rc = re.compile(_cstr_badval_rx)

    buf = []
    for k, v in cstr_arg_list:
        if not v or _cstr_badval_rc.search(v):
            v = v.replace('\\', r'\\')
            v = v.replace("'", r"\'")
            v = "'" + v + "'"
        buf.append("%s=%s" % (k, v))
    return ' '.join(buf)

