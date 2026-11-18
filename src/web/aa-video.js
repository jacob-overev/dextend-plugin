// Dextend | Developed by Overev | https://overev.com/
'use strict';
(() => {
  const form = document.querySelector('#aa-video');
  const panel = form.closest('[role="tabpanel"]');
  const profile = form.querySelector('#aa-profile');
  const save = form.querySelector('#aa-save');
  const reload = form.querySelector('#aa-reload');
  const status = form.querySelector('#aa-status');
  const size = form.querySelector('#aa-size');
  const moves = [...form.querySelectorAll('#aa-move button')];
  const api = '/cgi-bin/dextend-phones?view=aa-video';
  const profiles = { yamaha: null, center: [640, 360, 80, 80, 60, 60] };
  const fields = [
    ['width', 'Szerokość AA', 2, 800],
    ['height', 'Wysokość AA', 2, 480],
    ['left', 'Lewy margines', 0, 798],
    ['right', 'Prawy margines', 0, 798],
    ['top', 'Górny margines', 0, 478],
    ['bottom', 'Dolny margines', 0, 478],
  ];
  const inputs = fields.map(([name, title, min, max]) => {
    const row = document.createElement('div');
    row.className = 'field';
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'number';
    input.id = label.htmlFor = 'aa-' + name;
    input.min = min;
    input.max = max;
    input.step = 2;
    input.required = true;
    input.disabled = true;
    i18n.set(label, title + ' (px)');
    row.append(label, input);
    form.querySelector('#aa-values').append(row);
    return input;
  });
  let token = '',
    saved = '',
    busy = false,
    attempted = false;
  const values = () => inputs.map((input) => input.valueAsNumber);
  function valid(v) {
    return (
      v.length === 6 &&
      v.every(
        (n, i) => Number.isInteger(n) && n % 2 === 0 && n >= fields[i][2] && n <= fields[i][3],
      ) &&
      v[2] + v[3] < 800 &&
      v[4] + v[5] < 480
    );
  }
  function setValues(v) {
    inputs.forEach((input, i) => {
      input.value = v[i];
    });
  }
  // Moving the content left advances the left edge of the crop window.
  function shifted(v, direction) {
    const result = [...v];
    const axis = direction < 2 ? 2 : 4;
    const delta = direction % 2 === 0 ? 2 : -2;
    result[axis] += delta;
    result[axis + 1] -= delta;
    return result;
  }
  function render() {
    const v = values();
    const key = JSON.stringify(v);
    const editable = !!token && !busy;
    const ok = valid(v);
    profile.disabled = !editable;
    inputs.forEach((input) => {
      input.disabled = !editable;
    });
    save.disabled = !editable || !ok || key === saved;
    reload.disabled = busy;
    moves.forEach((button, i) => {
      button.disabled = !editable || !ok || !valid(shifted(v, i));
    });
    profile.value =
      Object.keys(profiles).find((k) => JSON.stringify(profiles[k]) === key) || 'custom';
    i18n.set(
      size,
      !token
        ? ''
        : ok
          ? 'Widoczny kadr: {w} × {h} px'
          : 'Podaj wartości parzyste. Marginesy muszą pozostawić widoczny kadr.',
      { w: 800 - v[2] - v[3], h: 480 - v[4] - v[5] },
    );
    form.setAttribute('aria-busy', String(busy));
  }
  function edited() {
    render();
    i18n.set(
      status,
      JSON.stringify(values()) === saved
        ? 'Brak niezapisanych zmian'
        : 'Niezapisane zmiany profilu.',
    );
  }
  profile.addEventListener('change', () => {
    if (profiles[profile.value]) setValues(profiles[profile.value]);
    else {
      inputs[0].focus();
      return;
    }
    edited();
  });
  inputs.forEach((input) => input.addEventListener('input', edited));
  moves.forEach((button, i) =>
    button.addEventListener('click', () => {
      setValues(shifted(values(), i));
      edited();
    }),
  );
  async function transfer(write) {
    if (busy || (write && save.disabled)) return;
    const v = values();
    busy = true;
    render();
    try {
      const options = { cache: 'no-store', signal: AbortSignal.timeout(10000) };
      if (write)
        Object.assign(options, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Dextend-Token': token },
          body: JSON.stringify(v),
        });
      const response = await fetch(api, options);
      const data = await response.json();
      if (!response.ok) throw i18n.error(data.error, 'Nie udało się połączyć z adapterem.');
      if (write) {
        if (data.saved !== true) throw new Error();
        saved = JSON.stringify(v);
        i18n.set(
          status,
          data.reloadRequested
            ? 'Zapisano profil na donglu.'
            : 'Zapisano profil. Uruchom ponownie dongiel, aby go zastosować.',
        );
      } else {
        if (
          !Array.isArray(data.geometry) ||
          !valid(data.geometry) ||
          !Array.isArray(data.defaultGeometry) ||
          !valid(data.defaultGeometry) ||
          !data.token
        )
          throw new Error();
        profiles.yamaha = data.defaultGeometry;
        token = data.token;
        setValues(data.geometry);
        saved = JSON.stringify(data.geometry);
        i18n.set(status, 'Wczytano profil z dongla.');
      }
    } catch (error) {
      i18n.set(status, i18n.errorKey(error));
    } finally {
      busy = false;
      render();
    }
  }
  reload.addEventListener('click', () => transfer(false));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    transfer(true);
  });
  function loadWhenVisible() {
    if (panel.hidden || attempted) return;
    attempted = true;
    transfer(false);
  }
  document.addEventListener('dextend-tab-change', loadWhenVisible);
  loadWhenVisible();
})();
