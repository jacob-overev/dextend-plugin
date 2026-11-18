// Dextend | Developed by Overev
// Copyright (c) 2026 Overev | https://overev.com/

'use strict';
(() => {
  const endpoint = '/cgi-bin/dextend-restore';
  // The CGI expects the same protocol phrase in both languages.
  const requestPhrase = 'PRZYWRÓĆ';
  const confirmation = () => (i18n.language === 'pl' ? requestPhrase : 'RESTORE');
  const dialog = document.querySelector('#restore-dialog');
  const launch = document.querySelector('#restore-open');
  const input = document.querySelector('#restore-phrase');
  const submit = document.querySelector('#restore-submit');
  const status = document.querySelector('#restore-status');
  const factoryPanel = document.querySelector('#restore-oem');
  let polling = false;

  async function request(options) {
    const response = await fetch(endpoint, {
      cache: 'no-store',
      signal: AbortSignal.timeout(8000),
      ...options,
    });
    if (!response.headers.get('Content-Type')?.includes('application/json')) {
      throw new Error('Usługa przywracania jest niedostępna.');
    }
    const data = await response.json();
    if (!response.ok) {
      const error = i18n.error(data.error, 'Adapter odrzucił żądanie.');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function show(state) {
    launch.disabled = state !== 'idle';
    factoryPanel.hidden = state !== 'restored';
    const messages = {
      checking: 'Sprawdzanie instalacji i tworzenie kopii. Nie odłączaj zasilania.',
      writing: 'Usuwanie Dextend i sprawdzanie plików. Nie odłączaj zasilania.',
      restored:
        'Dextend usunięty. Uruchom adapter ponownie, połącz się z jego Wi-Fi i w panelu producenta wybierz przywrócenie ustawień fabrycznych. Zostaw zasilanie podłączone, aż adapter ponownie się uruchomi.',
      rejected: 'Adapter odrzucił operację przed zapisem. Dextend pozostaje zainstalowany.',
      error:
        'Nie udało się potwierdzić usunięcia Dextend. Zostaw zasilanie podłączone i sprawdź stan przed ponowieniem.',
    };
    i18n.set(status, Object.hasOwn(messages, state) ? messages[state] : '');
  }

  async function follow() {
    if (polling) return;
    polling = true;
    try {
      const data = await request();
      if (data.state === 'idle') throw new Error('Nie otrzymano potwierdzenia uruchomienia.');
      show(data.state);
      if (data.state === 'checking' || data.state === 'writing') setTimeout(follow, 1200);
    } catch {
      launch.disabled = true;
      i18n.set(
        status,
        'Brak potwierdzenia z adaptera. Nie odłączaj zasilania. Panel spróbuje ponownie sprawdzić stan.',
      );
      setTimeout(follow, 4000);
    } finally {
      polling = false;
    }
  }

  launch.addEventListener('click', () => {
    input.value = '';
    submit.disabled = true;
    dialog.showModal();
  });
  // Keep confirmation in the selected language.
  function validateConfirmation() {
    submit.disabled = input.value !== confirmation();
  }
  input.addEventListener('input', validateConfirmation);
  document.addEventListener('dextend-languagechange', validateConfirmation);
  document.querySelector('#restore-cancel').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    if (!launch.disabled) launch.focus();
  });

  document.querySelector('#restore-confirm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (input.value !== confirmation() || launch.disabled) return;
    launch.disabled = true;
    dialog.close();
    status.focus();
    let info;
    try {
      info = await request();
    } catch (error) {
      i18n.set(status, i18n.errorKey(error));
      launch.disabled = false;
      return;
    }
    if (info.state !== 'idle') {
      show(info.state);
      if (info.state === 'checking' || info.state === 'writing') follow();
      return;
    }
    show('checking');
    try {
      await request({
        method: 'POST',
        headers: { 'Content-Type': 'text/plain;charset=UTF-8', 'X-Dextend-Token': info.token },
        body: requestPhrase,
      });
    } catch (error) {
      if ([400, 403, 405, 503].includes(error.status)) {
        i18n.set(status, i18n.errorKey(error));
        launch.disabled = false;
        return;
      }
      i18n.set(
        status,
        'Nie potwierdzono przyjęcia żądania. Nie odłączaj zasilania podczas sprawdzania stanu.',
      );
    }
    follow();
  });
})();
