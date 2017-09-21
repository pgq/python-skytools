
"""Nicer config class."""

from __future__ import division, absolute_import, print_function

import os
import os.path
import re
import socket

import skytools

try:
    from configparser import (      # noqa
        NoOptionError, NoSectionError, InterpolationError, InterpolationDepthError,
        Error as ConfigError, ConfigParser, MAX_INTERPOLATION_DEPTH,
        ExtendedInterpolation, Interpolation)
except ImportError:
    from ConfigParser import (      # noqa
        NoOptionError, NoSectionError, InterpolationError, InterpolationDepthError,
        Error as ConfigError, SafeConfigParser, MAX_INTERPOLATION_DEPTH)

    class Interpolation(object):
        """Define Interpolation API from Python3."""

        def before_get(self, parser, section, option, value, defaults):
            return value

        def before_set(self, parser, section, option, value):
            return value

        def before_read(self, parser, section, option, value):
            return value

        def before_write(self, parser, section, option, value):
            return value

    class ConfigParser(SafeConfigParser):
        """Default Python's ConfigParser that uses _DEFAULT_INTERPOLATION"""
        _DEFAULT_INTERPOLATION = None

        def _interpolate(self, section, option, rawval, defs):
            if self._DEFAULT_INTERPOLATION is None:
                return SafeConfigParser._interpolate(self, section, option, rawval, defs)
            return self._DEFAULT_INTERPOLATION.before_get(self, section, option, rawval, defs)


__all__ = [
    'Config',
    'NoOptionError', 'ConfigError',
    'ConfigParser', 'ExtendedConfigParser', 'ExtendedCompatConfigParser'
]

class Config(object):
    """Bit improved ConfigParser.

    Additional features:
     - Remembers section.
     - Accepts defaults in get() functions.
     - List value support.
    """
    def __init__(self, main_section, filename, sane_config=None,
                 user_defs=None, override=None, ignore_defs=False):
        """Initialize Config and read from file.
        """
        # use config file name as default job_name
        if filename:
            job_name = os.path.splitext(os.path.basename(filename))[0]
        else:
            job_name = main_section

        # initialize defaults, make them usable in config file
        if ignore_defs:
            self.defs = {}
        else:
            self.defs = {
                'job_name': job_name,
                'service_name': main_section,
                'host_name': socket.gethostname(),
            }
            if filename:
                self.defs['config_dir'] = os.path.dirname(filename)
                self.defs['config_file'] = filename
            if user_defs:
                self.defs.update(user_defs)

        self.main_section = main_section
        self.filename = filename
        self.override = override or {}
        self.cf = ConfigParser()

        if filename is None:
            self.cf.add_section(main_section)
        elif not os.path.isfile(filename):
            raise ConfigError('Config file not found: '+filename)

        self.reload()

    def reload(self):
        """Re-reads config file."""
        if self.filename:
            self.cf.read(self.filename)
        if not self.cf.has_section(self.main_section):
            raise NoSectionError(self.main_section)

        # apply default if key not set
        for k, v in self.defs.items():
            if not self.cf.has_option(self.main_section, k):
                self.cf.set(self.main_section, k, v)

        # apply overrides
        if self.override:
            for k, v in self.override.items():
                self.cf.set(self.main_section, k, v)

    def get(self, key, default=None):
        """Reads string value, if not set then default."""

        if not self.cf.has_option(self.main_section, key):
            if default is None:
                raise NoOptionError(key, self.main_section)
            return default

        return str(self.cf.get(self.main_section, key))

    def getint(self, key, default=None):
        """Reads int value, if not set then default."""

        if not self.cf.has_option(self.main_section, key):
            if default is None:
                raise NoOptionError(key, self.main_section)
            return default

        return self.cf.getint(self.main_section, key)

    def getboolean(self, key, default=None):
        """Reads boolean value, if not set then default."""

        if not self.cf.has_option(self.main_section, key):
            if default is None:
                raise NoOptionError(key, self.main_section)
            return default

        return self.cf.getboolean(self.main_section, key)

    def getfloat(self, key, default=None):
        """Reads float value, if not set then default."""

        if not self.cf.has_option(self.main_section, key):
            if default is None:
                raise NoOptionError(key, self.main_section)
            return default

        return self.cf.getfloat(self.main_section, key)

    def getlist(self, key, default=None):
        """Reads comma-separated list from key."""

        if not self.cf.has_option(self.main_section, key):
            if default is None:
                raise NoOptionError(key, self.main_section)
            return default

        s = self.get(key).strip()
        res = []
        if not s:
            return res
        for v in s.split(","):
            res.append(v.strip())
        return res

    def getdict(self, key, default=None):
        """Reads key-value dict from parameter.

        Key and value are separated with ':'.  If missing,
        key itself is taken as value.
        """

        if not self.cf.has_option(self.main_section, key):
            if default is None:
                raise NoOptionError(key, self.main_section)
            return default

        s = self.get(key).strip()
        res = {}
        if not s:
            return res
        for kv in s.split(","):
            tmp = kv.split(':', 1)
            if len(tmp) > 1:
                k = tmp[0].strip()
                v = tmp[1].strip()
            else:
                k = kv.strip()
                v = k
            res[k] = v
        return res

    def getfile(self, key, default=None):
        """Reads filename from config.

        In addition to reading string value, expands ~ to user directory.
        """
        fn = self.get(key, default)
        if fn == "" or fn == "-":
            return fn
        # simulate that the cwd is script location
        #path = os.path.dirname(sys.argv[0])
        #  seems bad idea, cwd should be cwd

        fn = os.path.expanduser(fn)

        return fn

    def getbytes(self, key, default=None):
        """Reads a size value in human format, if not set then default.

        Examples: 1, 2 B, 3K, 4 MB
        """

        if not self.cf.has_option(self.main_section, key):
            if default is None:
                raise NoOptionError(key, self.main_section)
            s = default
        else:
            s = self.cf.get(self.main_section, key)

        return skytools.hsize_to_bytes(s)

    def get_wildcard(self, key, values=(), default=None):
        """Reads a wildcard property from conf and returns its string value, if not set then default."""

        orig_key = key
        keys = [key]

        for wild in values:
            key = key.replace('*', wild, 1)
            keys.append(key)
        keys.reverse()

        for k in keys:
            if self.cf.has_option(self.main_section, k):
                return self.cf.get(self.main_section, k)

        if default is None:
            raise NoOptionError(orig_key, self.main_section)
        return default

    def sections(self):
        """Returns list of sections in config file, excluding DEFAULT."""
        return self.cf.sections()

    def has_section(self, section):
        """Checks if section is present in config file, excluding DEFAULT."""
        return self.cf.has_section(section)

    def clone(self, main_section):
        """Return new Config() instance with new main section on same config file."""
        return Config(main_section, self.filename)

    def options(self):
        """Return list of options in main section."""
        return self.cf.options(self.main_section)

    def has_option(self, opt):
        """Checks if option exists in main section."""
        return self.cf.has_option(self.main_section, opt)

    def items(self):
        """Returns list of (name, value) for each option in main section."""
        return self.cf.items(self.main_section)

    # define some aliases (short-cuts / backward compatibility cruft)
    getbool = getboolean



