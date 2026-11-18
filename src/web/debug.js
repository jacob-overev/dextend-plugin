/* Dextend integration by Overev | https://overev.com/ */
'use strict';
(() => {
  const api = '/cgi-bin/dextend-debug';
  const panel = document.querySelector('#debug-panel');
  const message = document.querySelector('#debug-message');
  const form = document.querySelector('#debug-network-form');
  const availability = document.querySelector('#debug-availability');
  let busy = false,
    polling = false,
    ready = false,
    previousState = '',
    scanPending = false,
    volatile = false;
  const states = {
    COMPLETED: 'Połączono',
    SCANNING: 'Szukanie zapamiętanych sieci',
    ASSOCIATING: 'Łączenie z siecią',
    ASSOCIATED: 'Uwierzytelnianie',
    '4WAY_HANDSHAKE': 'Weryfikacja hasła',
    GROUP_HANDSHAKE: 'Weryfikacja połączenia',
    DISCONNECTED: 'Rozłączono · ponawianie',
    INACTIVE: 'Oczekiwanie na zapamiętaną sieć',
    INTERFACE_DISABLED: 'Karta nieaktywna',
  };
  async function call(data) {
    const options = {
      headers: { 'X-Dextend-Request': '1' },
      cache: 'no-store',
      signal: AbortSignal.timeout(10000),
    };
    if (data) {
      options.method = 'POST';
      options.headers['Content-Type'] = 'application/x-www-form-urlencoded';
      options.body = new URLSearchParams(data);
    }
    const response = await fetch(api, options);
    if (!(response.headers.get('content-type') || '').includes('application/json'))
      throw Error('API debug jest niedostępne.');
    const result = await response.json();
    if (!response.ok) throw i18n.error(result.error, 'Operacja nie powiodła się.');
    return result;
  }
  // wpa_supplicant uses printf encoding for binary/non-ASCII SSIDs.
  function decodeSSID(value) {
    const bytes = [];
    for (let i = 0; i < value.length; i++) {
      if (
        value[i] === '\\' &&
        value[i + 1] === 'x' &&
        /^[0-9a-f]{2}$/i.test(value.slice(i + 2, i + 4))
      ) {
        bytes.push(parseInt(value.slice(i + 2, i + 4), 16));
        i += 3;
      } else if (value[i] === '\\' && ['\\', '"'].includes(value[i + 1])) {
        bytes.push(value.charCodeAt(++i));
      } else bytes.push(...new TextEncoder().encode(value[i]));
    }
    return new TextDecoder().decode(new Uint8Array(bytes));
  }
  function event(text) {
    const li = document.createElement('li');
    i18n.set(li, '{time} · {event}', {
      time: new Date().toTimeString().slice(0, 8),
      event: () => i18n.t(text),
    });
    const list = document.querySelector('#debug-events');
    list.prepend(li);
    while (list.children.length > 30) list.lastElementChild.remove();
  }
  const ssh = document.querySelector('#service-ssh');
  const key = document.querySelector('#service-key');
  let selectedKey;
  ssh.addEventListener('change', () => {
    if (ssh.checked && !key.value.trim()) {
      ssh.checked = false;
      key.focus();
      return;
    }
    act(ssh.checked ? { action: 'ssh-on', key: key.value.trim() } : { action: 'ssh-off' },
        'Zapisano ustawienie SSH.');
  });
  function controls() {
    panel.querySelectorAll('button,input').forEach((input) => (input.disabled = busy || !ready));
    key.disabled = busy || !ready || ssh.checked;
  }
  function row(title, detail, buttons, values) {
    const item = document.createElement('div');
    item.className = 'network-row';
    const name = document.createElement('span');
    name.textContent = title;
    const info = document.createElement('small');
    i18n.set(info, detail, values);
    name.append(info);
    item.append(name);
    const actions = document.createElement('div');
    actions.className = 'actions';
    actions.append(...buttons);
    item.append(actions);
    return item;
  }
  function button(label, callback) {
    const element = document.createElement('button');
    element.type = 'button';
    i18n.set(element, label);
    element.addEventListener('click', callback);
    return element;
  }
  let lastScan, lastSaved;
  function render(data) {
    ssh.checked = data.ssh_enabled === true;
    if (selectedKey !== data.ssh_key) {
      selectedKey = data.ssh_key;
      key.value = selectedKey || '';
    }
    const present = data.present === true;
    ready = present && data.ready === true;
    volatile = data.volatile === true;
    i18n.set(
      document.querySelector('#debug-storage-mode'),
      volatile
        ? 'Test w RAM: sieci i hasła znikną po ponownym uruchomieniu dongla.'
        : 'Zapamiętane sieci są zapisywane na donglu wyłącznie przy zmianie konfiguracji.',
    );
    if (!present) document.querySelector('#debug-password').value = '';
    window.dextendDebugVisibility(present);
    i18n.set(
      availability,
      present ? (ready ? 'karta USB podłączona' : 'inicjalizacja karty USB') : 'brak karty USB',
    );
    const state = present ? data.wpa_state || (ready ? 'INACTIVE' : 'INITIALIZING') : 'ABSENT';
    const stateLabel = Object.hasOwn(states, state) ? states[state] : '';
    i18n.set(
      document.querySelector('#debug-state'),
      stateLabel || (present ? 'Inicjalizacja karty' : 'Karta odłączona'),
    );
    const details = [data.ssid && decodeSSID(data.ssid), data.ip_address]
      .filter(Boolean)
      .join(' · ');
    i18n.set(
      document.querySelector('#debug-details'),
      details ? '{details}' : 'Brak aktywnego adresu IP',
      { details },
    );
    if (state !== previousState) {
      event(stateLabel || (present ? 'Brak odpowiedzi usługi Wi-Fi' : 'Karta USB odłączona'));
      previousState = state;
    }
    if (data.scan !== lastScan) {
      lastScan = data.scan;
      const list = document.querySelector('#debug-networks');
      list.replaceChildren();
      const seen = new Set();
      for (const line of (data.scan || '').split('\n').slice(1)) {
        const parts = line.split('\t');
        if (parts.length < 5 || !parts[4] || seen.has(parts[4])) continue;
        seen.add(parts[4]);
        const ssid = decodeSSID(parts[4]);
        const supported = /WPA2?-PSK/.test(parts[3]);
        const select = button('Wybierz', () => {
          document.querySelector('#debug-ssid').value = ssid;
          document.querySelector('#debug-password').focus();
        });
        select.dataset.unsupported = String(!supported);
        list.append(
          row(ssid, '{level} dBm · {security}', [select], {
            level: parts[2],
            security: () =>
              i18n.t(supported ? 'WPA/WPA2 Personal' : 'Nieobsługiwane zabezpieczenia'),
          }),
        );
      }
      if (!list.children.length) {
        const empty = document.createElement('p');
        empty.className = 'muted';
        i18n.set(empty, 'Brak sieci w wynikach. Uruchom skanowanie lub wpisz SSID.');
        list.append(empty);
      }
    }
    if (data.networks !== lastSaved) {
      lastSaved = data.networks;
      const list = document.querySelector('#debug-saved');
      list.replaceChildren();
      for (const line of (data.networks || '').split('\n').slice(1)) {
        const parts = line.split('\t');
        if (parts.length < 4 || !/^\d+$/.test(parts[0])) continue;
        const ssid = decodeSSID(parts[1]);
        const connect = button('Połącz', () =>
          act(
            { action: 'connect', id: parts[0] },
            'Wybrano sieć. Inne zapamiętane sieci pozostają dostępne.',
          ),
        );
        const forget = button('Zapomnij', () =>
          act({ action: 'forget', id: parts[0] }, 'Usunięto zapamiętaną sieć.'),
        );
        forget.className = 'danger';
        list.append(
          row(ssid, parts[3].includes('CURRENT') ? 'Bieżąca sieć' : 'Automatyczne połączenie', [
            connect,
            forget,
          ]),
        );
      }
      if (!list.children.length) {
        const empty = document.createElement('p');
        empty.className = 'muted';
        i18n.set(empty, 'Nie zapisano jeszcze żadnej sieci.');
        list.append(empty);
      }
    }
    controls();
    panel.querySelectorAll('[data-unsupported="true"]').forEach((input) => (input.disabled = true));
  }
  async function refresh() {
    if (polling || busy || document.hidden) return;
    polling = true;
    try {
      render(await call());
    } catch {
      ready = false;
      window.dextendDebugVisibility(false);
      i18n.set(availability, 'API debug niedostępne');
      controls();
    } finally {
      polling = false;
    }
  }
  async function act(data, success) {
    if (busy || !ready) return;
    busy = true;
    controls();
    i18n.set(message, 'Wykonywanie operacji…');
    try {
      await call(data);
      i18n.set(message, success);
      event(success);
      if (data.action === 'remember') form.reset();
    } catch (error) {
      i18n.set(message, i18n.errorKey(error));
    } finally {
      busy = false;
      controls();
      await refresh();
    }
  }
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!form.reportValidity()) return;
    const ssid = document.querySelector('#debug-ssid').value;
    if (new TextEncoder().encode(ssid).length > 32) {
      i18n.set(message, 'SSID może mieć maksymalnie 32 bajty.');
      return;
    }
    const password = document.querySelector('#debug-password');
    const value = password.value;
    password.value = '';
    await act(
      { action: 'remember', ssid, password: value },
      volatile
        ? 'Sieć zapisana w RAM na czas testu. Rozpoczęto próbę połączenia.'
        : 'Sieć zapisana na donglu. Rozpoczęto próbę połączenia.',
    );
  });
  document.querySelector('#debug-scan').addEventListener('click', async () => {
    if (scanPending) return;
    scanPending = true;
    await act({ action: 'scan' }, 'Skanowanie rozpoczęte; wyniki odświeżą się automatycznie.');
    setTimeout(() => {
      scanPending = false;
      refresh();
    }, 3000);
  });
  document
    .querySelector('#debug-reconnect')
    .addEventListener('click', () =>
      act({ action: 'reconnect' }, 'Ponowiono wyszukiwanie zapamiętanych sieci.'),
    );
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refresh();
  });
  refresh();
  setInterval(refresh, 5000);
})();
