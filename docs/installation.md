# Install Dextend from a USB drive

## Check your adapter

Look up your motorcycle’s model and year in the compatibility table in the README. On the Carlinkit CPC200-CCPA / A15W, open **Box Info**. The tested hardware revision (**Hardware Version**) is `YMA0-WN16-0003`. The tested firmware versions (**Version**) are `2025.10.15.1127` and `2026.07.31.1733`. Both use the same installation image. On A15W the installer records the firmware version in its report. Other firmware versions require verification after startup. Installation preserves the owner’s `/etc/init.d/rcS` script and SSH or Telnet settings.

A power cut during installation can leave the adapter unusable. Keep a verified backup if you need to recover the original software. Recovery is not guaranteed.

## Prepare the drive

1. Download the [A15W_Update.img installation image](https://github.com/jacob-overev/dextend-plugin/releases/latest/download/A15W_Update.img). For optional verification on your computer, download the [SHA256SUMS checksum file](https://github.com/jacob-overev/dextend-plugin/releases/latest/download/SHA256SUMS).
2. To verify the downloaded image yourself, use the following commands. In the download folder on Windows, run `Get-FileHash .\A15W_Update.img -Algorithm SHA256` in PowerShell. In the same folder on macOS, run `shasum -a 256 A15W_Update.img` or, on Linux, `sha256sum A15W_Update.img`. Compare the hash with the entry in `SHA256SUMS`. Stop if they differ.
3. Back up the files on your USB drive before formatting it as FAT32. Copy just the image to the root of the drive, keep its filename and eject the drive from the computer.

## Install and check the result

1. Power the adapter from a stable USB charger off the motorcycle. Once it has started, insert the drive into its USB-A port.
2. Keep power and the drive connected throughout the update. After the manufacturer’s update indication ends, wait another four minutes. Then disconnect power, remove the drive and open `DEXTEND-RESULT.txt` on your computer. Keep the report and the `dextend-backup.*` folder.
3. Check that the report shows `operation=install` and the version you selected. `result=PREPARED_FOR_BOOT` means the installer verified the files. Start the adapter without the drive and follow the connection guide to check picture, controls and sound. `ALREADY_INSTALLED` means this version was already present.
4. If you see `REJECTED`, read the `detail` field. If the report is missing, shows an error or ends at `FILES_COMMITTED`, keep the backup and check the adapter before trying again. The LED colour alone cannot confirm installation.

© 2026 Overev · [overev.com](https://overev.com/)
