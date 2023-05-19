"""Useful functions and classes for database scripts.
"""

import argparse
import errno
import logging
import logging.config
import logging.handlers
import optparse
import os
import select
import signal
import sys
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union, Callable, Type, cast

import skytools
import skytools.skylog

from .basetypes import Connection, Runnable, Cursor, DictRow, ExecuteParams

try:
    import skytools.installer_config
    default_skylog = skytools.installer_config.skylog
except ImportError:
    default_skylog = 0


__all__ = (
    'BaseScript', 'UsageError', 'daemonize', 'DBScript',
)


class UsageError(Exception):
    """User induced error."""


#
# daemon mode
#

def daemonize() -> None:
    """Turn the process into daemon.

    Goes background and disables all i/o.
    """

    # launch new process, kill parent
    pid = os.fork()
    if pid != 0:
        os._exit(0)

    # start new session
    os.setsid()

    # stop i/o
    fd = os.open("/dev/null", os.O_RDWR)
    os.dup2(fd, 0)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    if fd > 2:
        os.close(fd)


#
# Pidfile locking+cleanup & daemonization combined
#

def run_single_process(runnable: Runnable, daemon: bool, pidfile: Optional[str]) -> None:
    """Run runnable class, possibly daemonized, locked on pidfile."""

    # check if another process is running
    if pidfile and os.path.isfile(pidfile):
        if skytools.signal_pidfile(pidfile, 0):
            print("Pidfile exists, another process running?")
            sys.exit(1)
        else:
            print("Ignoring stale pidfile")

    # daemonize if needed
    if daemon:
        daemonize()

    # clean only own pidfile
    own_pidfile = False

    try:
        if pidfile:
            data = str(os.getpid())
            skytools.write_atomic(pidfile, data)
            own_pidfile = True

        runnable.run()
    finally:
        if own_pidfile and pidfile:
            try:
                os.remove(pidfile)
            except BaseException:
                pass


#
# logging setup
#

_log_config_done: int = 0
_log_init_done: Dict[str, int] = {}


def _init_log(job_name: str, service_name: str, cf: skytools.Config, log_level: int, is_daemon: bool) -> logging.Logger:
    """Logging setup happens here."""
    global _log_config_done

    got_skylog = 0
    use_skylog = cf.getint("use_skylog", default_skylog)

    # if non-daemon, avoid skylog if script is running on console.
    # set use_skylog=2 to disable.
    if not is_daemon and use_skylog == 1:
        # pylint gets spooked by it's own stdout wrapper and refuses to shut down
        # about it.  'noqa' tells prospector to ignore all warnings here.
        if sys.stdout.isatty():   # noqa
            use_skylog = 0

    # load logging config if needed
    if use_skylog and not _log_config_done:
        # python logging.config braindamage:
        # cannot specify external classess without such hack
        logging.skylog = skytools.skylog    # type: ignore
        skytools.skylog.set_service_name(service_name, job_name)

        # load general config
        flist = cf.getlist('skylog_locations',
                           ['skylog.ini', '~/.skylog.ini', '/etc/skylog.ini'])
        for fn in flist:
            fn = os.path.expanduser(fn)
            if os.path.isfile(fn):
                defs = {'job_name': job_name, 'service_name': service_name}
                logging.config.fileConfig(fn, defs, False)
                got_skylog = 1
                break
        _log_config_done = 1
        if not got_skylog:
            sys.stderr.write("skylog.ini not found!\n")
            sys.exit(1)

    # avoid duplicate logging init for job_name
    log = logging.getLogger(job_name)
    if job_name in _log_init_done:
        return log
    _log_init_done[job_name] = 1

    # tune level on root logger
    root = logging.getLogger()
    root.setLevel(log_level)

    # compatibility: specify ini file in script config
    def_fmt = '%(asctime)s %(process)s %(levelname)s %(message)s'
    def_datefmt = ''  # None
    logfile = cf.getfile("logfile", "")
    if logfile:
        fstr = cf.get('logfmt_file', def_fmt)
        fstr_date = cf.get('logdatefmt_file', def_datefmt)
        if log_level < logging.INFO:
            fstr = cf.get('logfmt_file_verbose', fstr)
            fstr_date = cf.get('logdatefmt_file_verbose', fstr_date)
        fmt = logging.Formatter(fstr, fstr_date)
        size = cf.getint('log_size', 10 * 1024 * 1024)
        num = cf.getint('log_count', 3)
        file_hdlr = logging.handlers.RotatingFileHandler(
            logfile, 'a', size, num)
        file_hdlr.setFormatter(fmt)
        root.addHandler(file_hdlr)

    # if skylog.ini is disabled or not available, log at least to stderr
    if not got_skylog:
        fstr = cf.get('logfmt_console', def_fmt)
        fstr_date = cf.get('logdatefmt_console', def_datefmt)
        if log_level < logging.INFO:
            fstr = cf.get('logfmt_console_verbose', fstr)
            fstr_date = cf.get('logdatefmt_console_verbose', fstr_date)
        stream_hdlr = logging.StreamHandler()
        fmt = logging.Formatter(fstr, fstr_date)
        stream_hdlr.setFormatter(fmt)
        root.addHandler(stream_hdlr)

    return log


