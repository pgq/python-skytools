"""Check if SQL keywords are up-to-date.
"""

from typing import Dict, List, Tuple

import os.path
import re

import skytools.quoting

versions = [
    "94", "95", "96",
    "10", "11", "12", "13", "14",
    "15", "16", "17", "18", "19"
]

locations = [
    #"/usr/include/postgresql/{VER}/server/parser/kwlist.h",
    "~/src/pgsql/pg{VER}/src/include/parser/kwlist.h",
    #"~/src/pgsql/postgresql/src/include/parser/kwlist.h",
]

known_cats = [
    "COL_NAME_KEYWORD", "UNRESERVED_KEYWORD",
    "RESERVED_KEYWORD", "TYPE_FUNC_NAME_KEYWORD",
]

def addkw(kmap: Dict[str, str], kw: str, cat: str) -> None:
    assert cat in known_cats
    if kw not in kmap:
        kmap[kw] = cat
    elif kmap[kw] != cat and cat not in kmap[kw]:
        kmap[kw] += "," + cat

def _load_kwlist(fn: str, full_map: Dict[str, str], cur_map: Dict[str, str]) -> None:
    fn = os.path.expanduser(fn)
    if not os.path.isfile(fn):
        return
    with open(fn, 'rt') as f:
        data = f.read()
    rc = re.compile(r'PG_KEYWORD[(]"(.*)" , \s* \w+ , \s* (\w+) [)]', re.X)
    for kw, cat in rc.findall(data):
        addkw(full_map, kw, cat)
        if cat == 'UNRESERVED_KEYWORD':
            continue
        #if cat == 'COL_NAME_KEYWORD':
        #    continue
        addkw(cur_map, kw, cat)


def test_kwcheck() -> None:
    """Compare keyword list in quoting.py to the one in postgres sources
    """

    kwset = set(skytools.quoting._ident_kwmap)
    full_map: Dict[str, str] = {}           # all types from kwlist.h
    cur_map: Dict[str, str] = {}            # only kwlist.h
    new_list: List[Tuple[str, str]] = []           # missing from kwset
    obsolete_list: List[Tuple[str, str]] = []      # in kwset, but not in cur_map

    done = set()
    for loc in locations:
        for ver in versions:
            fn = loc.format(VER=ver)
            if fn not in done:
                _load_kwlist(fn, full_map, cur_map)
                done.add(fn)

    if not full_map:
        return

    for kw in sorted(cur_map):
        if kw not in kwset:
            new_list.append((kw, cur_map[kw]))
        kwset.add(kw)

    for k in sorted(kwset):
        if k not in full_map:
            # especially obsolete
            obsolete_list.append((k, '!FULL'))
        elif k not in cur_map:
            # slightly obsolete
            obsolete_list.append((k, '!CUR'))

    assert new_list == []

    # here we need to keep older keywords around longer
    #assert obsolete_list == []

