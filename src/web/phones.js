// Dextend | Developed by Overev
// Copyright (c) 2026 Overev | https://overev.com/

'use strict';
(() => {
  const api = '/cgi-bin/dextend-phones';
  const form = document.querySelector('#phone-settings');
  const preference = document.querySelector('#phone-preferred');
  const list = document.querySelector('#phone-devices');
  const save = document.querySelector('#phone-save');
  const refresh = document.querySelector('#phone-refresh');
  const status = document.querySelector('#phone-status');
  let devices = [],
    token = '',
    saved = '',
    busy = false,
    pendingForget = null,
    forgetFocus = null;
  const dialog = document.querySelector('#phone-forget-dialog');
  const confirmForget = document.querySelector('#phone-forget-confirm');
  const cancelForget = document.querySelector('#phone-forget-cancel');
  function closeForget() {
    dialog.close();
    pendingForget = null;
    forgetFocus?.focus();
  }
  cancelForget.addEventListener('click', closeForget);
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    if (!busy) closeForget();
  });
  confirmForget.addEventListener('click', async () => {
    if (!pendingForget || busy) return;
    const id = pendingForget.id;
    busy = true;
    confirmForget.disabled = true;
    cancelForget.disabled = true;
    render();
    try {
      await request({
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Dextend-Token': token },
        body: JSON.stringify({ action: 'forget', id }),
      });
      devices = devices.filter((device) => device.id !== id);
      const previous = JSON.parse(saved);
      previous.order = previous.order.filter((value) => value !== id);
      saved = JSON.stringify(previous);
      dialog.close();
      pendingForget = null;
      i18n.set(
        status,
        'Usunięto sparowanie. Usuń adapter także w ustawieniach Bluetooth telefonu przed ponownym parowaniem.',
      );
    } catch (error) {
      dialog.close();
      pendingForget = null;
      i18n.set(status, i18n.errorKey(error));
    } finally {
      busy = false;
      confirmForget.disabled = false;
      cancelForget.disabled = false;
      render();
      list.querySelector('button:not(:disabled)')?.focus();
      if (!list.querySelector('button:not(:disabled)')) refresh.focus();
    }
  });
  const labels = {
    carplay: 'CarPlay',
    'android-auto': 'Android Auto',
    unknown: 'Platforma jeszcze nierozpoznana',
  };
  const payload = () => ({
    schema: 1,
    preferred: preference.value,
    order: devices.map((d) => d.id),
  });
  const dirty = () => JSON.stringify(payload()) !== saved;
  function controls() {
    preference.disabled = busy || !token;
    refresh.disabled = busy || (!!token && dirty());
    save.disabled = busy || !token || !dirty();
    form.setAttribute('aria-busy', String(busy));
  }
  function group(device) {
    if (device.platform === 'unknown') return 2;
    return preference.value !== 'none' && device.platform !== preference.value ? 1 : 0;
  }
  // Render the paired-phone order used by the adapter.
  function render(focusId, direction) {
    devices.sort((a, b) => group(a) - group(b));
    list.replaceChildren();
    if (!devices.length) {
      const empty = document.createElement('li');
      empty.className = 'muted';
      i18n.set(empty, 'Nie ma jeszcze sparowanych telefonów.');
      list.append(empty);
    }
    devices.forEach((device, index) => {
      const row = document.createElement('li');
      row.className = 'network-row phone';

      const text = document.createElement('span');
      const name = document.createElement('span');
      name.className = 'name';
      name.textContent = `${index + 1}. ${device.name}`;
      const meta = document.createElement('small');
      meta.className = 'meta';
      const platform = Object.hasOwn(labels, device.platform)
        ? labels[device.platform]
        : labels.unknown;
      i18n.set(meta, '{platform} · {id}', { platform: () => i18n.t(platform), id: device.id });
      text.append(name, meta);
      const actions = document.createElement('div');
      actions.className = 'actions';
      [-1, 1].forEach((step) => {
        const button = document.createElement('button');
        button.type = 'button';
        i18n.set(button, step < 0 ? '↑ Wyżej' : '↓ Niżej');
        i18n.set(
          button,
          step < 0 ? 'Wyżej: {name}' : 'Niżej: {name}',
          { name: device.name },
          'aria-label',
        );
        const target = index + step;
        button.disabled =
          busy ||
          target < 0 ||
          target >= devices.length ||
          group(devices[target]) !== group(device);
        button.addEventListener('click', () => {
          [devices[index], devices[target]] = [devices[target], devices[index]];
          i18n.set(status, 'Kolejność zmieniona. Zapisz ją na donglu.');
          render(device.id, step);
        });
        actions.append(button);
        if (device.id === focusId && step === direction)
          requestAnimationFrame(() => {
            if (!button.disabled) button.focus();
            else actions.querySelector('button:not(:disabled)')?.focus();
          });
      });
      const forget = document.createElement('button');
      forget.type = 'button';
      i18n.set(forget, 'Usuń');
      i18n.set(forget, 'Usuń sparowanie: {name}', { name: device.name }, 'aria-label');
      forget.disabled = busy || !token;
      forget.addEventListener('click', () => {
        pendingForget = device;
        forgetFocus = forget;
        i18n.set(
          document.querySelector('#phone-forget-description'),
          'Usunąć sparowanie z {name}? Może to zakończyć aktywne połączenie z tym telefonem.',
          { name: device.name },
        );
        dialog.showModal();
        cancelForget.focus();
      });
      actions.append(forget);
      row.append(text, actions);
      list.append(row);
    });
    controls();
  }
  async function request(options) {
    const response = await fetch(api, {
      cache: 'no-store',
      signal: AbortSignal.timeout(10000),
      ...options,
    });
    const data = await response.json();
    if (!response.ok) throw i18n.error(data.error, 'Dongiel nie przyjął żądania.');
    return data;
  }
  async function load() {
    busy = true;
    controls();
    i18n.set(status, 'Pobieranie telefonów z dongla…');
    try {
      const data = await request();
      if (
        !Array.isArray(data.devices) ||
        !['none', 'carplay', 'android-auto'].includes(data.preferred)
      )
        throw new Error('Nieprawidłowa odpowiedź dongla.');
      devices = data.devices;
      token = data.token;
      preference.value = data.preferred;
      saved = JSON.stringify(payload());
      i18n.set(status, 'Ustawienia odczytane z dongla.');
    } catch (error) {
      token = '';
      i18n.set(status, 'Nie udało się odczytać ustawień. {detail}', {
        detail: () => i18n.t(i18n.errorKey(error)),
      });
      list.replaceChildren();
      const item = document.createElement('li');
      item.className = 'muted';
      i18n.set(item, 'Lista telefonów jest niedostępna. Spróbuj odświeżyć.');
      list.append(item);
    } finally {
      busy = false;
      if (token) render();
      else controls();
    }
  }
  preference.addEventListener('change', () => {
    i18n.set(status, 'Priorytet zmieniony. Zapisz go na donglu.');
    render();
  });
  refresh.addEventListener('click', load);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (save.disabled) return;
    const body = JSON.stringify(payload());
    busy = true;
    render();
    i18n.set(status, 'Zapisywanie na donglu…');
    try {
      await request({
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Dextend-Token': token },
        body,
      });
      saved = body;
      i18n.set(status, 'Zapisano na donglu. Kolejność obowiązuje przy następnym łączeniu.');
    } catch (error) {
      i18n.set(status, i18n.errorKey(error));
    } finally {
      busy = false;
      render();
    }
  });
  window.addEventListener('beforeunload', (event) => {
    if (token && dirty()) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  load();
})();
