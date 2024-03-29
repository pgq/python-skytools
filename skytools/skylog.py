"""Our log handlers for Python's logging package.
"""

import logging
import logging.handlers
import os
import socket
import time
from logging import LoggerAdapter
from typing import Any, Dict, Optional, Union

import skytools
import skytools.tnetstrings
from skytools.basetypes import Buffer

__all__ = ['getLogger']

# add TRACE level
TRACE = 5
logging.TRACE = TRACE   # type: ignore
logging.addLevelName(TRACE, 'TRACE')

# extra info to be added to each log record
_service_name = 'unknown_svc'
_job_name = 'unknown_job'
_hostname = socket.gethostname()
try:
    _hostaddr = socket.gethostbyname(_hostname)
except BaseException:
    _hostaddr = "0.0.0.0"
_log_extra = {
    'job_name': _job_name,
    'service_name': _service_name,
    'hostname': _hostname,
    'hostaddr': _hostaddr,
}


def set_service_name(service_name: str, job_name: str) -> None:
    """Set info about current script."""
    global _service_name, _job_name

    _service_name = service_name
    _job_name = job_name

    _log_extra['job_name'] = _job_name
    _log_extra['service_name'] = _service_name


# Make extra fields available to all log records
_old_factory = logging.getLogRecordFactory()


def _new_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _old_factory(*args, **kwargs)
    record.__dict__.update(_log_extra)
    return record


logging.setLogRecordFactory(_new_factory)


