import os
import socket
import sys

import pytest

from skytools.sockutil import set_cloexec, set_nonblocking, set_tcp_keepalive


def test_set_tcp_keepalive() -> None:
    with socket.socket() as s:
        set_tcp_keepalive(s)


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason="set_nonblocking on fd does not work on win32"
)
def test_set_nonblocking() -> None:
    with socket.socket() as s:
        assert set_nonblocking(s, None) == False
        assert set_nonblocking(s, True) == True
        assert set_nonblocking(s, None) == True


def test_set_cloexec_file() -> None:
    with open(os.devnull, 'rb') as f:
        assert set_cloexec(f, None) in (True, False)
        assert set_cloexec(f, True) == True
        assert set_cloexec(f, None) == True


def test_set_cloexec_socket() -> None:
    with socket.socket() as s:
        assert set_cloexec(s, None) in (True, False)
        assert set_cloexec(s, True) == True
        assert set_cloexec(s, None) == True

