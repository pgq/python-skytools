
import logging

import skytools
from skytools import skylog


def test_trace_setup() -> None:
    assert skylog.TRACE < logging.DEBUG
    assert skylog.TRACE == logging.TRACE    # type: ignore
    assert logging.getLevelName(skylog.TRACE) == "TRACE"


def test_skylog() -> None:
    log = skytools.getLogger("test.skylog")
    log.trace("tracemsg")

    assert not log.isEnabledFor(logging.TRACE)  # type: ignore

