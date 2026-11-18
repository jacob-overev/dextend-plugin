/* Dextend integration by Overev | https://overev.com/ */
'use strict';
// Prototype keys are UI identifiers, not vendor API parameter names.
const toggle = (id, title, value = false, help = '') => ({
  id,
  title,
  value,
  help,
  type: 'checkbox',
});
const choice = (id, title, options, value = options[0], help = '') => ({
  id,
  title,
  options,
  value,
  help,
  type: 'select',
});
const number = (id, title, value, min, max, unit = '', help = '') => ({
  id,
  title,
  value,
  min,
  max,
  unit,
  help,
  type: 'number',
});
const text = (id, title, value = '', help = '') => ({ id, title, value, help, type: 'text' });
const groups = [
  [
    'Dextend',
    'Profil mostu do CCU. Wartości referencyjne recovery32-rc1; edycja jest lokalna.',
    [
      choice(
        'sdl.fps',
        'FPS bezprzewodowego CarPlay',
        ['15', '20', '30'],
        '20',
        'Profil bezprzewodowy: 20 FPS. Liczba określa cel, nie bieżący pomiar.',
      ),
      choice(
        'sdl.connection',
        'Połączenie telefonu',
        ['USB', 'USB + wireless'],
        'USB + wireless',
        'USB ma pierwszeństwo. Wireless potwierdzono na motocyklu.',
      ),
      choice(
        'sdl.audio',
        'Dźwięk i mikrofon',
        ['Telefon — potwierdzony profil'],
        undefined,
        'Dźwięk i mikrofon obsługuje telefon. Zmiana wymaga innego pakietu firmware.',
      ),
      number(
        'sdl.initDelay',
        'Opóźnienie startu mostu',
        20,
        0,
        120,
        's',
        'Czas na inicjalizację fabrycznych usług.',
      ),
      toggle('sdl.enabled', 'Autostart mostu', true, 'Start dodatku po włączeniu dongla.'),
      toggle(
        'sdl.recovery',
        'Odzyskiwanie połączeń',
        true,
        'Niezależny nadzór CCU i telefonu. Obecnie wbudowany.',
      ),
      choice(
        'sdl.waiting',
        'Plansza oczekiwania',
        ['Dextend — motocykl + QR', 'Statyczna', 'Animowana (test)'],
        'Dextend — motocykl + QR',
        'Projekt pakietu 2026-10-24; nie jest odczytem aktywnej planszy.',
      ),
      toggle(
        'sdl.autoConnect',
        'AutoConnect Bluetooth',
        true,
        'Automatycznie próbuje połączyć wcześniej sparowany telefon.',
      ),
      choice(
        'sdl.btRetry',
        'Ponowienie Bluetooth',
        ['5', '10', '30'],
        '5',
        'Odstęp prób w sekundach. Oczekiwanie po błędach narasta do 32 s.',
      ),
      toggle(
        'sdl.ackGuard',
        'Ograniczanie zaległych ACK',
        true,
        'Ogranicza zaległe klatki i narastanie opóźnienia obrazu.',
      ),
      toggle(
        'sdl.videoWatchdog',
        'Nadzór obrazu wireless',
        true,
        'Po 2 s ciszy sprawdza źródło; po kolejnych 2 s próbuje odzyskać obraz.',
      ),
      toggle(
        'sdl.smoothTransitions',
        'Płynne przejścia obrazu',
        true,
        'Przygotowuje obraz telefonu przed przejściem z planszy oczekiwania.',
      ),
      toggle(
        'sdl.fastRefresh',
        'Szybkie odświeżenie IDR',
        true,
        'Odświeża klatkę kluczową po 500 ms od startu obrazu.',
      ),
      toggle(
        'sdl.ipcDiagnostics',
        'Diagnostyka IPC',
        false,
        'Zapisuje ograniczone metadane komunikacji, bez treści pakietów.',
      ),
      choice(
        'sdl.androidAuto',
        'Android Auto i CarPlay',
        ['Automatyczny wybór'],
        undefined,
        'Rzeczywiste priorytety połączeń ustawisz w zakładce Parowanie.',
      ),
      choice(
        'sdl.usbLogs',
        'Logi na pamięci USB',
        ['Katalog dongle-logs na pendrivie'],
        undefined,
        'Podłączenie nośnika z tym katalogiem włącza diagnostykę; minimum 8 MiB wolnego.',
      ),
      choice(
        'sdl.logLevel',
        'Poziom logów',
        ['Zdarzenia', 'Diagnostyczny'],
        'Zdarzenia',
        'Szczegółowe logi są aktywne podczas sesji USB.',
      ),
      choice(
        'sdl.joystick',
        'Profil joysticka',
        ['Yamaha — potwierdzone mapowanie'],
        undefined,
        'Lewo/prawo: pokrętło; długi powrót obsługuje CCU.',
      ),
    ],
  ],
  [
    'Obraz',
    'Android Auto · ustawienia obrazu na donglu.',
    [
      choice(
        'video.fps',
        'FPS odbiornika',
        ['20', '25', '30', '60'],
        '30',
        'W profilu Yamaha docelowe FPS określa sekcja SDL.',
      ),
      choice(
        'video.resolution',
        'Rozdzielczość',
        ['Automatyczna', '640 × 360', 'Własna'],
        '640 × 360',
      ),
      number('video.width', 'Szerokość własna', 640, 1, 4096, 'px'),
      number('video.height', 'Wysokość własna', 360, 1, 4096, 'px'),
      number(
        'video.bitrate',
        'Bitrate',
        8,
        0,
        20,
        'Mbps',
        'Wartości fabryczne trzeba odczytać z API; 0 = auto.',
      ),
      number('video.dpi', 'DPI', 0, 0, 480, '', '0 = automatycznie.'),
      choice('video.display', 'Rozmiar interfejsu', ['Automatyczny', 'Mały', 'Duży']),
      choice('video.mode', 'Tryb obrazu', ['Domyślny', 'Płynność', 'Oryginalna rozdzielczość']),
      toggle('video.refresh', 'Automatyczne odświeżanie'),
      toggle('video.background', 'Praca w tle'),
      toggle('video.emptyFrame', 'Wysyłanie pustej klatki'),
    ],
  ],
  [
    'Audio',
    'Opcje fabryczne. W profilu Yamaha audio pozostaje po stronie telefonu.',
    [
      number('audio.delay', 'Opóźnienie mediów', 1000, 300, 2000, 'ms'),
      number('audio.echo', 'Opóźnienie echa', 80, 0, 2000, 'ms'),
      number('audio.micGain', 'Wzmocnienie mikrofonu', 0, 0, 100, ''),
      choice('audio.microphone', 'Źródło mikrofonu', ['Telefon', 'Dongiel', 'Pojazd']),
      choice('audio.micMode', 'Tryb mikrofonu', ['Domyślny', 'Tryb 1', 'Tryb 2']),
      choice('audio.category', 'Kategoria mediów', ['Domyślna', 'Tryb 1', 'Tryb 2']),
      choice('audio.callQuality', 'Jakość rozmów', ['Standard', 'HD']),
      choice('audio.navChannel', 'Kanał nawigacji', ['Nawigacja', 'Media', 'Głos']),
      toggle('audio.btCall', 'Rozmowy przez Bluetooth'),
      toggle('audio.bluetooth', 'Audio Bluetooth'),
      toggle('audio.autoPlay', 'Automatyczne odtwarzanie'),
      toggle('audio.recording', 'Nagrywanie w tle'),
      number('audio.mediaBuffer', 'Bufor mediów', 1000, 200, 20000),
      number('audio.navBuffer', 'Bufor nawigacji', 1000, 200, 40000),
      number('audio.callBuffer', 'Bufor rozmów', 1000, 200, 40000),
      number('audio.navGain', 'Wzmocnienie nawigacji', 0, 0, 100),
      number('audio.callGain', 'Wzmocnienie rozmów', 0, 0, 100),
      number('audio.navCallVolume', 'Nawigacja podczas rozmowy', 50, 0, 100, '%'),
    ],
  ],
  [
    'Połączenia',
    'Wi-Fi, Bluetooth i zachowanie po uruchomieniu.',
    [
      text('network.ssid', 'Nazwa Wi-Fi', '', 'Odczyt z dongla po podłączeniu API.'),
      text('network.bluetoothName', 'Nazwa Bluetooth'),
      choice('network.band', 'Pasmo Wi-Fi', ['Automatyczne', '2.4 GHz', '5 GHz']),
      toggle('network.autoConnect', 'Automatyczne połączenie', true),
      toggle('network.fastConnect', 'Szybkie połączenie'),
      number('network.startDelay', 'Fabryczne opóźnienie startu', 0, 0, 120, 's'),
      choice('network.connection', 'Tryb połączenia', ['Domyślny', 'Tryb 1', 'Tryb 2']),
      choice('network.transfer', 'Tryb transmisji', ['Domyślny', 'Zgodność']),
      toggle('network.heartbeat', 'Heartbeat'),
    ],
  ],
  [
    'Sterowanie i zachowanie',
    'Opcje fabrycznego interfejsu i zgodności z pojazdem.',
    [
      choice('control.knob', 'Tryb pokrętła', ['Domyślny', 'Tryb 1', 'Tryb 2']),
      toggle('control.mouse', 'Tryb kursora'),
      choice('control.autoDisplay', 'Automatyczne wyświetlanie', [
        'Automatyczne',
        'Standard',
        'Wymuszone',
      ]),
      choice('control.return', 'Powrót do interfejsu', ['Pojazd', 'Dongiel']),
      toggle('control.sync', 'Synchronizacja licznika'),
      toggle('control.gps', 'Synchronizacja GPS'),
      choice('control.huLink', 'Typ HULink', [
        'Automatyczny',
        'Tryb 1',
        'Tryb 2',
        'Tryb 3',
        'Tryb 4',
      ]),
    ],
  ],
  [
    'Personalizacja',
    'Dane pojazdu, język i ekran połączenia.',
    [
      text('vehicle.brand', 'Marka', 'Yamaha'),
      text('vehicle.model', 'Model', 'Tracer 9 GT+'),
      number('vehicle.year', 'Rok', 2024, 1980, 2100),
      choice('ui.language', 'Język ekranu dongla', ['Polski', 'English', 'Deutsch']),
      choice('ui.logo', 'Logo startowe', ['Domyślne', 'Własne']),
      {
        id: 'ui.logoFile',
        title: 'Plik logo',
        type: 'file',
        help: 'Propozycja lokalna: PNG/JPEG do 100 kB. Plik nie jest zapisywany na donglu.',
      },
      toggle('updates.auto', 'Automatyczne sprawdzanie aktualizacji'),
    ],
  ],
];
const fields = groups.flatMap((group) => group[2]);
const defaults = Object.fromEntries(
  fields.filter((f) => f.type !== 'file').map((f) => [f.id, f.value]),
);
const storageKey = 'dextend-console-prototype-v2';
let saved = { ...defaults };
let storageWarning = '';
try {
  const stored = JSON.parse(localStorage.getItem(storageKey) || '{}');
  for (const key of Object.keys(defaults)) if (Object.hasOwn(stored, key)) saved[key] = stored[key];
} catch {
  storageWarning = 'Pamięć lokalna niedostępna lub uszkodzona.';
}
const container = document.querySelector('#sections');
for (const [index, group] of groups.entries()) {
  const section = document.createElement('section');
  section.className = 'panel' + (index === 0 ? ' featured' : '');
  const heading = document.createElement('div');
  heading.className = 'section-heading';
  const num = document.createElement('span');
  num.className = 'section-number';
  num.textContent = String(index + 1).padStart(2, '0');
  const titleWrap = document.createElement('div');
  const title = document.createElement('h2');
  i18n.set(title, group[0]);
  const subtitle = document.createElement('p');
  i18n.set(subtitle, group[1]);
  titleWrap.append(title, subtitle);
  heading.append(num, titleWrap);
  section.append(heading);
  const grid = document.createElement('div');
  grid.className = 'fields';
  for (const field of group[2]) {
    const row = document.createElement('div');
    row.className = 'field';
    const description = document.createElement('div');
    const label = document.createElement('label');
    label.htmlFor = field.id;
    i18n.set(label, field.title);
    description.append(label);
    if (field.help) {
      const help = document.createElement('span');
      help.className = 'help';
      help.id = field.id + '-help';
      i18n.set(help, field.help);
      description.append(help);
    }
    const control = document.createElement('div');
    control.className = 'control';
    const input = document.createElement(field.type === 'select' ? 'select' : 'input');
    input.id = field.id;
    input.name = field.id;
    input.setAttribute('form', 'configuration');
    if (field.options)
      for (const value of field.options) {
        const option = document.createElement('option');
        option.value = value;
        i18n.set(option, value);
        input.append(option);
      }
    else input.type = field.type;
    if (field.type === 'number') {
      input.min = field.min;
      input.max = field.max;
      input.step = 1;
      input.required = true;
    }
    if (field.type === 'text') input.maxLength = 64;
    if (field.type === 'file') input.accept = 'image/png,image/jpeg';
    if (field.help) input.setAttribute('aria-describedby', field.id + '-help');
    control.append(input);
    if (field.unit) {
      const unit = document.createElement('span');
      unit.className = 'unit';
      unit.textContent = field.unit;
      control.append(unit);
    }
    row.append(description, control);
    grid.append(row);
  }
  if (index === 1) {
    const aaForm = document.querySelector('#aa-video');
    const local = document.createElement('details');
    local.id = 'local-video';
    const summary = document.createElement('summary');
    i18n.set(summary, 'Ustawienia lokalne odbiornika');
    local.append(summary, grid);
    section.append(aaForm, local);
    aaForm.hidden = false;
    local.addEventListener('toggle', () => {
      if (!section.hidden) videoLocalControls(local.open);
    });
  } else section.append(grid);
  container.append(section);
}
const panels = [
  ...container.children,
  document.querySelector('#phone-panel'),
  document.querySelector('.maintenance'),
  document.querySelector('#update-panel'),
  document.querySelector('#restore-panel'),
  document.querySelector('#diagnostics-panel'),
  document.querySelector('#debug-panel'),
];
const tabs = document.querySelector('#tabs');
// Hash routes work on the embedded web server without rewrite rules.
const tabRoutes = [
  'dextend',
  'video',
  'audio',
  'connections',
  'controls',
  'personalization',
  'pairing',
  'device',
  'update',
  'restore',
  'diagnostics',
  'debug',
];
function routeIndex() {
  return tabRoutes.indexOf(location.hash.slice(2));
}
function videoLocalControls(open) {
  document.querySelector('.toolbar').hidden = !open;
  document.querySelector('.savebar').hidden = !open;
}
function activateTab(index, focus = false, historyMode = 'push') {
  if (historyMode) {
    const url = new URL(location.href);
    url.hash = '/' + tabRoutes[index];
    if (url.href !== location.href) history[historyMode + 'State'](null, '', url);
  }
  document.querySelector('.savebar').hidden = panels[index].matches(
    '.debug-panel, .phone-panel, .restore-panel, .diagnostics-panel, .update-panel',
  );
  document.querySelector('.toolbar').hidden = false;
  if (tabRoutes[index] === 'video') videoLocalControls(document.querySelector('#local-video').open);
  panels.forEach((panel, i) => {
    panel.hidden = i !== index;
    const tab = tabs.children[i];
    tab.setAttribute('aria-selected', String(i === index));
    tab.tabIndex = i === index ? 0 : -1;
  });
  if (focus) tabs.children[index].focus();
  document.dispatchEvent(new CustomEvent('dextend-tab-change'));
}
panels.forEach((panel, index) => {
  panel.id = panel.id || 'panel-' + index;
  panel.setAttribute('role', 'tabpanel');
  panel.setAttribute('aria-labelledby', 'tab-' + index);
  const tab = document.createElement('button');
  tab.type = 'button';
  tab.id = 'tab-' + index;
  tab.setAttribute('role', 'tab');
  tab.setAttribute('aria-controls', panel.id);
  i18n.set(
    tab,
    index < groups.length
      ? groups[index][0]
      : {
          'update-panel': 'Aktualizacja',
          'diagnostics-panel': 'Diagnostyka',
          'phone-panel': 'Parowanie',
          'restore-panel': 'Przywracanie',
          'debug-panel': 'Debug',
        }[panel.id] || 'Urządzenie',
  );
  if (panel.classList.contains('debug-panel')) tab.hidden = true;
  tab.addEventListener('click', () => activateTab(index));
  tab.addEventListener('keydown', (event) => {
    const visible = [...tabs.children].filter((item) => !item.hidden);
    const position = visible.indexOf(tab);
    let target;
    if (event.key === 'ArrowRight') target = visible[(position + 1) % visible.length];
    if (event.key === 'ArrowLeft')
      target = visible[(position + visible.length - 1) % visible.length];
    if (event.key === 'Home') target = visible[0];
    if (event.key === 'End') target = visible[visible.length - 1];
    if (target) {
      event.preventDefault();
      activateTab([...tabs.children].indexOf(target), true);
    }
  });
  tabs.append(tab);
});
const initialTab = routeIndex();
// Debug remains hidden until the external adapter is confirmed by the API.
activateTab(
  initialTab >= 0 && initialTab !== panels.length - 1 ? initialTab : 0,
  false,
  initialTab === panels.length - 1 ? null : 'replace',
);
window.addEventListener('hashchange', () => {
  const index = routeIndex();
  if (index === panels.length - 1 && tabs.children[index].hidden) return;
  activateTab(index >= 0 ? index : 0, false, 'replace');
});
const form = document.getElementById('configuration');
function validateForm() {
  const invalid = [...form.elements].find((input) => input.willValidate && !input.validity.valid);
  if (!invalid) return true;
  activateTab(panels.indexOf(invalid.closest('[role="tabpanel"]')));
  const details = invalid.closest('details');
  if (details) details.open = true;
  invalid.reportValidity();
  return false;
}
function read() {
  return Object.fromEntries(
    fields
      .filter((f) => f.type !== 'file')
      .map((f) => {
        const input = document.getElementById(f.id);
        return [
          f.id,
          f.type === 'checkbox'
            ? input.checked
            : f.type === 'number'
              ? Number(input.value)
              : input.value,
        ];
      }),
  );
}
function restore() {
  for (const field of fields) {
    const input = document.getElementById(field.id);
    if (field.type === 'checkbox') input.checked = saved[field.id] === true;
    else input.value = field.type === 'file' ? '' : saved[field.id];
  }
  update();
}
function update() {
  const values = read();
  const count = fields.filter((f) =>
    f.type === 'file'
      ? document.getElementById(f.id).files.length > 0
      : values[f.id] !== saved[f.id],
  ).length;
  i18n.set(
    document.querySelector('#change-state'),
    count ? 'Niezapisane zmiany: {count}' : storageWarning || 'Brak niezapisanych zmian',
    { count },
  );
  document.querySelector('#save').disabled = !count;
  document.querySelector('#discard').disabled = !count;
}
let toastTimer;
function toast(message) {
  const target = document.querySelector('#toast');
  i18n.set(target, message);
  target.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (target.style.display = 'none'), 4500);
}
for (const type of ['input', 'change']) {
  container.addEventListener(type, (event) => {
    if (event.target.form === form) update();
  });
}
form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (!validateForm()) return;
  const file = document.getElementById('ui.logoFile').files[0];
  if (file && file.size > 100 * 1024) {
    toast('Logo przekracza limit 100 kB.');
    return;
  }
  try {
    const values = read();
    localStorage.setItem(storageKey, JSON.stringify(values));
    saved = values;
    storageWarning = '';
    restore();
    toast(
      file
        ? 'Zapisano ustawienia lokalnie. Przesyłanie logo wymaga API.'
        : 'Zapisano w przeglądarce. Dongiel pozostaje bez zmian.',
    );
  } catch {
    toast('Nie udało się zapisać. Możesz wyeksportować konfigurację.');
  }
});
document.querySelector('#discard').addEventListener('click', restore);
document.querySelector('#export').addEventListener('click', () => {
  if (!validateForm()) return;
  const blob = new Blob(
    [JSON.stringify({ schema: 1, prototype: true, settings: read() }, null, 2)],
    { type: 'application/json' },
  );
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'dextend-console-preview.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast('Wyeksportowano projekt konfiguracji.');
});
restore();

// Only a successful hardware API response may reveal the Debug tab.
window.dextendDebugVisibility = (present) => {
  const index = panels.length - 1;
  const tab = tabs.children[index];
  if (!present && tab.getAttribute('aria-selected') === 'true') {
    activateTab(
      0,
      document.activeElement === tab || panels[index].contains(document.activeElement),
    );
  }
  tab.hidden = !present;
  if (present && routeIndex() === index) activateTab(index, false, null);
  else if (!present && routeIndex() === index) activateTab(0, false, 'replace');
};
