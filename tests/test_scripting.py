
import os
import sys
import time
import signal

import pytest

import skytools
from skytools.scripting import run_single_process

WIN32 = sys.platform == "win32"


def checklog(log, word):
    with open(log, 'r') as f:
        return word in f.read()


class Runner:
    def __init__(self, logfile, word, sleep=0):
        self.logfile = logfile
        self.word = word
        self.sleep = sleep
    def run(self):
        with open(self.logfile, "a") as f:
            f.write(self.word + "\n")
        time.sleep(self.sleep)


@pytest.mark.skipif(WIN32, reason="cannot daemonize on win32")
def test_bg_process(tmp_path):
    pidfile = str(tmp_path / "proc.pid")
    logfile = str(tmp_path / "proc.log")

    run_single_process(Runner(logfile, "STEP1"), False, pidfile)
    while skytools.signal_pidfile(pidfile, 0):
        time.sleep(1)
    assert checklog(logfile, "STEP1")

    # daemonize from other process
    pid = os.fork()
    if pid == 0:
        run_single_process(Runner(logfile, "STEP2", 10), True, pidfile)

    time.sleep(2)
    with pytest.raises(SystemExit):
        run_single_process(Runner(logfile, "STEP3"), False, pidfile)
    skytools.signal_pidfile(pidfile, signal.SIGTERM)
    while skytools.signal_pidfile(pidfile, 0):
        time.sleep(1)

    assert checklog(logfile, "STEP2")
    assert not checklog(logfile, "STEP3")

