
import skytools

from nose.tools import *

def test_version():
    assert_true(skytools.natsort_key(skytools.__version__) >= skytools.natsort_key('3.3'))

