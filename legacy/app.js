(() => {
  'use strict';

  const body = document.body;
  const currentPath = window.location.pathname;
  const themeButton = document.querySelector('.theme-toggle');
  const savedTheme = localStorage.getItem('petshop-theme');

  if (savedTheme === 'dark') body.classList.add('theme-dark');
  if (themeButton) {
    themeButton.textContent = body.classList.contains('theme-dark') ? '☀' : '☾';
    themeButton.addEventListener('click', () => {
      body.classList.toggle('theme-dark');
      const dark = body.classList.contains('theme-dark');
      localStorage.setItem('petshop-theme', dark ? 'dark' : 'light');
      themeButton.textContent = dark ? '☀' : '☾';
      themeButton.setAttribute('aria-label', dark ? 'Usar tema claro' : 'Usar tema escuro');
    });
  }

  document.querySelectorAll('.main-nav a').forEach(link => {
    const linkPath = new URL(link.href).pathname;
    if (linkPath === currentPath || (currentPath === '/' && linkPath === '/')) {
      link.classList.add('active');
      link.setAttribute('aria-current', 'page');
    }
  });

  if (currentPath === '/login') {
    const main = document.querySelector('main');
    if (main) main.classList.add('login-shell');
    const card = document.querySelector('.login-shell .card');
    if (card) {
      const intro = card.querySelector('p');
      if (intro) intro.classList.add('login-intro');
      const form = card.querySelector('form');
      if (form) {
        const submit = form.querySelector('button[type="submit"], button:not([type])');
        if (submit) submit.classList.add('login-submit');
      }
    }
  }

  document.querySelectorAll('table').forEach((table, index) => {
    const card = table.closest('.card');
    if (!card) return;
    const toolbar = document.createElement('div');
    toolbar.className = 'table-tools';

    const search = document.createElement('input');
    search.className = 'table-search';
    search.type = 'search';
    search.placeholder = 'Buscar nesta lista...';
    search.setAttribute('aria-label', 'Buscar nesta lista');

    const counter = document.createElement('span');
    counter.className = 'row-count';
    counter.setAttribute('aria-live', 'polite');
    toolbar.append(search, counter);
    table.parentNode.insertBefore(toolbar, table);

    const rows = Array.from(table.tBodies[0]?.rows || []).filter(row => !row.querySelector('th'));
    const empty = document.createElement('tr');
    empty.innerHTML = '<td class="empty-state" colspan="20">Nenhum resultado encontrado.</td>';
    empty.hidden = true;
    table.tBodies[0]?.appendChild(empty);

    const update = () => {
      const query = search.value.trim().toLocaleLowerCase('pt-BR');
      let visible = 0;
      rows.forEach(row => {
        const match = row.textContent.toLocaleLowerCase('pt-BR').includes(query);
        row.hidden = !match;
        if (match) visible += 1;
      });
      empty.hidden = visible !== 0;
      counter.textContent = `${visible} de ${rows.length} registro${rows.length === 1 ? '' : 's'}`;
    };
    search.addEventListener('input', update);
    update();
  });

  if (currentPath === '/produtos') {
    document.querySelectorAll('table tbody tr').forEach(row => {
      const stockCell = row.cells[4];
      if (!stockCell || !/^\d+$/.test(stockCell.textContent.trim())) return;
      const stock = Number(stockCell.textContent.trim());
      stockCell.classList.add(stock <= 3 ? 'stock-low' : 'stock-ok');
      if (stock <= 3) stockCell.title = 'Estoque baixo: reponha este produto';
    });
  }

  document.querySelectorAll('[data-count]').forEach(element => {
    const target = Number(element.dataset.count || 0);
    const duration = 650;
    const start = performance.now();
    const animate = now => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      element.textContent = Math.round(target * eased).toLocaleString('pt-BR');
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  });

  document.querySelectorAll('.notice').forEach(notice => {
    window.setTimeout(() => notice.classList.add('hide'), 4800);
    window.setTimeout(() => notice.remove(), 5200);
  });

  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', event => {
      if (event.defaultPrevented) return;
      const button = form.querySelector('button[type="submit"], button:not([type])');
      if (!button) return;
      button.disabled = true;
      button.dataset.originalText = button.textContent;
      button.textContent = 'Processando...';
    });
  });

  document.addEventListener('keydown', event => {
    if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
    const active = document.activeElement;
    if (active && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName)) return;
    const search = document.querySelector('.table-search');
    if (search) {
      event.preventDefault();
      search.focus();
    }
  });
})();
