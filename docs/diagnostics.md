# Collect logs from the adapter

After the issue occurs, open Diagnostics in the panel. Copy or download the report before restarting the adapter. For a longer trace, use a USB drive.

## Prepare the USB drive

1. Use a FAT32 USB drive with at least 8 MiB of free space. Back up any files first if you need to format the drive.
2. Create an empty dongle-logs folder at the root of the drive. Keep the A15W_Update.img update file on a separate drive.
3. Eject the drive from your computer.

## Reproduce the issue

1. Plug the drive into the adapter. If the issue happens during startup, plug it in before powering up the adapter.
2. Repeat the steps that trigger the issue. If you can, note the time and what happened on your motorcycle display or phone.
3. Wait a few seconds, then remove the drive. Plugging it in again starts a new session.

## Share the session

1. Plug the drive into your computer and open dongle-logs. Find the session-… folder for your test. The adapter’s clock may be off, so check the order the folders were created in if you’re unsure.
2. Zip the entire session folder and send it privately to the developer, along with the steps you took and the time the issue occurred.

## Optional SSH session

With the supported USB Wi-Fi adapter connected, join the dongle’s own Wi-Fi and open **Debug**. In **SSH service access**, leave the developer’s public key in the field or replace it with your own Ed25519 public key. Turn the switch on only when you want the holder of that key to sign in as root. The SSH server listens on port 2223 on the diagnostic interface. Turn the switch off after the session. Restarting the dongle also turns it off.

© 2026 Overev · [overev.com](https://overev.com/)
