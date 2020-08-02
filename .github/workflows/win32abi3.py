#! /usr/bin/env python3

"""
Convert windows wheel to abi3-like multi-python wheel.

This is a workaround for missing win32-abi3 support in pip/wheel/bdist_wheel.

Requirements:
- extensions must be compiled as abi3 compatible.
- python 3.5+, older don't have stable libc abi.
"""

import argparse
import base64
import hashlib
import os
import os.path
import re
import sys
import zipfile

#from wheel.wheelfile import WheelFile, WHEEL_INFO_RE


RC_FN = re.compile(r"""
    ^ (?P<namever>
        (?P<name> .+? ) - (?P<ver> \d [^-]* )
      )
      (?P<build> - \d [^-]* )?
    - (?P<pyver>[a-z][^-]*)
    - (?P<abi>[a-z][a-z0-9]+)
    - (?P<arch>[a-z][a-z0-9_]+)
    [.]whl $
""", re.X)

_quiet = False
_verbose = False


def writemsg(fd, msg, args):
    if args:
        msg = msg % args
    fd.write(msg + "\n")
    fd.flush()


def printf(msg, *args):
    if not _quiet:
        writemsg(sys.stdout, msg, args)


def dprintf(msg, *args):
    if _verbose:
        writemsg(sys.stdout, msg, args)


def eprintf(msg, *args):
    writemsg(sys.stderr, msg, args)


def die(msg, *args):
    eprintf(msg, *args)
    sys.exit(1)


def convert_filename(fn, pyvers):
    m = RC_FN.match(fn)
    if not m:
        die("Unsupported wheel name: %s", fn)
    namever = m.group("namever")
    build = m.group("build") or ""
    abi = m.group("abi")
    arch = m.group("arch")
    if arch.startswith("win"):
        abi = "none"  # should be "abi3"
    newtag = "%s-%s-%s" % (pyvers, abi, arch)
    fn2 = "%s%s-%s.whl" % (namever, build, newtag)
    return fn2, namever, newtag


def convert_tags(wheeldata, newtag):
    res = []
    for ln in wheeldata.decode().split("\n"):
        if ln.startswith("Tag:"):
            res.append("Tag: %s" % newtag)
        else:
            res.append(ln)
    return "\n".join(res).encode()


def digest(data):
    md = hashlib.sha256(data).digest()
    b64 = base64.urlsafe_b64encode(md).decode()
    return "sha256=" + b64.strip("=")


def convert_record(data, wheeldata):
    res = []
    for ln in data.decode().split("\n"):
        parts = ln.split(",")
        if len(parts) != 3:
            res.append(ln)
            continue
        elif parts[0].endswith("WHEEL"):
            ln2 = "%s,%s,%s" % (parts[0], digest(wheeldata), len(wheeldata))
            res.append(ln2)
        else:
            res.append(ln)
    return "\n".join(res).encode()


def convert_wheel(srcwheel, dstwheel, namever, newtag):
    recordfn = "%s.dist-info/RECORD" % namever
    wheelfn = "%s.dist-info/WHEEL" % namever

    printf("Creating %s", dstwheel)
    wheel = None
    record = None
    with zipfile.ZipFile(srcwheel, "r") as zsrc:
        wheel = convert_tags(zsrc.read(wheelfn), newtag)
        if not wheel:
            die("WHEEL entry not found")
        with zipfile.ZipFile(dstwheel, "w") as zdst:
            for info in zsrc.infolist():
                if info.is_dir():
                    continue
                filename = info.filename.replace("\\", "/")
                info2 = zipfile.ZipInfo(filename=filename, date_time=info.date_time)
                info2.compress_type = zipfile.ZIP_DEFLATED
                if filename == wheelfn:
                    dprintf("  Converting %s", filename)
                    zdst.writestr(info2, wheel)
                elif filename == recordfn:
                    dprintf("  Converting %s", filename)
                    record = convert_record(zsrc.read(info), wheel)
                    zdst.writestr(info2, record)
                else:
                    dprintf("  Copying %s", filename)
                    zdst.writestr(info2, zsrc.read(info))
    if not record:
        die("RECORD entry not found")


def main(argv=None):
    """Convert win32/64 wheels to be abi3-like.
    """
    global _verbose, _quiet
    p = argparse.ArgumentParser(
        description=main.__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("wheel", metavar="WHEEL", nargs="+", help="Wheels to convert")
    p.add_argument("-d", dest="dest", help="target dir", default=".")
    p.add_argument("-p", dest="pyvers", help="python versions", default="cp36.cp37.cp38")
    p.add_argument("-q", dest="quiet", help="no info messages", action="store_true")
    p.add_argument("-v", dest="verbose", help="debug messages", action="store_true")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    if args.quiet:
        _quiet = True
    elif args.verbose:
        _verbose = True

    os.makedirs(args.dest, exist_ok=True)

    for fn in args.wheel:
        srcfn = os.path.basename(fn)
        dstfn, namever, newtag = convert_filename(srcfn, args.pyvers)
        fn2 = os.path.join(args.dest, dstfn)
        convert_wheel(fn, fn2, namever, newtag)


if __name__ == "__main__":
    main()

