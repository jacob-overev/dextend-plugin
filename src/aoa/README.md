# Yamaha AOA module

The Yamaha AOA module is by overev.com and distributed under [GPL-2.0-only](LICENSE). Its source is in
`yamaha_aoa.c`, with the USB control request parser in `aoa_protocol.h`.

## Build and test

On a Linux host, set `CROSS_COMPILE` to the ARM GCC 4.9.4 compiler prefix and
run `sh build-module.sh /absolute/path/to/new-output`. You can supply a cached
kernel archive through `DEXTEND_KERNEL_ARCHIVE`. The recipe verifies the
archive before applying the inputs in `build-support/`.

Run `sh test.sh` for the host tests. The USB tests and their kernel substitutes
are in `tests/`. The test script also runs the ABI checker's self tests.
Use `python3 check-abi.py CANDIDATE.ko REFERENCE.ko` for an offline comparison
of module metadata and symbol CRCs.

## Kernel inputs and reference module

The build uses the public NXP kernel revision
`ad37eebd4b27a81080b655034e45521f064a7a09` with archive SHA-256
`417a92355f11a0c225cd948daa7eb21f42adca8c00c549156a5365474870f7d6`.

`kernel.config` was reconstructed from ABI observations on the test adapter.
`target.symvers` records the observed symbol CRCs. The build recipe describes
the ATH9K adjustment and checks the generated configuration against the
reference build by SHA-256. The output directory contains the generated
defines for inspection. These inputs reconstruct the build and do not
establish that all kernel structures match the test adapter.

The reference module from `2026-10-24-console-persistent-rc3` has SHA-256
`18adac8ec65cb1efec71917dc85c038a072e52689ee271b107b46e3699c45690`.
Two load/open/poll/unload cycles passed on the adapter while disconnected.
Those checks did not cover USB enumeration with the motorcycle.
