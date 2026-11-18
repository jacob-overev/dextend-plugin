# Testing a change

We run `sh tools/test.sh` from the repository root. The suite covers the protocol bridge, phone selection, recovery, installer transactions and driver ABI. Some installer tests need an external OEM fixture tree (`DEXTEND_OEM_TEST_ROOT`). When we report results, we list any skipped tests. For changes to packaging or rollback, we also [test the finished IMG](build.md).

On the motorcycle, we check video, controls and audio separately. For a restart test, we compare the boot identifier before and after. For Android Auto geometry changes, we check the map edges, navigation bar and joystick on the target display. We record the build and equipment alongside each result in [hardware compatibility](compatibility.md).

© 2026 Overev · [overev.com](https://overev.com/)
