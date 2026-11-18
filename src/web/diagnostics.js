// Dextend | Developed by Overev
// Copyright (c) 2026 Overev | https://overev.com/

'use strict';
(() => {
  const panel = document.querySelector('#diagnostics-panel');
  const output = document.querySelector('#diagnostics-output');
  const status = document.querySelector('#diagnostics-status');
  const refresh = document.querySelector('#diagnostics-refresh');
  const copy = document.querySelector('#diagnostics-copy');
  const download = document.querySelector('#diagnostics-download');
  let busy = false;
  async function load() {
    if (busy || panel.hidden || document.hidden) return;
    busy = true;
    refresh.disabled = true;
    if (!output.value) i18n.set(status, 'Pobieranie raportu…');
    try {
      const response = await fetch('/cgi-bin/dextend-debug?diagnostics=1', {
        headers: { 'X-Dextend-Request': '1' },
        cache: 'no-store',
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok || !(response.headers.get('content-type') || '').includes('text/plain'))
        throw new Error('report');
      const text = await response.text();
      if (text.length > 150000 || !text.startsWith('DEXTEND DIAGNOSTICS'))
        throw new Error('report');
      // Preserve a manual selection while the reader copies from the field.
      if (document.activeElement !== output) output.value = text;
      copy.disabled = download.disabled = false;
      i18n.set(status, 'Raport odświeżony.');
    } catch {
      i18n.set(
        status,
        'Nie udało się pobrać raportu. Sprawdź połączenie z panelem i spróbuj ponownie.',
      );
    } finally {
      busy = false;
      refresh.disabled = false;
    }
  }
  refresh.addEventListener('click', load);
  copy.addEventListener('click', async () => {
    try {
      if (navigator.clipboard && window.isSecureContext)
        await navigator.clipboard.writeText(output.value);
      else {
        output.focus();
        output.select();
        if (!document.execCommand('copy')) throw new Error('clipboard');
      }
      i18n.set(status, 'Skopiowano raport.');
    } catch {
      output.focus();
      output.select();
      i18n.set(status, 'Nie udało się skopiować. Zaznaczony tekst możesz skopiować ręcznie.');
    }
  });
  download.addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([output.value], { type: 'text/plain;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'dextend-diagnostics.txt';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.addEventListener('dextend-tab-change', load);
  document.addEventListener('visibilitychange', load);
  setInterval(load, 5000);
})();
