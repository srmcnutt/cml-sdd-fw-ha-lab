# vendor/

Third-party code the test scripts depend on. Nothing here is part of the lab
design; it exists so `scripts/trex_run.py` and `scripts/run_test.py` can talk to
the TRex nodes without installing TRex on the workstation.

## trex-core/ (TRex 2.87, sparse checkout)

The TRex Python client (`scripts/automation/trex_control_plane/interactive`),
its bundled pure-Python libraries (`scripts/external_libs`), and the stock ASTF
profiles (`scripts/astf`), taken from the public TRex repository at tag
`v2.87`. The version must match the TRex image in CML, because the client and
server speak a versioned RPC.

It was produced with a blob-less partial clone and a sparse checkout, then the
`.git` directory was removed so this project can be committed as one repository:

```sh
git clone --filter=blob:none --no-checkout --depth 1 --branch v2.87 \
    https://github.com/cisco-system-traffic-generator/trex-core.git vendor/trex-core
git -C vendor/trex-core sparse-checkout set \
    scripts/astf scripts/automation/trex_control_plane/interactive scripts/external_libs
git -C vendor/trex-core checkout
rm -rf vendor/trex-core/.git
```

`vendor/trex-core/scripts/astf_schema.json` is also embedded in the TRex day-0
configs (`configs/trex/*.node.cfg`) because the CML TRex image ships without it.

## trex-ext-libs/

The TRex client loader looks for its bundled libraries in `$TREX_EXT_LIBS`.
This directory is a set of symlinks into `trex-core/scripts/external_libs`
plus a placeholder `pyzmq-ctypes/` directory that satisfies the loader; the
real `pyzmq` comes from `.venv-trex` (`requirements-trex.txt`).
