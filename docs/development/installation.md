# Why updates start from the OEM state

An update may start on factory firmware or on an adapter with an earlier Dextend release. Installing over the old files would make the result depend on what the previous release left behind. The installer therefore uses the same starting point for both paths.

After checking the device profile and available space, the installer backs up the files it will change. If it recognizes a previous installation, it restores the OEM files and removes the old plugin settings. It verifies that state before installing the new runtime and writes the startup hook last. OEM pairings are preserved. The Restore action in the panel uses the same removal procedure.

When we add a persistent file, we update the removal procedure and check that both installation paths restore the original state. We cover these checks in the [build and rollback tests](build.md). The [USB installation guide](../installation.md) describes the steps on the adapter.

© 2026 Overev · [overev.com](https://overev.com/)
