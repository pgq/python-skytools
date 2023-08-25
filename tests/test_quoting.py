"""Extra tests for quoting module.
"""

from typing import Dict, Callable, Any, List, Type, Tuple, Union, Optional
from decimal import Decimal

try:
    import psycopg2.extras
    _have_psycopg2 = True
except ImportError:
    _have_psycopg2 = False

import pytest

import skytools._cquoting
import skytools._pyquoting
from skytools.quoting import (
    json_decode, json_encode, make_pgarray,
    quote_fqident, unescape_copy, unquote_fqident,
)

QuoteTests = List[Tuple[Any, str]]
QuoteFunc = Callable[[Any], str]
UnquoteTests = List[Tuple[str, Optional[str]]]
UnquoteFunc = Callable[[str], Optional[str]]

class fake_cursor:
    """create a DictCursor row"""
    index = {'id': 0, 'data': 1}
    description = ['x', 'x']


if _have_psycopg2:
    dbrow = psycopg2.extras.DictRow(fake_cursor())
    dbrow[0] = '123'
    dbrow[1] = 'value'


def try_quote(func: QuoteFunc, data_list: QuoteTests) -> None:
    for val, exp in data_list:
        got = func(val)
        assert got == exp


def try_unquote(func: UnquoteFunc, data_list: UnquoteTests) -> None:
    for val, exp in data_list:
        got = func(val)
        assert got == exp


def test_quote_literal() -> None:
    sql_literal = [
        (None, "null"),
        ("", "''"),
        ("a'b", "'a''b'"),
        (r"a\'b", r"E'a\\''b'"),
        (1, "'1'"),
        (True, "'True'"),
        (Decimal(1), "'1'"),
        (u'qwe', "'qwe'")
    ]
    def quote_literal_c(x: Any) -> str:
        return skytools._cquoting.quote_literal(x)
    def quote_literal_py(x: Any) -> str:
        return skytools._pyquoting.quote_literal(x)
    def quote_literal_default(x: Any) -> str:
        return skytools.quote_literal(x)
    try_quote(quote_literal_default, sql_literal)
    try_quote(quote_literal_default, sql_literal)
    try_quote(quote_literal_default, sql_literal)


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
    (u"'qwe'", 'qwe'),
]

bad_dol_literals = [
    ('$$', '$$'),
    #('$$q', '$$q'),
    ('$$q$', '$$q$'),
    ('$q$q$', '$q$q$'),
    ('$q$q$x$', '$q$q$x$'),
]


def test_unquote_literal() -> None:
    qliterals_nonstd = qliterals_common + [
        (r"""'a\\b\\c'""", r"""a\b\c"""),
        (r"""e'a\\b\\c'""", r"""a\b\c"""),
    ]
    def unquote_literal_c(x: str) -> Optional[str]:
        return skytools._cquoting.unquote_literal(x)
    def unquote_literal_py(x: str) -> Optional[str]:
        return skytools._pyquoting.unquote_literal(x)
    def unquote_literal_default(x: str) -> Optional[str]:
        return skytools.unquote_literal(x)
    try_unquote(unquote_literal_c, qliterals_nonstd)
    try_unquote(unquote_literal_py, qliterals_nonstd)
    try_unquote(unquote_literal_default, qliterals_nonstd)

    for v1, v2 in bad_dol_literals:
        with pytest.raises(ValueError):
            skytools._pyquoting.unquote_literal(v1)
        with pytest.raises(ValueError):
            skytools._cquoting.unquote_literal(v1)
        with pytest.raises(ValueError):
            skytools.unquote_literal(v1)


def test_unquote_literal_std() -> None:
    qliterals_std = qliterals_common + [
        (r"''", r""),
        (r"'foo'", r"foo"),
        (r"E'foo'", r"foo"),
        (r"'\\''z'", r"\\'z"),
    ]
    for val, exp in qliterals_std:
        assert skytools._cquoting.unquote_literal(val, True) == exp
        assert skytools._pyquoting.unquote_literal(val, True) == exp
        assert skytools.unquote_literal(val, True) == exp


def test_quote_copy() -> None:
    sql_copy = [
        (None, "\\N"),
        ("", ""),
        ("a'\tb", "a'\\tb"),
        (r"a\'b", r"a\\'b"),
        (1, "1"),
        (True, "True"),
        (u"qwe", "qwe"),
        (Decimal(1), "1"),
    ]
    try_quote(skytools._cquoting.quote_copy, sql_copy)
    try_quote(skytools._pyquoting.quote_copy, sql_copy)
    try_quote(skytools.quote_copy, sql_copy)


def test_quote_bytea_raw() -> None:
    sql_bytea_raw: List[Tuple[Optional[bytes], Optional[str]]] = [
        (None, None),
        (b"", ""),
        (b"a'\tb", "a'\\011b"),
        (b"a\\'b", r"a\\'b"),
        (b"\t\344", r"\011\344"),
    ]
    for val, exp in sql_bytea_raw:
        assert skytools._cquoting.quote_bytea_raw(val) == exp
        assert skytools._pyquoting.quote_bytea_raw(val) == exp
        assert skytools.quote_bytea_raw(val) == exp


def test_quote_bytea_raw_fail() -> None:
    with pytest.raises(TypeError):
        skytools._pyquoting.quote_bytea_raw(u'qwe')  # type: ignore[arg-type]
    #assert_raises(TypeError, skytools._cquoting.quote_bytea_raw, u'qwe')
    #assert_raises(TypeError, skytools.quote_bytea_raw, 'qwe')


def test_quote_ident() -> None:
    sql_ident = [
        ('', '""'),
        ("a'\t\\\"b", '"a\'\t\\""b"'),
        ('abc_19', 'abc_19'),
        ('from', '"from"'),
        ('0foo', '"0foo"'),
        ('mixCase', '"mixCase"'),
        (u'utf', 'utf'),
    ]
    try_quote(skytools.quote_ident, sql_ident)


