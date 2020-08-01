#! /bin/sh

# will be run inside manylinux docker

set -e
set -x

PYLIST="cp36-cp36m cp37-cp37m cp38-cp38"
PYDEPS=""
DSTDIR="dist"
BLDDIR="build/${AUDITWHEEL_PLAT}"

PIPOPTS="--no-cache-dir --disable-pip-version-check"

build_wheel() {
    if test -n "${PYDEPS}"; then
        pip install ${PIPOPTS} -U ${PYDEPS}
    fi
    pip wheel ${PIPOPTS} -w "${BLDDIR}" .
}

for tag in ${PYLIST}; do
    PATH="/opt/python/${tag}/bin:${PATH}" \
    build_wheel
done

for whl in "${BLDDIR}"/*.whl; do
    auditwheel repair -w "${DSTDIR}" "${whl}"
done

