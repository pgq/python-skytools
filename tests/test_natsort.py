
from skytools.natsort import natsorted, natsorted_icase


def test_natsorted():
    res = natsorted(['ver-1.1', 'ver-1.11', '', 'ver-1.0'])
    assert res == ['', 'ver-1.0', 'ver-1.1', 'ver-1.11']


def test_natsorted_icase():
    res = natsorted_icase(['Ver-1.1', 'vEr-1.11', '', 'veR-1.0'])
    assert res == ['', 'veR-1.0', 'Ver-1.1', 'vEr-1.11']

