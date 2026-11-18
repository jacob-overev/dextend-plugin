# Fitting Android Auto to the Yamaha display

We started with a centred 640×360 area inside an 800×480 H.264 stream. The phone chooses its interface layout from the content dimensions it receives. The Yamaha display shows the window described by the stream’s SPS crop. Changing only one of those settings could leave the map clipped or move the navigation bar to the side.

On the LYWW20, a 624×332 content area put the bar on the left. At 624×352 and 120 DPI, the phone kept the bottom bar. Cropping 44 pixels on the left, 76 on the right, 32 at the top and 40 at the bottom gave a 680×408 window. A rider confirmed the map edges and joystick controls on a physical LYWW20 with wireless Android Auto.

The bridge changes the H.264 crop metadata, so the adapter can forward encoded frames without decoding and re-encoding them. A comparison using synthetic streams and a phone recording matched the expected crop pixel for pixel across 306 frames. The Video tab keeps the LYWW20 settings as a preset and allows another display to use different margins. Wired Android Auto and other CCUs need their own hardware tests.

© 2026 Overev · [overev.com](https://overev.com/)
