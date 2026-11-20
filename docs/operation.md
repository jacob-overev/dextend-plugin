# Connect your phone and motorcycle

Do the first setup while parked.

## Connect the adapter

1. Remove the USB drive. Plug the adapter into the motorcycle infotainment system’s USB port and turn on the display.
2. Wait for the adapter to start. Enable Bluetooth and Wi-Fi on your phone.

## Pair over Bluetooth

1. On iPhone, open Settings → Bluetooth. On Android, open Settings → Connected devices → Pair new device. Menu labels can vary by phone.
2. Select your adapter’s Bluetooth name. Confirm the pairing and accept any CarPlay or Android Auto prompts. Leave Wi-Fi enabled for wireless projection.
3. Open the projection feature on the motorcycle display if it is available. Check the picture, controls and sound.

## Open the Dextend panel

1. On your phone or computer, open Settings → Wi-Fi and join the adapter’s network if it is available. Enter the network password if prompted. If your device warns that the network has no internet access, choose to stay connected.
2. Enter http://192.168.43.1/dextend/ in the browser address bar. This is the address on the adapter’s factory network. On a configured service network, use the adapter’s IP address on that network and keep the /dextend/ path.
3. If the panel does not open, check that you are still on the adapter’s network and that the URL starts with http://. The panel is available once the plugin starts and the adapter’s network is up.

## Set priorities and Wi-Fi

The Polish labels below can help you find these settings if your panel opens in Polish.

### Parowanie → Paired phones and priorities

1. Open Parowanie (Pairing). After pairing a phone in its Bluetooth settings, choose Odśwież listę (Refresh list).
2. Under Preferowana platforma (Preferred platform), choose Według listy (List order), CarPlay or Android Auto. The adapter tries phones on the selected platform first.
3. Use ↑ Wyżej (Move up) and ↓ Niżej (Move down) to set the order within a group. Select Zapisz na donglu (Save to adapter). The new order takes effect the next time the adapter connects, and the current session stays active.

After power returns and Bluetooth starts, the adapter automatically tries the first phone in the list. With an empty list, it waits for a phone to initiate pairing. If a phone is out of range or its negotiation fails, the adapter tries the next phone. After the last phone it returns to the first. When an active session ends, the search starts at the top of the list.

After a failed attempt, the adapter waits at least 5, 10, 15, 20, 20 and then 30 seconds before trying the same phone again. Other phones keep their turns. A successful connection resets the delay for that phone. During the wait, you can initiate a connection from your phone. The adapter can accept it as soon as the phone opens its Bluetooth profile and the receiver is free.

### Debug → Debug / USB Wi-Fi

This tab appears when the service network is available with a separate USB Wi-Fi adapter. The adapter’s built-in Wi-Fi handles regular pairing and projection.

1. In Debug, select Skanuj ponownie (Scan again). Choose Wybierz (Select) next to your network or enter the name in SSID.
2. Enter the WPA2 Personal password and choose Zapamiętaj i połącz (Remember and connect). Check progress under Połączenie (Connection).
3. Under Zapamiętane sieci (Saved networks), use Połącz (Connect) or Zapomnij (Forget). Ponów połączenie (Retry connection) starts a new attempt.

Zapisz na donglu changes the adapter’s phone priorities. Zapisz lokalnie (Save locally) stores the other configuration in the browser.

## Update or remove Dextend

Open the updater from the Dextend panel. Stay connected to the adapter’s Wi-Fi and keep internet access on your phone to download the release. Select the version, confirm installation and keep the adapter powered.

To remove Dextend, open the factory restore section and follow the confirmation prompts. After restarting the adapter, open the manufacturer’s panel if you also want to reset settings and pairings.

© 2026 Overev · [overev.com](https://overev.com/)
