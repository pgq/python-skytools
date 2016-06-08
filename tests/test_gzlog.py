
import os
import tempfile
import gzip

from skytools.gzlog import gzip_append

from nose.tools import *

def test_gzlog():
    fd, tmpname = tempfile.mkstemp(suffix='.gz')
    os.close(fd)
    try:
        blk = b'1234567890'*100
        write_total = 0
        for i in range(5):
            gzip_append(tmpname, blk)
            write_total += len(blk)

        read_total = 0
        with gzip.open(tmpname) as rfd:
            while 1:
                blk = rfd.read(512)
                if not blk:
                    break
                read_total += len(blk)
    finally:
        os.remove(tmpname)
    eq_(read_total, write_total)

