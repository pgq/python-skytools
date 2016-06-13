
import os.path

import io

from nose.tools import *

from skytools.config import (Config, NoOptionError, NoSectionError,
        ConfigError, InterpolationError,
        ExtendedConfigParser, ExtendedCompatConfigParser)

TOP = os.path.dirname(__file__)
CONFIG = os.path.join(TOP, 'config.ini')

def test_config_str():
    cf = Config('base', CONFIG)
    eq_(cf.get('foo'), '1')
    eq_(cf.get('missing', 'q'), 'q')
    assert_raises(NoOptionError, cf.get, 'missing')

def test_config_int():
    cf = Config('base', CONFIG)
    eq_(cf.getint('foo'), 1)
    eq_(cf.getint('missing', 2), 2)
    assert_raises(NoOptionError, cf.getint, 'missing')

def test_config_float():
    cf = Config('base', CONFIG)
    eq_(cf.getfloat('float-val'), 2.0)
    eq_(cf.getfloat('missing', 3.0), 3.0)
    assert_raises(NoOptionError, cf.getfloat, 'missing')

def test_config_bool():
    cf = Config('base', CONFIG)
    eq_(cf.getboolean('bool-true1'), True)
    eq_(cf.getboolean('bool-true2'), True)
    eq_(cf.getboolean('missing', True), True)
    assert_raises(NoOptionError, cf.getboolean, 'missing')

    eq_(cf.getboolean('bool-false1'), False)
    eq_(cf.getboolean('bool-false2'), False)
    eq_(cf.getboolean('missing', False), False)
    assert_raises(NoOptionError, cf.getbool, 'missing')

def test_config_list():
    cf = Config('base', CONFIG)
    eq_(cf.getlist('list-val1'), [])
    eq_(cf.getlist('list-val2'), ['a', '1', 'asd', 'ppp'])
    eq_(cf.getlist('missing', [1]), [1])
    assert_raises(NoOptionError, cf.getlist, 'missing')

def test_config_dict():
    cf = Config('base', CONFIG)
    eq_(cf.getdict('dict-val1'), {})
    eq_(cf.getdict('dict-val2'), {'a': '1', 'b': '2', 'z': 'z'})
    eq_(cf.getdict('missing', {'a':1}), {'a':1})
    assert_raises(NoOptionError, cf.getdict, 'missing')

def test_config_file():
    cf = Config('base', CONFIG)
    eq_(cf.getfile('file-val1'), '-')
    eq_(cf.getfile('file-val2')[0], '/')
    eq_(cf.getfile('missing', 'qwe'), 'qwe')
    assert_raises(NoOptionError, cf.getfile, 'missing')

def test_config_bytes():
    cf = Config('base', CONFIG)
    eq_(cf.getbytes('bytes-val1'), 4)
    eq_(cf.getbytes('bytes-val2'), 2048)
    eq_(cf.getbytes('missing', '3k'), 3072)
    assert_raises(NoOptionError, cf.getbytes, 'missing')

def test_config_wildcard():
    cf = Config('base', CONFIG)

    eq_(cf.get_wildcard('wild-*-*', ['a', 'b']), 'w.a.b')
    eq_(cf.get_wildcard('wild-*-*', ['a', 'x']), 'w.a')
    eq_(cf.get_wildcard('wild-*-*', ['q', 'b']), 'w2')
    eq_(cf.get_wildcard('missing-*-*', ['1', '2'], 'def'), 'def')
    assert_raises(NoOptionError, cf.get_wildcard, 'missing-*-*', ['1', '2'])

def test_config_default():
    cf = Config('base', CONFIG)
    eq_(cf.get('all'), 'yes')

def test_config_other():
    cf = Config('base', CONFIG)
    eq_(sorted(cf.sections()), ['base', 'other'])
    assert_true(cf.has_section('base'))
    assert_true(cf.has_section('other'))
    assert_false(cf.has_section('missing'))
    assert_false(cf.has_section('DEFAULT'))

    assert_false(cf.has_option('missing'))
    assert_true(cf.has_option('all'))
    assert_true(cf.has_option('foo'))

    cf2 = cf.clone('other')
    eq_(sorted(cf2.options()), ['all', 'config_dir', 'config_file',
        'host_name', 'job_name', 'service_name', 'test'])
    eq_(len(cf2.items()), len(cf2.options()))

def test_loading():
    assert_raises(NoSectionError, Config, 'random', CONFIG)
    assert_raises(ConfigError, Config, 'random', 'random.ini')

def test_nofile():
    cf = Config('base', None, user_defs = {'a': '1'})
    eq_(cf.sections(), ['base'])
    eq_(cf.get('a'), '1')

    cf = Config('base', None, user_defs = {'a': '1'}, ignore_defs=True)
    eq_(cf.get('a', '2'), '2')

def test_override():
    cf = Config('base', CONFIG, override = {'foo': 'overrided'})
    eq_(cf.get('foo'), 'overrided')

def test_vars():
    cf = Config('base', CONFIG)
    eq_(cf.get('vars1'), 'V2=V3=Q3')

    assert_raises(InterpolationError, cf.get, 'bad1')


def test_extended_compat():
    config = u'[foo]\nkey = ${sub} $${nosub}\nsub = 2\n[bar]\nkey = ${foo:key}\n'
    cf = ExtendedCompatConfigParser()
    cf.readfp(io.StringIO(config), 'conf.ini')
    eq_(cf.get('bar', 'key'), '2 ${nosub}')

    config = u'[foo]\nloop1= ${loop1}\nloop2 = ${loop3}\nloop3 = ${loop2}\n'
    cf = ExtendedCompatConfigParser()
    cf.readfp(io.StringIO(config), 'conf.ini')
    assert_raises(InterpolationError, cf.get, 'foo', 'loop1')
    assert_raises(InterpolationError, cf.get, 'foo', 'loop2')

    config = u'[foo]\nkey = %(sub)s ${sub}\nsub = 2\n[bar]\nkey = %(foo:key)s\nkey2 = ${foo:key}\n'
    cf = ExtendedCompatConfigParser()
    cf.readfp(io.StringIO(config), 'conf.ini')
    eq_(cf.get('bar', 'key2'), '2 2')
    assert_raises(NoOptionError, cf.get, 'bar', 'key')

    config = u'[foo]\nkey = ${bad:xxx}\n[bad]\nsub = 1\n'
    cf = ExtendedCompatConfigParser(); cf.readfp(io.StringIO(config), 'conf.ini')
    assert_raises(NoOptionError, cf.get, 'foo', 'key')