class BaseScript:
    """Base class for service scripts.

    Handles logging, daemonizing, config, errors.

    Config template::

        ## Parameters for skytools.BaseScript ##

        # how many seconds to sleep between work loops
        # if missing or 0, then instead sleeping, the script will exit
        loop_delay = 1.0

        # where to log
        logfile = ~/log/%(job_name)s.log

        # where to write pidfile
        pidfile = ~/pid/%(job_name)s.pid

        # per-process name to use in logging
        #job_name = %(config_name)s

        # whether centralized logging should be used
        # search-path [ ./skylog.ini, ~/.skylog.ini, /etc/skylog.ini ]
        #   0 - disabled
        #   1 - enabled, unless non-daemon on console (os.isatty())
        #   2 - always enabled
        #use_skylog = 0

        # where to find skylog.ini
        #skylog_locations = skylog.ini, ~/.skylog.ini, /etc/skylog.ini

        # how many seconds to sleep after catching a exception
        #exception_sleep = 20
    """
    service_name: str
    job_name: str
    cf: "skytools.Config"
    go_daemon: bool
    need_reload: bool

    cf_defaults: Dict[str, str] = {}
    pidfile: Optional[str] = None

    # >0 - sleep time if work() requests sleep
    # 0  - exit if work requests sleep
    # <0 - run work() once [same as looping=0]
    loop_delay: float = 1.0

    # 0 - run work() once
    # 1 - run work() repeatedly
    looping: int = 1

    # result from last work() call:
    #  1 - there is probably more work, don't sleep
    #  0 - no work, sleep before calling again
    # -1 - exception was thrown
    work_state: int = 1

    # setup logger here, this allows override by subclass
    log = logging.getLogger('skytools.BaseScript')

    # start time
    started: float = 0

    # set to True to use argparse
    ARGPARSE: bool = False

    def __init__(self, service_name: str, args: Sequence[str]) -> None:
        """Script setup.

        User class should override work() and optionally __init__(), startup(),
        reload(), reset(), shutdown() and init_optparse().

        NB: In case of daemon, __init__() and startup()/work()/shutdown() will be
        run in different processes.  So nothing fancy should be done in __init__().

        @param service_name: unique name for script.
            It will be also default job_name, if not specified in config.
        @param args: cmdline args (sys.argv[1:]), but can be overridden
        """
        self.service_name = service_name
        self.go_daemon = False
        self.need_reload = False
        self.exception_count = 0
        self.stat_dict: Dict[str, float] = {}
        self.log_level = logging.INFO

        # parse command line
        self.options, self.args = self.parse_args(args)

        # check args
        if self.options.version:
            self.print_version()
            sys.exit(0)
        if self.options.daemon:
            self.go_daemon = True
        if self.options.quiet:
            self.log_level = logging.WARNING
        if self.options.verbose:
            if self.options.verbose > 1:
                self.log_level = skytools.skylog.TRACE
            else:
                self.log_level = logging.DEBUG

        self.cf_override = {}
        if self.options.set:
            for a in self.options.set:
                k, v = a.split('=', 1)
                self.cf_override[k.strip()] = v.strip()

        if self.options.ini:
            self.print_ini()
            sys.exit(0)

        # read config file
        self.reload()

        # init logging
        _init_log(self.job_name, self.service_name, self.cf, self.log_level, self.go_daemon)

        # send signal, if needed
        if self.options.cmd == "kill":
            self.send_signal(signal.SIGTERM)
        elif self.options.cmd == "stop":
            self.send_signal(signal.SIGINT)
        elif self.options.cmd == "reload":
            self.send_signal(signal.SIGHUP)

    def parse_args(self, args: Sequence[str]) -> Tuple[Any, Sequence[str]]:
        if self.ARGPARSE:
            arg_parser = self.init_argparse()
            options = arg_parser.parse_args(args)
            args = getattr(options, "args", [])
            return options, args
        opt_parser = self.init_optparse()
        options2, args2 = opt_parser.parse_args(args)
        return options2, args2

    def print_version(self) -> None:
        service = self.service_name
        ver = getattr(self, '__version__', None)
        if ver:
            service += ' version %s' % ver
        print('%s, Skytools version %s' % (service, getattr(skytools, '__version__')))

    def print_ini(self) -> None:
        """Prints out ini file from doc string of the script of default for dbscript

        Used by --ini option on command line.
        """

        # current service name
        print("[%s]\n" % self.service_name)

        # walk class hierarchy
        bases = [self.__class__]
        while len(bases) > 0:
            parents = []
            for c in bases:
                for p in c.__bases__:
                    if p not in parents:
                        parents.append(p)
                doc = c.__doc__
                if doc:
                    self._print_ini_frag(doc)
            bases = parents

    def _print_ini_frag(self, doc: str) -> None:
        # use last '::' block as config template
        pos = doc and doc.rfind('::\n') or -1
        if pos < 0:
            return
        doc = doc[pos + 2:].rstrip()
        doc = skytools.dedent(doc)

        # merge overrided options into output
        for ln in doc.splitlines():
            vals = ln.split('=', 1)
            if len(vals) != 2:
                print(ln)
                continue

            k = vals[0].strip()
            v = vals[1].strip()
            if k and k[0] == '#':
                print(ln)
                k = k[1:]
                if k in self.cf_override:
                    print('%s = %s' % (k, self.cf_override[k]))
            elif k in self.cf_override:
                if v:
                    print('#' + ln)
                print('%s = %s' % (k, self.cf_override[k]))
            else:
                print(ln)

        print('')

    def load_config(self) -> skytools.Config:
        """Loads and returns skytools.Config instance.

        By default it uses first command-line argument as config
        file name.  Can be overridden.
        """

        if len(self.args) < 1:
            print("need config file, use --help for help.")
            sys.exit(1)
        conf_file = self.args[0]
        return skytools.Config(self.service_name, conf_file,
                               user_defs=self.cf_defaults,
                               override=self.cf_override)

    def init_optparse(self, parser: Optional[optparse.OptionParser] = None) -> optparse.OptionParser:
        """Initialize a OptionParser() instance that will be used to
        parse command line arguments.

        Note that it can be overridden both directions - either DBScript
        will initialize an instance and pass it to user code or user can
        initialize and then pass to DBScript.init_optparse().

        @param parser: optional OptionParser() instance,
               where DBScript should attach its own arguments.
        @return: initialized OptionParser() instance.
        """
        if parser:
            p = parser
        else:
            p = optparse.OptionParser()
            p.set_usage("%prog [options] INI")

        # generic options
        p.add_option("-q", "--quiet", action="store_true",
                     help="log only errors and warnings")
        p.add_option("-v", "--verbose", action="count",
                     help="log verbosely")
        p.add_option("-d", "--daemon", action="store_true",
                     help="go background")
        p.add_option("-V", "--version", action="store_true",
                     help="print version info and exit")
        p.add_option("", "--ini", action="store_true",
                     help="display sample ini file")
        p.add_option("", "--set", action="append",
                     help="override config setting (--set 'PARAM=VAL')")

        # control options
        g = optparse.OptionGroup(p, 'control running process')
        g.add_option("-r", "--reload",
                     action="store_const", const="reload", dest="cmd",
                     help="reload config (send SIGHUP)")
        g.add_option("-s", "--stop",
                     action="store_const", const="stop", dest="cmd",
                     help="stop program safely (send SIGINT)")
        g.add_option("-k", "--kill",
                     action="store_const", const="kill", dest="cmd",
                     help="kill program immediately (send SIGTERM)")
        p.add_option_group(g)

        return p

    def init_argparse(self, parser: Optional[argparse.ArgumentParser] = None) -> argparse.ArgumentParser:
        """Initialize a ArgumentParser() instance that will be used to
        parse command line arguments.

        Note that it can be overridden both directions - either BaseScript
        will initialize an instance and pass it to user code or user can
        initialize and then pass to BaseScript.init_optparse().

        @param parser: optional ArgumentParser() instance,
               where BaseScript should attach its own arguments.
        @return: initialized ArgumentParser() instance.
        """
        if parser:
            p = parser
        else:
            p = argparse.ArgumentParser()

        # generic options
        p.add_argument("-q", "--quiet", action="store_true",
                       help="log only errors and warnings")
        p.add_argument("-v", "--verbose", action="count",
                       help="log verbosely")
        p.add_argument("-d", "--daemon", action="store_true",
                       help="go background")
        p.add_argument("-V", "--version", action="store_true",
                       help="print version info and exit")
        p.add_argument("--ini", action="store_true",
                       help="display sample ini file")
        p.add_argument("--set", action="append",
                       help="override config setting (--set 'PARAM=VAL')")
        p.add_argument("args", nargs="*")

        # control options
        g = p.add_argument_group('control running process')
        g.add_argument("-r", "--reload",
                       action="store_const", const="reload", dest="cmd",
                       help="reload config (send SIGHUP)")
        g.add_argument("-s", "--stop",
                       action="store_const", const="stop", dest="cmd",
                       help="stop program safely (send SIGINT)")
        g.add_argument("-k", "--kill",
                       action="store_const", const="kill", dest="cmd",
                       help="kill program immediately (send SIGTERM)")

        return p

    def send_signal(self, sig: int) -> None:
        if not self.pidfile:
            self.log.warning("No pidfile in config, nothing to do")
        elif os.path.isfile(self.pidfile):
            alive = skytools.signal_pidfile(self.pidfile, sig)
            if not alive:
                self.log.warning("pidfile exists, but process not running")
        else:
            self.log.warning("No pidfile, process not running")
        sys.exit(0)

    def set_single_loop(self, do_single_loop: int) -> None:
        """Changes whether the script will loop or not."""
        if do_single_loop:
            self.looping = 0
        else:
            self.looping = 1

    def _boot_daemon(self) -> None:
        run_single_process(self, self.go_daemon, self.pidfile)

    def start(self) -> None:
        """This will launch main processing thread."""
        if self.go_daemon:
            if not self.pidfile:
                self.log.error("Daemon needs pidfile")
                sys.exit(1)
        self.run_func_safely(self._boot_daemon)

    def stop(self) -> None:
        """Safely stops processing loop."""
        self.looping = 0

    def reload(self) -> None:
        "Reload config."
        # avoid double loading on startup
        if not getattr(self, "cf", None):
            self.cf = self.load_config()
        else:
            self.cf.reload()
            self.log.info("Config reloaded")
        self.job_name = self.cf.get("job_name")
        self.pidfile = self.cf.getfile("pidfile", '')
        self.loop_delay = self.cf.getfloat("loop_delay", self.loop_delay)
        self.exception_sleep = self.cf.getfloat("exception_sleep", 20)
        self.exception_quiet = self.cf.getlist("exception_quiet", [])
        self.exception_grace = self.cf.getfloat("exception_grace", 5 * 60)
        self.exception_reset = self.cf.getfloat("exception_reset", 15 * 60)

    def hook_sighup(self, sig: int, frame: Any) -> None:
        "Internal SIGHUP handler.  Minimal code here."
        self.need_reload = True

    last_sigint: float = 0

    def hook_sigint(self, sig: int, frame: Any) -> None:
        "Internal SIGINT handler.  Minimal code here."
        self.stop()
        t = time.time()
        if t - self.last_sigint < 1:
            self.log.warning("Double ^C, fast exit")
            sys.exit(1)
        self.last_sigint = t

    def stat_get(self, key: str) -> Optional[float]:
        """Reads a stat value."""
        try:
            return self.stat_dict[key]
        except KeyError:
            return None

    def stat_put(self, key: str, value: float) -> None:
        """Sets a stat value."""
        self.stat_dict[key] = value

    def stat_increase(self, key: str, increase: float = 1) -> None:
        """Increases a stat value."""
        try:
            self.stat_dict[key] += increase
        except KeyError:
            self.stat_dict[key] = increase

    def send_stats(self) -> None:
        "Send statistics to log."

        res = []
        for k, v in self.stat_dict.items():
            res.append("%s: %s" % (k, v))

        if len(res) == 0:
            return

        logmsg = "{%s}" % ", ".join(res)
        self.log.info(logmsg)
        self.stat_dict = {}

    def reset(self) -> None:
        "Something bad happened, reset all state."
        pass

    def run(self) -> None:
        "Thread main loop."

        # run startup, safely
        self.run_func_safely(self.startup)

        while True:
            # reload config, if needed
            if self.need_reload:
                self.reload()
                self.need_reload = False

            # do some work
            work = self.run_once()

            if not self.looping or self.loop_delay < 0:
                break

            # remember work state
            if work:
                self.work_state = 1 if work > 0 else -1
            else:
                self.work_state = 0
            # should sleep?
            if not work:
                if self.loop_delay > 0:
                    self.sleep(self.loop_delay)
                    if not self.looping:
                        break
                else:
                    break

        # run shutdown, safely?
        self.shutdown()

    def run_once(self) -> int:
        state = self.run_func_safely(self.work, True)

        # send stats that was added
        self.send_stats()

        return state

    last_func_fail: Optional[float] = None

    def run_func_safely(self, func, prefer_looping:bool=False) -> int:
        "Run users work function, safely."
        try:
            r = func()
            if self.last_func_fail and time.time() > self.last_func_fail + self.exception_reset:
                self.last_func_fail = None
            # set exception count to 0 after success
            self.exception_count = 0
            return 1 if r else 0
        except UsageError as d:
            self.log.error(str(d))
            sys.exit(1)
        except MemoryError:
            try:  # complex logging may not succeed
                self.log.exception("Job %s out of memory, exiting", self.job_name)
            except MemoryError:
                self.log.fatal("Out of memory")
            sys.exit(1)
        except SystemExit as d:
            self.send_stats()
            if prefer_looping and self.looping and self.loop_delay > 0:
                self.log.info("got SystemExit(%s), exiting", str(d))
            self.reset()
            raise d
        except KeyboardInterrupt:
            self.send_stats()
            if prefer_looping and self.looping and self.loop_delay > 0:
                self.log.info("got KeyboardInterrupt, exiting")
            self.reset()
            sys.exit(1)
        except Exception as d:
            try:  # this may fail too
                self.send_stats()
            except BaseException:
                pass
            if self.last_func_fail is None:
                self.last_func_fail = time.time()
            emsg = str(d).rstrip()
            self.reset()
            self.exception_hook(d, emsg)
        # reset and sleep
        self.reset()
        if prefer_looping and self.looping and self.loop_delay > 0:
            # increase exception count & sleep
            self.exception_count += 1
            self.sleep_on_exception()
            return -1
        sys.exit(1)

    def sleep(self, secs: float) -> None:
        """Make script sleep for some amount of time."""
        try:
            time.sleep(secs)
        except IOError as ex:
            if ex.errno != errno.EINTR:
                raise

    def sleep_on_exception(self) -> None:
        """Make script sleep for some amount of time when an exception occurs.

        To implement more advance exception sleeping like exponential backoff you
        can override this method. Also note that you can use self.exception_count
        to track the number of consecutive exceptions.
        """
        self.sleep(self.exception_sleep)

    def _is_quiet_exception(self, ex: Exception) -> bool:
        if "ALL" in self.exception_quiet or ex.__class__.__name__ in self.exception_quiet:
            if self.last_func_fail and time.time() < self.last_func_fail + self.exception_grace:
                return True
        return False

    def exception_hook(self, det: Exception, emsg: str) -> None:
        """Called on after exception processing.

        Can do additional logging.

        @param det: exception details
        @param emsg: exception msg
        """
        lm = "Job %s crashed: %s" % (self.job_name, emsg)
        if self._is_quiet_exception(det):
            self.log.warning(lm)
        else:
            self.log.exception(lm)

    def work(self) -> Optional[int]:
        """Here should user's processing happen.

        Return value is taken as boolean - if true, the next loop
        starts immediately.  If false, DBScript sleeps for a loop_delay.
        """
        raise Exception("Nothing implemented?")

    def startup(self) -> None:
        """Will be called just before entering main loop.

        In case of daemon, if will be called in same process as work(),
        unlike __init__().
        """
        self.started = time.time()

        # set signals
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, self.hook_sighup)
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, self.hook_sigint)

    def shutdown(self) -> None:
        """Will be called just after exiting main loop.

        In case of daemon, if will be called in same process as work(),
        unlike __init__().
        """
        pass

    # define some aliases (short-cuts / backward compatibility cruft)
    stat_add = stat_put                 # Old, deprecated function.
    stat_inc = stat_increase


