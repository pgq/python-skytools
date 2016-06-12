"""Check if SQL keywords are up-to-date.
"""

from __future__ import division, absolute_import, print_function

import sys
import re
import os.path

import skytools.quoting

from nose.tools import *

locations = [
    "/opt/src/pgsql/postgresql/src/include/parser/kwlist.h",
    "~/src/pgsql/postgres/src/include/parser/kwlist.h",
    "~/src/pgsql/pg95/src/include/parser/kwlist.h",
    "~/src/pgsql/pg94/src/include/parser/kwlist.h",
    "~/src/pgsql/pg93/src/include/parser/kwlist.h",
    "~/src/pgsql/pg92/src/include/parser/kwlist.h",
    "~/src/pgsql/pg91/src/include/parser/kwlist.h",
    "~/src/pgsql/pg90/src/include/parser/kwlist.h",
    "~/src/pgsql/pg84/src/include/parser/kwlist.h",
    "~/src/pgsql/pg83/src/include/parser/kwlist.h",
    "/usr/include/postgresql/9.5/server/parser/kwlist.h",
    "/usr/include/postgresql/9.4/server/parser/kwlist.h",
    "/usr/include/postgresql/9.3/server/parser/kwlist.h",
    "/usr/include/postgresql/9.2/server/parser/kwlist.h",
    "/usr/include/postgresql/9.1/server/parser/kwlist.h",
]

def _load_kwlist(fn, full_map, cur_map):
    fn = os.path.expanduser(fn)
    if not os.path.isfile(fn):
        return
    data = open(fn, 'rt').read()
    rc = re.compile(r'PG_KEYWORD[(]"(.*)" , \s* \w+ , \s* (\w+) [)]', re.X)
    for kw, cat in rc.findall(data):
        full_map[kw] = cat
        if cat == 'UNRESERVED_KEYWORD':
            continue
        if cat == 'COL_NAME_KEYWORD':
            continue
        cur_map[kw] = cat

def test_kwcheck():
    """Compare keyword list in quoting.py to the one in postgres sources
    """

    kwset = set(skytools.quoting._ident_kwmap)
    full_map = {}           # all types from kwlist.h
    cur_map = {}            # only kwlist.h
    new_list = []           # missing from kwset
    obsolete_list = []      # in kwset, but not in cur_map

    for fn in locations:
        _load_kwlist(fn, full_map, cur_map)
    if not full_map:
        return

    for kw in sorted(cur_map):
        if kw not in kwset:
            new_list.append((kw, cur_map[kw]))
        kwset.add(kw)

    for k in sorted(kwset):
        if k not in full_map:
            # especially obsolete
            obsolete_list.append( (k, '!FULL') )
        elif k not in cur_map:
            # slightly obsolete
            obsolete_list.append( (k, '!CUR') )

    eq_(new_list, [])

    # here we need to keep older keywords around longer
    #eq_(obsolete_list, [])

