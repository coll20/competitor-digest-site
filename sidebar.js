(async function () {
  const ul = document.getElementById('archive-list');
  const empty = document.getElementById('archive-empty');
  if (!ul) return;
  try {
    const r = await fetch('/archive/manifest.json', { cache: 'no-cache' });
    if (!r.ok) throw new Error('manifest ' + r.status);
    const items = await r.json();
    items.sort((a, b) => (a.date < b.date ? 1 : -1));
    if (items.length === 0) {
      if (empty) empty.textContent = '아직 아카이브 없음';
      return;
    }
    if (empty) empty.remove();
    const currentDate = (document.body.dataset.pageDate || '').trim();
    items.forEach((it, idx) => {
      const li = document.createElement('li');
      if (it.date === currentDate) li.className = 'current';
      const a = document.createElement('a');
      a.href = idx === 0 && !currentDate ? '/' : `/archive/${it.date}.html`;
      const dateEl = document.createElement('span');
      dateEl.className = 'date';
      dateEl.textContent = it.date + (idx === 0 ? ' (최초)' : '');
      const subEl = document.createElement('span');
      subEl.className = 'sub';
      subEl.textContent = it.headline || '';
      a.appendChild(dateEl);
      a.appendChild(subEl);
      li.appendChild(a);
      ul.appendChild(li);
    });
  } catch (e) {
    if (empty) empty.textContent = '아카이브 로드 실패';
    console.error('archive manifest load failed', e);
  }
})();

(function () {
  const btn = document.querySelector('.sidebar-toggle');
  const side = document.querySelector('aside.sidebar');
  if (!btn || !side) return;
  btn.addEventListener('click', () => side.classList.toggle('open'));
})();
