# Updating through the browser

We started with USB installation. The browser updater uses the same signed IMG so both methods install the same release. We start a browser update from the Update tab in the adapter panel. The local page embeds the HTTPS updater and relays its requests to the receiver on the adapter. The phone needs access to both the adapter and the download site.

The receiver checks the signed manifest, sequence number, length and checksum before installation. Once started, installation continues if the page closes. The browser confirms success after the adapter restarts and reports the expected version as active. USB remains the recovery path if the web service cannot start.

© 2026 Overev · [overev.com](https://overev.com/)