def test_fqident() -> None:
    assert quote_fqident('tbl') == 'public.tbl'
    assert quote_fqident('Baz.Foo.Bar') == '"Baz"."Foo.Bar"'


def _sort_urlenc(func: Callable[[Any], str]) -> Callable[[Any], str]:
    def wrapper(data: Any) -> str:
        res = func(data)
        return '&'.join(sorted(res.split('&')))
    return wrapper


def test_db_urlencode() -> None:
    t_urlenc = [
        ({}, ""),
        ({'a': 1}, "a=1"),
        ({'a': None}, "a"),
        ({'qwe': 1, u'zz': u"qwe"}, 'qwe=1&zz=qwe'),
        ({'qwe': 1, u'zz': u"qwe"}, 'qwe=1&zz=qwe'),
        ({'a': '\000%&'}, "a=%00%25%26"),
        ({'a': Decimal("1")}, "a=1"),
    ]
    if _have_psycopg2:
        t_urlenc.append((dbrow, 'data=value&id=123'))
    try_quote(_sort_urlenc(skytools._cquoting.db_urlencode), t_urlenc)
    try_quote(_sort_urlenc(skytools._pyquoting.db_urlencode), t_urlenc)
    try_quote(_sort_urlenc(skytools.db_urlencode), t_urlenc)


def test_db_urldecode() -> None:
    t_urldec = [
        ("", {}),
        ("a=b&c", {'a': 'b', 'c': None}),
        ("&&b=f&&", {'b': 'f'}),
        (u"abc=qwe", {'abc': 'qwe'}),
        ("b=", {'b': ''}),
        ("b=%00%45", {'b': '\x00E'}),
    ]
    for val, exp in t_urldec:
        assert skytools._cquoting.db_urldecode(val) == exp
        assert skytools._pyquoting.db_urldecode(val) == exp
        assert skytools.db_urldecode(val) == exp


def test_unescape() -> None:
    t_unesc: List[Tuple[str, str]] = [
        ("", ""),
        ("\\N", "N"),
        ("abc", "abc"),
        (r"\0\000\001\01\1", "\0\000\001\001\001"),
        (r"a\001b\tc\r\n", "a\001b\tc\r\n"),
    ]
    for val, exp in t_unesc:
        assert skytools._cquoting.unescape(val) == exp
        assert skytools._pyquoting.unescape(val) == exp
        assert skytools.unescape(val) == exp


def test_quote_bytea_literal() -> None:
    bytea_raw = [
        (None, "null"),
        (b"", "''"),
        (b"a'\tb", "E'a''\\\\011b'"),
        (b"a\\'b", r"E'a\\\\''b'"),
        (b"\t\344", r"E'\\011\\344'"),
    ]
    try_quote(skytools.quote_bytea_literal, bytea_raw)


def test_quote_bytea_copy() -> None:
    bytea_raw = [
        (None, "\\N"),
        (b"", ""),
        (b"a'\tb", "a'\\\\011b"),
        (b"a\\'b", r"a\\\\'b"),
        (b"\t\344", r"\\011\\344"),
    ]
    try_quote(skytools.quote_bytea_copy, bytea_raw)


def test_quote_statement() -> None:
    sql = "set a=%s, b=%s, c=%s"
    args = [None, u"qwe'qwe", 6.6]
    assert skytools.quote_statement(sql, args) == "set a=null, b='qwe''qwe', c='6.6'"

    sql2 = "set a=%(a)s, b=%(b)s, c=%(c)s"
    args2 = dict(a=None, b="qwe'qwe", c=6.6)
    assert skytools.quote_statement(sql2, args2) == "set a=null, b='qwe''qwe', c='6.6'"


def test_quote_json() -> None:
    json_string_vals = [
        (None, "null"),
        ('', '""'),
        (u'xx', '"xx"'),
        ('qwe"qwe\t', '"qwe\\"qwe\\t"'),
        ('\x01', '"\\u0001"'),
    ]
    try_quote(skytools.quote_json, json_string_vals)


def test_unquote_ident() -> None:
    idents = [
        ('qwe', 'qwe'),
        ('"qwe"', 'qwe'),
        ('"q""w\\\\e"', 'q"w\\\\e'),
        ('Foo', 'foo'),
        ('"Wei "" rd"', 'Wei " rd'),
    ]
    for val, exp in idents:
        assert skytools.unquote_ident(val) == exp



def test_unquote_ident_fail() -> None:
    with pytest.raises(Exception):
        skytools.unquote_ident('asd"asd')


def test_unescape_copy() -> None:
    assert unescape_copy(r'baz\tfo\'o') == "baz\tfo'o"
    assert unescape_copy(r'\N') is None


def test_unquote_fqident() -> None:
    assert unquote_fqident('Foo') == 'foo'
    assert unquote_fqident('"Foo"."Bar "" z"') == 'Foo.Bar " z'


def test_json_encode() -> None:
    assert json_encode({'a': 1}) == '{"a": 1}'
    assert json_encode('a') == '"a"'
    assert json_encode(['a']) == '["a"]'
    assert json_encode(a=1) == '{"a": 1}'


def test_json_decode() -> None:
    assert json_decode('[1]') == [1]


def test_make_pgarray() -> None:
    assert make_pgarray([]) == '{}'
    assert make_pgarray(['foo_3', 1, '', None]) == '{foo_3,1,"",NULL}'

    res = make_pgarray([None, ',', '\\', "'", '"', "{", "}", '_'])
    exp = '{NULL,",","\\\\","\'","\\"","{","}",_}'
    assert res == exp

