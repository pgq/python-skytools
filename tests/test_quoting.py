"""Extra tests for quoting module.
"""

from __future__ import division, absolute_import, print_function

import sys, time
import skytools.psycopgwrapper
import skytools._cquoting
import skytools._pyquoting
from decimal import Decimal

from skytools.testing import ordered_dict
from nose.tools import *

# create a DictCursor row
class fake_cursor:
    index = ordered_dict({'id': 0, 'data': 1})
    description = ['x', 'x']
dbrow = skytools.psycopgwrapper._CompatRow(fake_cursor())
dbrow[0] = '123'
dbrow[1] = 'value'

def try_func(qfunc, data):
    for val, exp in data:
        got = qfunc(val)
        eq_(got, exp)

def test_quote_literal():
    sql_literal = [
        [None, "null"],
        ["", "''"],
        ["a'b", "'a''b'"],
        [r"a\'b", r"E'a\\''b'"],
        [1, "'1'"],
        [True, "'True'"],
        [Decimal(1), "'1'"],
    ]
    try_func(skytools._cquoting.quote_literal, sql_literal)
    try_func(skytools._pyquoting.quote_literal, sql_literal)
    try_func(skytools.quote_literal, sql_literal)

qliterals_common = [
    (r"""null""", None),
    (r"""NULL""", None),
    (r"""123""", "123"),
    (r"""''""", r""""""),
    (r"""'a''b''c'""", r"""a'b'c"""),
    (r"""'foo'""", r"""foo"""),
    (r"""E'foo'""", r"""foo"""),
    (r"""E'a\n\t\a\b\0\z\'b'""", "a\n\t\x07\x08\x00z'b"),
    (r"""$$$$""", r""),
    (r"""$$qw$e$z$$""", r"qw$e$z"),
    (r"""$qq$$aa$$$'"\\$qq$""", '$aa$$$\'"\\\\'),
]
def test_unquote_literal():
    qliterals_nonstd = qliterals_common + [
        (r"""'a\\b\\c'""", r"""a\b\c"""),
        (r"""e'a\\b\\c'""", r"""a\b\c"""),
    ]
    try_func(skytools._cquoting.unquote_literal, qliterals_nonstd)
    try_func(skytools._pyquoting.unquote_literal, qliterals_nonstd)
    try_func(skytools.unquote_literal, qliterals_nonstd)

def test_unquote_literal_std():
    qliterals_std = qliterals_common + [
        (r"''", r""),
        (r"'foo'", r"foo"),
        (r"E'foo'", r"foo"),
        (r"'\\''z'", r"\\'z"),
    ]
    for val, exp in qliterals_std:
        eq_(skytools._cquoting.unquote_literal(val, True), exp)
        eq_(skytools._pyquoting.unquote_literal(val, True), exp)
        eq_(skytools.unquote_literal(val, True), exp)

def test_quote_copy():
    sql_copy = [
        [None, "\\N"],
        ["", ""],
        ["a'\tb", "a'\\tb"],
        [r"a\'b", r"a\\'b"],
        [1, "1"],
        [True, "True"],
        [u"qwe", "qwe"],
        [Decimal(1), "1"],
    ]
    try_func(skytools._cquoting.quote_copy, sql_copy)
    try_func(skytools._pyquoting.quote_copy, sql_copy)
    try_func(skytools.quote_copy, sql_copy)

def test_quote_bytea_raw():
    sql_bytea_raw = [
        [None, None],
        [b"", ""],
        [b"a'\tb", "a'\\011b"],
        [b"a\\'b", r"a\\'b"],
        [b"\t\344", r"\011\344"],
    ]
    try_func(skytools._cquoting.quote_bytea_raw, sql_bytea_raw)
    try_func(skytools._pyquoting.quote_bytea_raw, sql_bytea_raw)
    try_func(skytools.quote_bytea_raw, sql_bytea_raw)

def test_quote_ident():
    sql_ident = [
        ['', '""'],
        ["a'\t\\\"b", '"a\'\t\\""b"'],
        ['abc_19', 'abc_19'],
        ['from', '"from"'],
        ['0foo', '"0foo"'],
        ['mixCase', '"mixCase"'],
    ]
    try_func(skytools.quote_ident, sql_ident)

def _sort_urlenc(func):
    def wrapper(data):
        res = func(data)
        return '&'.join(sorted(res.split('&')))
    return wrapper

def test_db_urlencode():
    t_urlenc = [
        [{}, ""],
        [{'a': 1}, "a=1"],
        [{'a': None}, "a"],
        [{'qwe': 1, u'zz': u"qwe"}, 'qwe=1&zz=qwe'],
        [ordered_dict({'qwe': 1, u'zz': u"qwe"}), 'qwe=1&zz=qwe'],
        [{'a': '\000%&'}, "a=%00%25%26"],
        [dbrow, 'data=value&id=123'],
        [{'a': Decimal("1")}, "a=1"],
    ]
    try_func(_sort_urlenc(skytools._cquoting.db_urlencode), t_urlenc)
    try_func(_sort_urlenc(skytools._pyquoting.db_urlencode), t_urlenc)
    try_func(_sort_urlenc(skytools.db_urlencode), t_urlenc)

def test_db_urldecode():
    t_urldec = [
        ["", {}],
        ["a=b&c", {'a': 'b', 'c': None}],
        ["&&b=f&&", {'b': 'f'}],
        [u"abc=qwe", {'abc': 'qwe'}],
        ["b=", {'b': ''}],
        ["b=%00%45", {'b': '\x00E'}],
    ]
    try_func(skytools._cquoting.db_urldecode, t_urldec)
    try_func(skytools._pyquoting.db_urldecode, t_urldec)
    try_func(skytools.db_urldecode, t_urldec)

def test_unescape():
    t_unesc = [
        ["", ""],
        ["\\N", "N"],
        ["abc", "abc"],
        [u"abc", "abc"],
        [r"\0\000\001\01\1", "\0\000\001\001\001"],
        [r"a\001b\tc\r\n", "a\001b\tc\r\n"],
    ]
    try_func(skytools._cquoting.unescape, t_unesc)
    try_func(skytools._pyquoting.unescape, t_unesc)
    try_func(skytools.unescape, t_unesc)

