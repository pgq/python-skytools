
import skytools


def test_version() -> None:
    a = skytools.natsort_key(getattr(skytools, "__version__"))
    assert a
    b = skytools.natsort_key('3.3')
    assert a >= b