# configurable file logger
class EasyRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Easier setup for RotatingFileHandler."""
    def __init__(self, filename: str, maxBytes: int = 10 * 1024 * 1024, backupCount: int = 3) -> None:
        """Args same as for RotatingFileHandler, but in filename '~' is expanded."""
        fn = os.path.expanduser(filename)
        super().__init__(fn, maxBytes=maxBytes, backupCount=backupCount)


# send JSON message over UDP
class UdpLogServerHandler(logging.handlers.DatagramHandler):
    """Sends log records over UDP to logserver in JSON format."""

    # map logging levels to logserver levels
    _level_map = {
        logging.DEBUG: 'DEBUG',
        logging.INFO: 'INFO',
        logging.WARNING: 'WARN',
        logging.ERROR: 'ERROR',
        logging.CRITICAL: 'FATAL',
    }

    # JSON message template
    _log_template = '{\n\t'\
        '"logger": "skytools.UdpLogServer",\n\t'\
        '"timestamp": %.0f,\n\t'\
        '"level": "%s",\n\t'\
        '"thread": null,\n\t'\
        '"message": %s,\n\t'\
        '"properties": {"application":"%s", "apptype": "%s", "type": "sys", "hostname":"%s", "hostaddr": "%s"}\n'\
        '}\n'

    # cut longer msgs
    MAXMSG = 1024

    def makePickle(self, record: logging.LogRecord) -> bytes:
        """Create message in JSON format."""
        # get & cut msg
        msg = self.format(record)
        if len(msg) > self.MAXMSG:
            msg = msg[:self.MAXMSG]
        txt_level = self._level_map.get(record.levelno, "ERROR")
        hostname = _hostname
        hostaddr = _hostaddr
        jobname = _job_name
        svcname = _service_name
        pkt = self._log_template % (
            time.time() * 1000, txt_level, skytools.quote_json(msg),
            jobname, svcname, hostname, hostaddr
        )
        return pkt.encode("utf8")

    def send(self, s: Buffer) -> None:
        """Disable socket caching."""
        sock = self.makeSocket()
        sock.sendto(s, (self.host, self.port))
        sock.close()


# send TNetStrings message over UDP
class UdpTNetStringsHandler(logging.handlers.DatagramHandler):
    """ Sends log records in TNetStrings format over UDP. """

    # LogRecord fields to send
    send_fields = [
        'created', 'exc_text', 'levelname', 'levelno', 'message', 'msecs', 'name',
        'hostaddr', 'hostname', 'job_name', 'service_name']

    _udp_reset: float = 0

    def makePickle(self, record: logging.LogRecord) -> bytes:
        """ Create message in TNetStrings format.
        """
        msg = {}
        self.format(record)  # render 'message' attribute and others
        for k in self.send_fields:
            msg[k] = record.__dict__[k]
        tnetstr = skytools.tnetstrings.dumps(msg)
        return tnetstr

    def send(self, s: Buffer) -> None:
        """ Cache socket for a moment, then recreate it.
        """
        now = time.time()
        if now - 1 > self._udp_reset:
            if self.sock:
                self.sock.close()
            self.sock = self.makeSocket()
            self._udp_reset = now
        if self.sock:
            self.sock.sendto(s, (self.host, self.port))


class LogDBHandler(logging.handlers.SocketHandler):
    """Sends log records into PostgreSQL server.

    Additionally, does some statistics aggregating,
    to avoid overloading log server.

    It subclasses SocketHandler to get throtthling for
    failed connections.
    """

    # map codes to string
    _level_map = {
        logging.DEBUG: 'DEBUG',
        logging.INFO: 'INFO',
        logging.WARNING: 'WARNING',
        logging.ERROR: 'ERROR',
        logging.CRITICAL: 'FATAL',
    }

    sock: Any
    closeOnError: bool
    connect_string: str
    stat_cache: Dict[str, Union[int, float]]
    stat_flush_period: float
    last_stat_flush: float

    def __init__(self, connect_string: str) -> None:
        """
        Initializes the handler with a specific connection string.
        """

        super().__init__("localhost", 1)
        self.closeOnError = True

        self.connect_string = connect_string

        self.stat_cache = {}
        self.stat_flush_period = 60
        # send first stat line immediately
        self.last_stat_flush = 0

    def createSocket(self) -> None:
        try:
            super().createSocket()
        except BaseException:
            self.sock = self.makeSocket()

    def makeSocket(self, timeout: float = 1) -> Any:
        """Create server connection.
        In this case its not socket but database connection."""

        db = skytools.connect_database(self.connect_string)
        db.set_isolation_level(0)  # autocommit
        return db

    def emit(self, record: logging.LogRecord) -> None:
        """Process log record."""

        # we do not want log debug messages
        if record.levelno < logging.INFO:
            return

        try:
            self.process_rec(record)
        except (SystemExit, KeyboardInterrupt):
            raise
        except BaseException:
            self.handleError(record)

    def process_rec(self, record: logging.LogRecord) -> None:
        """Aggregate stats if needed, and send to logdb."""
        # render msg
        msg = self.format(record)

        # dont want to send stats too ofter
        if record.levelno == logging.INFO and msg and msg[0] == "{":
            self.aggregate_stats(msg)
            if time.time() - self.last_stat_flush >= self.stat_flush_period:
                self.flush_stats(_job_name)
            return

        if record.levelno < logging.INFO:
            self.flush_stats(_job_name)

        # dont send more than one line
        ln = msg.find('\n')
        if ln > 0:
            msg = msg[:ln]

        txt_level = self._level_map.get(record.levelno, "ERROR")
        self.send_to_logdb(_job_name, txt_level, msg)

    def aggregate_stats(self, msg: str) -> None:
        """Sum stats together, to lessen load on logdb."""

        msg = msg[1:-1]
        for rec in msg.split(", "):
            k, v = rec.split(": ")
            agg = self.stat_cache.get(k, 0)
            if v.find('.') >= 0:
                agg += float(v)
            else:
                agg += int(v)
            self.stat_cache[k] = agg

    def flush_stats(self, service: str) -> None:
        """Send acquired stats to logdb."""
        res = []
        for k, v in self.stat_cache.items():
            res.append("%s: %s" % (k, str(v)))
        if len(res) > 0:
            logmsg = "{%s}" % ", ".join(res)
            self.send_to_logdb(service, "INFO", logmsg)
        self.stat_cache = {}
        self.last_stat_flush = time.time()

    def send_to_logdb(self, service: str, level: str, msg: str) -> None:
        """Actual sending is done here."""

        if self.sock is None:
            self.createSocket()

        if self.sock:
            logcur = self.sock.cursor()
            query = "select * from log.add(%s, %s, %s)"
            logcur.execute(query, [level, service, msg])


# fix unicode bug in SysLogHandler
class SysLogHandler(logging.handlers.SysLogHandler):
    """Fixes unicode bug in logging.handlers.SysLogHandler."""

    # be compatible with both 2.6 and 2.7
    socktype = socket.SOCK_DGRAM

    _udp_reset: float = 0

    def _custom_format(self, record: logging.LogRecord) -> str:
        msg = self.format(record) + '\000'

        # We need to convert record level to lowercase, maybe this will
        # change in the future.
        prio = '<%d>' % self.encodePriority(self.facility,
                                            self.mapPriority(record.levelname))
        msg = prio + msg
        return msg

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a record.

        The record is formatted, and then sent to the syslog server. If
        exception information is present, it is NOT sent to the server.
        """
        xmsg = self._custom_format(record)
        msg = xmsg if isinstance(xmsg, bytes) else xmsg.encode("utf8")

        try:
            if self.unixsocket:
                try:
                    self.socket.send(msg)   # type: ignore[has-type]
                except socket.error:
                    self._connect_unixsocket(self.address)  # type: ignore[attr-defined]
                    self.socket.send(msg)                   # type: ignore[has-type]
            elif self.socktype == socket.SOCK_DGRAM:
                now = time.time()
                if now - 1 > self._udp_reset:
                    self.socket.close()  # type: ignore[has-type]
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._udp_reset = now
                self.socket.sendto(msg, self.address)
            else:
                self.socket.sendall(msg)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            self.handleError(record)


class SysLogHostnameHandler(SysLogHandler):
    """Slightly modified standard SysLogHandler - sends also hostname and service type"""

    def _custom_format(self, record: logging.LogRecord) -> str:
        msg = self.format(record)
        format_string = '<%d> %s %s %s\000'
        msg = format_string % (self.encodePriority(self.facility, self.mapPriority(record.levelname)),
                               _hostname, _service_name, msg)
        return msg


# add missing aliases (that are in Logger class)
if not hasattr(LoggerAdapter, 'fatal'):
    LoggerAdapter.fatal = LoggerAdapter.critical    # type: ignore


class SkyLogger(LoggerAdapter):
    """Adds API to existing Logger.
    """
    def trace(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log message with severity TRACE."""
        self.log(TRACE, msg, *args, **kwargs)


def getLogger(name: Optional[str] = None, **kwargs_extra: Any) -> SkyLogger:
    """Get logger with extra functionality.

    Adds additional log levels, and extra fields to log record.

    name - name for logging.getLogger()
    kwargs_extra - extra fields to add to log record
    """
    log = logging.getLogger(name)
    return SkyLogger(log, kwargs_extra)