##
##  DBScript
##

#: how old connections need to be closed
DEF_CONN_AGE = 20 * 60  # 20 min


class DBScript(BaseScript):
    """Base class for database scripts.

    Handles database connection state.

    Config template::

        ## Parameters for skytools.DBScript ##

        # default lifetime for database connections (in seconds)
        #connection_lifetime = 1200
    """

    db_cache: Dict[str, "DBCachedConn"]
    _db_defaults: Dict[str, Mapping[str, int]]
    _listen_map: Dict[str, List[str]]

    def __init__(self, service_name: str, args: Sequence[str]) -> None:
        """Script setup.

        User class should override work() and optionally __init__(), startup(),
        reload(), reset() and init_optparse().

        NB: in case of daemon, the __init__() and startup()/work() will be
        run in different processes.  So nothing fancy should be done in __init__().

        @param service_name: unique name for script.
            It will be also default job_name, if not specified in config.
        @param args: cmdline args (sys.argv[1:]), but can be overridden
        """
        self.db_cache: Dict = {}
        self._db_defaults = {}
        self._listen_map = {}  # dbname: channel_list
        super().__init__(service_name, args)

    def connection_hook(self, dbname: str, conn: Connection) -> None:
        pass

    def set_database_defaults(self, dbname: str, **kwargs: int) -> None:
        self._db_defaults[dbname] = kwargs

    def add_connect_string_profile(self, connstr: str, profile: Optional[str]) -> str:
        """Add extra profile info to connect string.
        """
        if profile:
            extra = self.cf.get("%s_extra_connstr" % profile, '')
            if extra:
                connstr += ' ' + extra
        return connstr

    def get_database(self, dbname: str, autocommit: int = 0, isolation_level: int = -1,
            cache: Optional[str] = None, connstr: Optional[str] = None,
            profile: Optional[str] = None) -> Connection:
        """Load cached database connection.

        User must not store it permanently somewhere,
        as all connections will be invalidated on reset.
        """

        max_age = self.cf.getint('connection_lifetime', DEF_CONN_AGE)

        if not cache:
            cache = dbname

        params: Dict[str, int] = {}
        defs = self._db_defaults.get(cache, {})
        for k in defs:
            params[k] = defs[k]
        if isolation_level >= 0:
            params['isolation_level'] = isolation_level
        elif autocommit:
            params['isolation_level'] = 0
        elif params.get('autocommit', 0):
            params['isolation_level'] = 0
        elif 'isolation_level' not in params:
            params['isolation_level'] = skytools.I_READ_COMMITTED

        if 'max_age' not in params:
            params['max_age'] = max_age

        if cache in self.db_cache:
            dbc = self.db_cache[cache]
            if connstr is None:
                connstr = self.cf.get(dbname, '')
            if connstr:
                connstr = self.add_connect_string_profile(connstr, profile)
                dbc.check_connstr(connstr)
        else:
            if not connstr:
                connstr = self.cf.get(dbname)
            connstr = self.add_connect_string_profile(connstr, profile)

            # connstr might contain password, it is not a good idea to log it
            filtered_connstr = connstr
            pos = connstr.lower().find('password')
            if pos >= 0:
                filtered_connstr = connstr[:pos] + ' [...]'

            self.log.debug("Connect '%s' to '%s'", cache, filtered_connstr)
            dbc = DBCachedConn(cache, connstr, params['max_age'], setup_func=self.connection_hook)
            self.db_cache[cache] = dbc

        clist = []
        if cache in self._listen_map:
            clist = self._listen_map[cache]

        return dbc.get_connection(params['isolation_level'], clist)

    def close_database(self, dbname: str) -> None:
        """Explicitly close a cached connection.

        Next call to get_database() will reconnect.
        """
        if dbname in self.db_cache:
            dbc = self.db_cache[dbname]
            dbc.reset()
            del self.db_cache[dbname]

    def reset(self) -> None:
        "Something bad happened, reset all connections."
        for dbc in self.db_cache.values():
            dbc.reset()
        self.db_cache = {}
        super().reset()

    def run_once(self) -> int:
        state = super().run_once()

        # reconnect if needed
        for dbc in self.db_cache.values():
            dbc.refresh()

        return state

    def exception_hook(self, det: Exception, emsg: str) -> None:
        """Log database and query details from exception."""
        curs = getattr(det, 'cursor', None)
        conn = getattr(curs, 'connection', None)
        if conn:
            # db connection
            sql = getattr(curs, 'query', None) or '?'
            if isinstance(sql, bytes):
                sql = sql.decode('utf8')
            if len(sql) > 200:  # avoid logging londiste huge batched queries
                sql = sql[:60] + " ..."
            lm = "Job %s got error on connection: %s.   Query: %s" % (
                self.job_name, emsg, sql)
            if self._is_quiet_exception(det):
                self.log.warning(lm)
            else:
                self.log.exception(lm)
        else:
            super().exception_hook(det, emsg)

    def sleep(self, secs: float) -> None:
        """Make script sleep for some amount of time."""
        fdlist = []
        for dbname in self._listen_map:
            if dbname not in self.db_cache:
                continue
            fd = self.db_cache[dbname].fileno()
            if fd is None:
                continue
            fdlist.append(fd)

        if not fdlist:
            return super().sleep(secs)

        try:
            if hasattr(select, 'poll'):
                p = select.poll()
                for fd in fdlist:
                    p.register(fd, select.POLLIN)
                p.poll(int(secs * 1000))
            else:
                select.select(fdlist, [], [], secs)
        except select.error:
            self.log.info('wait canceled')
        return None

    def _exec_cmd(self, curs: Cursor, sql: str, args: ExecuteParams, quiet: bool = False, prefix: Optional[str] = None) -> Tuple[bool, Sequence[DictRow]]:
        """Internal tool: Run SQL on cursor."""
        if self.options.verbose:
            self.log.debug("exec_cmd: %s", skytools.quote_statement(sql, args))

        _pfx = ""
        if prefix:
            _pfx = "[%s] " % prefix
        curs.execute(sql, args)
        ok = True
        rows = curs.fetchall()
        for row in rows:
            try:
                code = row['ret_code']
                msg = row['ret_note']
            except KeyError:
                self.log.error("Query does not conform to exec_cmd API:")
                self.log.error("SQL: %s", skytools.quote_statement(sql, args))
                self.log.error("Row: %s", repr(dict(row.items())))
                sys.exit(1)
            level = code // 100
            if level == 1:
                self.log.debug("%s%d %s", _pfx, code, msg)
            elif level == 2:
                if quiet:
                    self.log.debug("%s%d %s", _pfx, code, msg)
                else:
                    self.log.info("%s%s", _pfx, msg)
            elif level == 3:
                self.log.warning("%s%s", _pfx, msg)
            else:
                self.log.error("%s%s", _pfx, msg)
                self.log.debug("Query was: %s", skytools.quote_statement(sql, args))
                ok = False
        return (ok, rows)

    def _exec_cmd_many(self, curs: Cursor, sql: str, baseargs: List[Any], extra_list: Sequence[Any], quiet:bool=False, prefix:Optional[str]=None) -> Tuple[bool, Sequence[DictRow]]:
        """Internal tool: Run SQL on cursor multiple times."""
        ok = True
        rows: List[DictRow] = []
        for a in extra_list:
            (tmp_ok, tmp_rows) = self._exec_cmd(curs, sql, baseargs + [a], quiet, prefix)
            if not tmp_ok:
                ok = False
            rows += tmp_rows
        return (ok, rows)

    def exec_cmd(self, db_or_curs: Union[Connection, Cursor], q: str, args: ExecuteParams,
            commit: bool = True, quiet: bool = False, prefix: Optional[str] = None) -> Sequence[DictRow]:
        """Run SQL on db with code/value error handling."""

        db: Optional[Connection]
        curs: Cursor

        if hasattr(db_or_curs, 'cursor'):
            db = cast(Connection, db_or_curs)
            curs = db.cursor()
        else:
            db = None
            curs = cast(Cursor, db_or_curs)
        (ok, rows) = self._exec_cmd(curs, q, args, quiet, prefix)
        if ok:
            if commit and db:
                db.commit()
            return rows
        else:
            if db:
                db.rollback()
            if self.options.verbose:
                raise Exception("db error")
            # error is already logged
            sys.exit(1)

    def exec_cmd_many(self, db_or_curs: Union[Connection, Cursor], sql: str, baseargs: List[Any], extra_list: Sequence[Any],
            commit: bool = True, quiet: bool = False, prefix: Optional[str] = None) -> Sequence[DictRow]:
        """Run SQL on db multiple times."""
        if hasattr(db_or_curs, 'cursor'):
            db = cast(Connection, db_or_curs)
            curs = db.cursor()
        else:
            db = None
            curs = cast(Cursor, db_or_curs)
        (ok, rows) = self._exec_cmd_many(curs, sql, baseargs, extra_list, quiet, prefix)
        if ok:
            if commit and db:
                db.commit()
            return rows
        else:
            if db:
                db.rollback()
            if self.options.verbose:
                raise Exception("db error")
            # error is already logged
            sys.exit(1)

    def execute_with_retry(self, dbname: str, stmt: str, args: List[Any], exceptions: Optional[Sequence[Type[Exception]]] = None) -> Tuple[int, Cursor]:
        """ Execute SQL and retry if it fails.
        Return number of retries and current valid cursor, or raise an exception.
        """
        sql_retry = self.cf.getbool("sql_retry", False)
        sql_retry_max_count = self.cf.getint("sql_retry_max_count", 10)
        sql_retry_max_time = self.cf.getint("sql_retry_max_time", 300)
        sql_retry_formula_a = self.cf.getint("sql_retry_formula_a", 1)
        sql_retry_formula_b = self.cf.getint("sql_retry_formula_b", 5)
        sql_retry_formula_cap = self.cf.getint("sql_retry_formula_cap", 60)
        elist = tuple(exceptions) if exceptions else ()
        stime = time.time()
        tried = 0
        dbc: Optional[DBCachedConn] = None
        while True:
            try:
                if dbc is None:
                    if dbname not in self.db_cache:
                        self.get_database(dbname, autocommit=1)
                    dbc = self.db_cache[dbname]
                    if dbc.isolation_level != skytools.I_AUTOCOMMIT:
                        raise skytools.UsageError("execute_with_retry: autocommit required")
                else:
                    dbc.reset()
                curs = dbc.get_connection(dbc.isolation_level).cursor()
                curs.execute(stmt, args)
                break
            except elist as e:
                if not sql_retry or tried >= sql_retry_max_count or time.time() - stime >= sql_retry_max_time:
                    raise
                self.log.info("Job %s got error on connection %s: %s", self.job_name, dbname, e)
            except BaseException:
                raise
            # y = a + bx , apply cap
            y = sql_retry_formula_a + sql_retry_formula_b * tried
            if sql_retry_formula_cap is not None and y > sql_retry_formula_cap:
                y = sql_retry_formula_cap
            tried += 1
            self.log.info("Retry #%i in %i seconds ...", tried, y)
            self.sleep(y)
        return tried, curs

    def listen(self, dbname: str, channel: str) -> None:
        """Make connection listen for specific event channel.

        Listening will be activated on next .get_database() call.

        Basically this means that DBScript.sleep() will poll for events
        on that db connection, so when event appears, script will be
        woken up.
        """
        if dbname not in self._listen_map:
            self._listen_map[dbname] = []
        clist = self._listen_map[dbname]
        if channel not in clist:
            clist.append(channel)

    def unlisten(self, dbname: str, channel: str = '*') -> None:
        """Stop connection for listening on specific event channel.

        Listening will stop on next .get_database() call.
        """
        if dbname not in self._listen_map:
            return
        if channel == '*':
            del self._listen_map[dbname]
            return
        clist = self._listen_map[dbname]
        try:
            clist.remove(channel)
        except ValueError:
            pass