class ExtendedInterpolationCompat(Interpolation):
    _EXT_VAR_RX = r'\$\$|\$\{[^(){}]+\}'
    _OLD_VAR_RX = r'%%|%\([^(){}]+\)s'
    _var_rc = re.compile('(%s|%s)' % (_EXT_VAR_RX, _OLD_VAR_RX))
    _bad_rc = re.compile('[%$]')

    def before_get(self, parser, section, option, rawval, defaults):
        dst = []
        self._interpolate_ext(dst, parser, section, option, rawval, defaults, set())
        return ''.join(dst)

    def before_set(self, parser, section, option, value):
        sub = self._var_rc.sub('', value)
        if self._bad_rc.search(sub):
            raise ValueError("invalid interpolation syntax in %r" % value)
        return value

    def _interpolate_ext(self, dst, parser, section, option, rawval, defaults, loop_detect):
        if not rawval:
            return rawval

        if len(loop_detect) > MAX_INTERPOLATION_DEPTH:
            raise InterpolationDepthError(option, section, rawval)

        xloop = (section, option)
        if xloop in loop_detect:
            raise InterpolationError(section, option, 'Loop detected: %r in %r' % (xloop, loop_detect))
        loop_detect.add(xloop)

        parts = self._var_rc.split(rawval)
        for i, frag in enumerate(parts):
            fullkey = None
            use_vars = defaults
            if i % 2 == 0:
                dst.append(frag)
                continue
            if frag in ('$$', '%%'):
                dst.append(frag[0])
                continue
            if frag.startswith('${') and frag.endswith('}'):
                fullkey = frag[2:-1]

                # use section access only for new-style keys
                if ':' in fullkey:
                    ksect, key = fullkey.split(':', 1)
                    use_vars = None
                else:
                    ksect, key = section, fullkey
            elif frag.startswith('%(') and frag.endswith(')s'):
                fullkey = frag[2:-2]
                ksect, key = section, fullkey
            else:
                raise InterpolationError(section, option, 'Internal parse error: %r' % frag)

            key = parser.optionxform(key)
            newpart = parser.get(ksect, key, raw=True, vars=use_vars)
            if newpart is None:
                raise InterpolationError(ksect, key, 'Key referenced is None')
            self._interpolate_ext(dst, parser, ksect, key, newpart, defaults, loop_detect)

        loop_detect.remove(xloop)


try:
    ExtendedInterpolation
except NameError:
    class ExtendedInterpolationPy2(ExtendedInterpolationCompat):
        _var_rc = re.compile('(%s)' % ExtendedInterpolationCompat._EXT_VAR_RX)
        _bad_rc = re.compile('[$]')
    ExtendedInterpolation = ExtendedInterpolationPy2


class ExtendedConfigParser(ConfigParser):
    """ConfigParser that uses Python3-style extended interpolation by default.

    Syntax: ${var} and ${section:var}
    """
    _DEFAULT_INTERPOLATION = ExtendedInterpolation()


class ExtendedCompatConfigParser(ExtendedConfigParser):
    r"""Support both extended "${}" syntax from python3 and old "%()s" too.

    New ${} syntax allows ${key} to refer key in same section,
    and ${sect:key} to refer key in other sections.
    """
    _DEFAULT_INTERPOLATION = ExtendedInterpolationCompat()

