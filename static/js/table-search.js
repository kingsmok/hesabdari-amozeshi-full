/* جستجوی محلی یکپارچه برای همه جدول‌ها (با پشتیبانی از محتوای پویا) */
(() => {
    'use strict';

    const states = new Map();
    let tableCounter = 0;
    let shortcutBound = false;

    const normalise = value => String(value == null ? '' : value)
        .toLocaleLowerCase('fa-IR')
        .replace(/ي/g, 'ی')
        .replace(/ك/g, 'ک')
        .replace(/\s+/g, ' ')
        .trim();

    const debounce = (callback, delay = 100) => {
        let timer;
        return (...args) => {
            window.clearTimeout(timer);
            timer = window.setTimeout(() => callback(...args), delay);
        };
    };

    function searchableRows(table) {
        return Array.from(table.querySelectorAll('tbody tr')).filter(row =>
            !row.classList.contains('table-search-empty') &&
            !row.hasAttribute('data-no-table-search')
        );
    }

    function filterState(state, announce = false) {
        const query = normalise(state.input.value);
        const tbody = state.table.querySelector('tbody');
        if (!tbody) return;
        if (!tbody.contains(state.emptyRow)) tbody.appendChild(state.emptyRow);
        const rows = searchableRows(state.table);
        let visible = 0;

        rows.forEach(row => {
            const haystack = normalise(row.dataset.searchText || row.textContent);
            const matches = !query || haystack.includes(query);
            row.classList.toggle('table-search-filtered-out', !matches);
            if (matches && !row.hidden && !row.classList.contains('d-none')) visible += 1;
        });

        const colspan = Math.max(1, state.table.querySelectorAll('thead th').length ||
            state.table.querySelector('tbody tr:not(.table-search-empty)')?.children.length || 1);
        state.emptyCell.colSpan = colspan;
        state.emptyRow.hidden = !query || visible > 0;
        state.clearButton.hidden = !query;
        state.count.textContent = query ? `${visible.toLocaleString('fa-IR')} از ${rows.length.toLocaleString('fa-IR')}` : '';
        state.live.textContent = announce && query
            ? (visible ? `${visible.toLocaleString('fa-IR')} نتیجه یافت شد` : 'نتیجه‌ای یافت نشد')
            : '';
    }

    function createToolbar(table) {
        if (table.dataset.tableSearchReady === '1' || table.dataset.noSearch === 'true' ||
            table.dataset.noAutoSearch === 'true' || table.dataset.tableSearch === 'false' ||
            table.closest('.jalali-picker, .ss-dropdown, [data-no-table-search]')) return;
        if (!table.querySelector('tbody')) return;

        table.dataset.tableSearchReady = '1';
        table.id ||= `searchable-table-${++tableCounter}`;

        const toolbar = document.createElement('div');
        toolbar.className = 'universal-table-tools table-search-toolbar';
        toolbar.setAttribute('role', 'search');

        const wrapper = document.createElement('label');
        wrapper.className = 'universal-table-search table-search-input-wrap';
        const icon = document.createElement('i');
        icon.className = 'bi bi-search';
        icon.setAttribute('aria-hidden', 'true');
        const input = document.createElement('input');
        input.type = 'search';
        input.className = 'form-control table-search-input';
        input.placeholder = table.dataset.searchPlaceholder || 'جستجو در این جدول...';
        input.autocomplete = 'off';
        input.maxLength = 200;
        input.setAttribute('aria-label', table.dataset.searchLabel || 'جستجو در جدول');
        input.setAttribute('aria-controls', table.id);
        input.setAttribute('enterkeyhint', 'search');

        const clearButton = document.createElement('button');
        clearButton.type = 'button';
        clearButton.className = 'universal-table-clear table-search-clear';
        clearButton.setAttribute('aria-label', 'پاک کردن جستجو');
        clearButton.hidden = true;
        const clearIcon = document.createElement('i');
        clearIcon.className = 'bi bi-x-lg';
        clearIcon.setAttribute('aria-hidden', 'true');
        clearButton.appendChild(clearIcon);
        wrapper.append(icon, input, clearButton);

        const count = document.createElement('span');
        count.className = 'universal-table-count table-search-count';
        count.setAttribute('aria-hidden', 'true');
        const live = document.createElement('span');
        live.className = 'visually-hidden';
        live.setAttribute('role', 'status');
        live.setAttribute('aria-live', 'polite');
        live.setAttribute('aria-atomic', 'true');
        toolbar.append(wrapper, count, live);

        const parent = table.closest('.table-responsive') || table;
        parent.insertAdjacentElement('beforebegin', toolbar);

        const emptyRow = document.createElement('tr');
        emptyRow.className = 'universal-no-result table-search-empty';
        emptyRow.hidden = true;
        emptyRow.setAttribute('aria-live', 'polite');
        const emptyCell = document.createElement('td');
        emptyCell.className = 'text-center text-muted py-4';
        emptyCell.textContent = 'نتیجه‌ای یافت نشد';
        emptyRow.appendChild(emptyCell);
        table.querySelector('tbody').appendChild(emptyRow);

        const state = { table, toolbar, input, clearButton, count, live, emptyRow, emptyCell };
        states.set(table, state);
        const runFilter = debounce(announce => filterState(state, announce));
        input.addEventListener('input', () => runFilter(true));
        input.addEventListener('keydown', event => {
            if (event.key === 'Escape' && input.value) {
                event.preventDefault();
                input.value = '';
                filterState(state, true);
            }
        });
        clearButton.addEventListener('click', () => {
            input.value = '';
            filterState(state, true);
            input.focus();
        });

        state.observer = new MutationObserver(debounce(() => filterState(state, false), 50));
        state.observer.observe(table, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true,
            attributeFilter: ['data-search-text']
        });
        filterState(state, false);
    }

    function initialise(root = document) {
        if (root instanceof HTMLTableElement) createToolbar(root);
        if (root.querySelectorAll) root.querySelectorAll('table').forEach(createToolbar);
        const parentTable = root.closest?.('table');
        if (parentTable) createToolbar(parentTable);
    }

    function destroyRemoved(root) {
        const tables = [];
        if (root instanceof HTMLTableElement) tables.push(root);
        if (root.querySelectorAll) tables.push(...root.querySelectorAll('table[data-table-search-ready="1"]'));
        tables.forEach(table => {
            if (table.isConnected) return;
            const state = states.get(table);
            state?.observer.disconnect();
            state?.toolbar.remove();
            state?.emptyRow.remove();
            searchableRows(table).forEach(row => row.classList.remove('table-search-filtered-out'));
            delete table.dataset.tableSearchReady;
            states.delete(table);
        });
    }

    function bindShortcut() {
        if (shortcutBound) return;
        shortcutBound = true;
        document.addEventListener('keydown', event => {
            const target = event.target;
            const typing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement ||
                target instanceof HTMLSelectElement || target?.isContentEditable;
            if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || typing) return;
            const firstVisible = Array.from(document.querySelectorAll('.table-search-input')).find(input =>
                input.offsetParent !== null && !input.disabled
            );
            if (firstVisible) {
                event.preventDefault();
                firstVisible.focus();
            }
        });
    }

    function start() {
        initialise();
        bindShortcut();
        const pageObserver = new MutationObserver(mutations => {
            mutations.forEach(mutation => {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === Node.ELEMENT_NODE) initialise(node);
                });
                mutation.removedNodes.forEach(node => {
                    if (node.nodeType === Node.ELEMENT_NODE) destroyRemoved(node);
                });
            });
        });
        pageObserver.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