SetupFunc = Callable[[str, Connection], None]


class DBCachedConn:
    """Cache a db connection."""

    name: str
    loc: str
    conn: Optional[Connection]
    conn_time: float
    max_age: int
    isolation_level: int
    verbose: bool
    setup_func: Optional[SetupFunc]
    listen_channel_list: Sequence[str]

    def __init__(self, name: str, loc: str, max_age:int=DEF_CONN_AGE, verbose:bool=False, setup_func: Optional[SetupFunc] = None, channels: Sequence[str] = ()) -> None:
        self.name = name
        self.loc = loc
        self.conn = None
        self.conn_time = 0
        self.max_age = max_age
        self.isolation_level = -1
        self.verbose = verbose
        self.setup_func = setup_func
        self.listen_channel_list = []

    def fileno(self) -> Optional[int]:
        if not self.conn:
            return None
        return self.conn.cursor().fileno()

    def get_connection(self, isolation_level:int=-1, listen_channel_list: Sequence[str]=()) -> Connection:

        # default isolation_level is READ COMMITTED
        if isolation_level < 0:
            isolation_level = skytools.I_READ_COMMITTED

        # new conn?
        if not self.conn:
            self.isolation_level = isolation_level
            conn = skytools.connect_database(self.loc)
            conn = skytools.connect_database(self.loc)
            conn.set_isolation_level(isolation_level)

            self.conn = conn
            self.conn_time = time.time()
            if self.setup_func:
                self.setup_func(self.name, conn)
        else:
            if self.isolation_level != isolation_level:
                raise Exception("Conflict in isolation_level")
            conn = self.conn

        self._sync_listen(listen_channel_list)

        # done
        return conn

    def _sync_listen(self, new_clist: Sequence[str]) -> None:
        if not new_clist and not self.listen_channel_list:
            return
        if not self.conn:
            return
        curs = self.conn.cursor()
        for ch in self.listen_channel_list:
            if ch not in new_clist:
                curs.execute("UNLISTEN %s" % skytools.quote_ident(ch))
        for ch in new_clist:
            if ch not in self.listen_channel_list:
                curs.execute("LISTEN %s" % skytools.quote_ident(ch))
        if self.isolation_level != skytools.I_AUTOCOMMIT:
            self.conn.commit()
        self.listen_channel_list = new_clist[:]

    def refresh(self) -> None:
        if not self.conn:
            return
        #for row in self.conn.notifies():
        #    if row[0].lower() == "reload":
        #        self.reset()
        #        return
        if not self.max_age:
            return
        if time.time() - self.conn_time >= self.max_age:
            self.reset()

    def reset(self) -> None:
        if not self.conn:
            return

        # drop reference
        conn = self.conn
        self.conn = None
        self.listen_channel_list = []

        # close
        try:
            conn.close()
        except BaseException:
            pass

    def check_connstr(self, connstr: str) -> None:
        """Drop connection if connect string has changed.
        """
        if self.loc != connstr:
            self.reset()

