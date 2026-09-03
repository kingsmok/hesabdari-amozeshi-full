/* Unified reporting centre interactions. */
(function () {
    'use strict';

    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

    function csrf(config) {
        return (config && config.csrf) || ($('meta[name="csrf-token"]') || {}).content || '';
    }

    function notify(message, type) {
        if (window.showToast) window.showToast(message, type || 'success');
        else alert(message);
    }

    function api(url, options, config) {
        options = options || {};
        options.headers = Object.assign({
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf(config)
        }, options.headers || {});
        return fetch(url, options).then(async response => {
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.ok === false) throw new Error(data.error || 'عملیات ناموفق بود');
            return data;
        });
    }

    function buildChart(canvas, chart) {
        if (!canvas || !chart || typeof Chart === 'undefined') return null;
        const supportedTypes = ['bar', 'line', 'pie', 'doughnut', 'polarArea', 'radar'];
        const type = supportedTypes.includes(chart.type) ? chart.type : 'bar';
        const gridColor = document.body.classList.contains('dark-mode') ? 'rgba(148,163,184,.15)' : 'rgba(148,163,184,.18)';
        const textColor = document.body.classList.contains('dark-mode') ? '#cbd5e1' : '#64748b';
        const datasets = (chart.datasets || []).map((item, index) => Object.assign({
            borderWidth: type === 'line' ? 2 : 0,
            tension: .35,
            fill: type === 'line',
            pointRadius: 2,
            borderRadius: type === 'bar' ? 6 : 0
        }, item));
        return new Chart(canvas, {
            type,
            data: {labels: chart.labels || [], datasets},
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : undefined,
                interaction: {mode: 'index', intersect: false},
                plugins: {
                    legend: {position: 'bottom', rtl: true, labels: {color: textColor, usePointStyle: true, padding: 18}},
                    tooltip: {rtl: true, textDirection: 'rtl', callbacks: {label: context => {
                        const value = context.parsed && context.parsed.y !== undefined ? context.parsed.y : context.parsed;
                        return `${context.dataset.label || ''}: ${new Intl.NumberFormat('fa-IR').format(value || 0)}`;
                    }}}
                },
                scales: ['pie', 'doughnut', 'polarArea'].includes(type) ? {} : {
                    x: {grid: {display: false}, ticks: {color: textColor, maxRotation: 35, minRotation: 0}},
                    y: {beginAtZero: true, grid: {color: gridColor}, ticks: {color: textColor, callback: value => new Intl.NumberFormat('fa-IR', {notation: 'compact'}).format(value)}},
                    y1: {display: datasets.some(d => d.yAxisID === 'y1'), position: 'right', beginAtZero: true, grid: {drawOnChartArea: false}, ticks: {color: textColor, callback: value => new Intl.NumberFormat('fa-IR', {notation: 'compact'}).format(value)}}
                }
            }
        });
    }

    function initTabs() {
        const buttons = $$('[data-report-tab]');
        if (!buttons.length) return;
        const panes = $$('[data-report-pane]');
        buttons.forEach((button, index) => {
            const name = button.dataset.reportTab;
            button.setAttribute('role', 'tab');
            button.id = button.id || `report-tab-${name}`;
            button.setAttribute('aria-controls', `report-pane-${name}`);
            button.tabIndex = index === 0 ? 0 : -1;
        });
        panes.forEach(pane => {
            pane.id = `report-pane-${pane.dataset.reportPane}`;
            pane.setAttribute('role', 'tabpanel');
            pane.setAttribute('aria-labelledby', `report-tab-${pane.dataset.reportPane}`);
        });
        const activate = (name, focus) => {
            buttons.forEach(button => {
                const active = button.dataset.reportTab === name;
                button.classList.toggle('active', active);
                button.setAttribute('aria-selected', String(active));
                button.tabIndex = active ? 0 : -1;
                if (active && focus) button.focus();
            });
            panes.forEach(pane => pane.classList.toggle('active', pane.dataset.reportPane === name));
            try { localStorage.setItem('report-active-tab', name); } catch (_) {}
            if (history.replaceState) history.replaceState(null, '', '#' + name);
        };
        buttons.forEach((button, index) => {
            button.addEventListener('click', () => activate(button.dataset.reportTab));
            button.addEventListener('keydown', event => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();
                let target = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
                    (index + (event.key === 'ArrowLeft' ? 1 : -1) + buttons.length) % buttons.length;
                activate(buttons[target].dataset.reportTab, true);
            });
        });
        let savedTab = '';
        try { savedTab = localStorage.getItem('report-active-tab') || ''; } catch (_) {}
        const requested = location.hash.slice(1) || savedTab;
        const initial = requested && $('[data-report-pane="' + CSS.escape(requested) + '"]')
            ? requested : (buttons.find(button => button.classList.contains('active')) || buttons[0]).dataset.reportTab;
        activate(initial);
    }

    function normalise(value) {
        return String(value || '').normalize('NFKC').toLocaleLowerCase('fa')
            .replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').replace(/[ۀة]/g, 'ه').replace(/\u200c/g, ' ')
            .replace(/[۰-۹٠-٩]/g, d => String('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩'.indexOf(d) % 10))
            .replace(/[,٬]/g, '').replace(/٫/g, '.')
            .replace(/\s+/g, ' ').trim();
    }

    function initCatalog() {
        const input = $('#reportCatalogSearch');
        const category = $('#reportCategoryFilter');
        if (!input) return;
        const apply = () => {
            const query = normalise(input.value.trim());
            const selected = category ? category.value : '';
            let visible = 0;
            $$('[data-report-card]').forEach(card => {
                const match = (!query || normalise(card.dataset.search).includes(query)) &&
                    (!selected || card.closest('[data-category]').dataset.category === selected);
                card.classList.toggle('d-none', !match);
                if (match) visible++;
            });
            $$('.report-category').forEach(section => {
                section.classList.toggle('d-none', !$$('[data-report-card]:not(.d-none)', section).length);
            });
            const count = $('#reportCatalogCount');
            if (count) count.textContent = new Intl.NumberFormat('fa-IR').format(visible) + ' گزارش';
            const empty = $('#reportCatalogEmpty');
            if (empty) empty.classList.toggle('d-none', visible !== 0);
        };
        input.addEventListener('input', apply);
        if (category) category.addEventListener('change', apply);
    }

    function initFavorites(config) {
        $$('[data-favorite]').forEach(button => button.addEventListener('click', event => {
            event.preventDefault(); event.stopPropagation();
            if (button.disabled) return;
            const key = button.dataset.favorite;
            const peers = $$('[data-favorite="' + CSS.escape(key) + '"]');
            const method = button.classList.contains('active') ? 'DELETE' : 'POST';
            peers.forEach(other => { other.disabled = true; });
            api('/reports/api/favorites/' + encodeURIComponent(key), {method}, config).then(data => {
                peers.forEach(other => {
                    other.classList.toggle('active', data.favorite);
                    other.setAttribute('aria-pressed', String(data.favorite));
                    const icon = $('i', other);
                    if (icon) icon.className = 'bi bi-star' + (data.favorite ? '-fill' : '');
                    other.setAttribute('aria-label', data.favorite ? 'حذف از علاقه‌مندی' : 'افزودن به علاقه‌مندی');
                });
                notify(data.favorite ? 'گزارش به علاقه‌مندی‌ها اضافه شد' : 'گزارش از علاقه‌مندی‌ها حذف شد');
            }).catch(error => notify(error.message, 'error'))
              .finally(() => { peers.forEach(other => { other.disabled = false; }); });
        }));
    }

    function currentFilters() {
        const form = $('#reportFilterForm');
        if (!form) return {};
        const data = {};
        new FormData(form).forEach((value, key) => {
            if (value !== '' || key === 'date_from' || key === 'date_to') data[key] = value;
        });
        delete data.page;
        return data;
    }

    function selectedColumnKeys() {
        return $$('[data-column-toggle]:checked').map(input => input.value);
    }

    function applyColumns(config) {
        let keys = selectedColumnKeys();
        if (!keys.length) {
            const first = $('[data-column-toggle]');
            if (first) { first.checked = true; keys = [first.value]; }
        }
        $$('[data-column]').forEach(cell => cell.classList.toggle('d-none', !keys.includes(cell.dataset.column)));
        try { localStorage.setItem('report-columns-' + config.key, JSON.stringify(keys)); } catch (_) {}
        $$('.report-export-link').forEach(link => {
            const url = new URL(link.href, location.origin);
            url.searchParams.set('columns', keys.join(','));
            link.href = url.pathname + url.search;
        });
    }

    function initColumnPicker(config) {
        const inputs = $$('[data-column-toggle]');
        if (!inputs.length) return;
        let saved = null;
        const urlColumns = new URLSearchParams(location.search).get('columns');
        if (urlColumns) saved = urlColumns.split(',');
        if (!saved) {
            try { saved = JSON.parse(localStorage.getItem('report-columns-' + config.key)); } catch (_) {}
        }
        if (Array.isArray(saved) && saved.length) inputs.forEach(input => { input.checked = saved.includes(input.value); });
        $('[data-apply-columns]')?.addEventListener('click', () => applyColumns(config));
        $('[data-columns-all]')?.addEventListener('click', () => { inputs.forEach(input => input.checked = true); });
        applyColumns(config);
    }

    function initDatePresets() {
        $$('[data-date-preset]').forEach(button => button.addEventListener('click', () => {
            const from = $('[name="date_from"]'); const to = $('[name="date_to"]');
            if (!to) return;
            if (button.dataset.datePreset === 'clear') {
                if (from) from.value = '';
                to.value = '';
                // A fiscal period is also a date boundary. Clear it so the
                // “all dates” action cannot be silently narrowed on submit.
                const fiscal = $('[name="fiscal_id"]');
                if (fiscal) {
                    fiscal.value = '';
                    fiscal.dispatchEvent(new Event('change', {bubbles: true}));
                }
                const comparison = $('[name="compare"]');
                if (comparison) {
                    comparison.value = '';
                    comparison.dispatchEvent(new Event('change', {bubbles: true}));
                }
                return;
            }
            // These values are rendered by the server's configured reporting
            // timezone, so "today" cannot drift with the browser timezone.
            if (from && button.dataset.start) from.value = button.dataset.start;
            if (button.dataset.end) to.value = button.dataset.end;
        }));
    }

    function initFiscalPeriod() {
        const select = $('[data-fiscal-period]');
        if (!select) return;
        select.addEventListener('change', () => {
            const option = select.options[select.selectedIndex];
            if (!option || !option.value) return;
            const from = $('[name="date_from"]');
            const to = $('[name="date_to"]');
            if (from && option.dataset.start) from.value = option.dataset.start;
            if (to && option.dataset.end) to.value = option.dataset.end;
        });
    }

    function initDeliveryFields(root) {
        $$('[data-delivery-select]', root || document).forEach(select => {
            const recipient = $('[name="recipient"]', select.closest('form') || document);
            if (!recipient) return;
            const sync = () => {
                const required = ['telegram', 'email'].includes(select.value);
                recipient.required = required;
                recipient.type = select.value === 'email' ? 'email' : 'text';
                recipient.setAttribute('aria-required', String(required));
                recipient.placeholder = select.value === 'email' ? 'نشانی ایمیل گیرنده' :
                    select.value === 'telegram' ? 'شناسه گفت‌وگوی تلگرام' :
                    select.value === 'bale' ? 'شناسه گفت‌وگوی بله (اختیاری)' :
                    'برای اعلان داخلی خالی بگذارید';
            };
            select.addEventListener('change', sync);
            sync();
        });
    }

    function initViewActions(config) {
        $('[data-toggle-favorite]')?.addEventListener('click', event => {
            const button = event.currentTarget;
            if (button.disabled) return;
            button.disabled = true;
            const method = button.getAttribute('aria-pressed') === 'true' ? 'DELETE' : 'POST';
            api('/reports/api/favorites/' + encodeURIComponent(config.key), {method}, config).then(data => {
                button.setAttribute('aria-pressed', String(data.favorite));
                const icon = $('i', button); if (icon) icon.className = 'bi bi-star' + (data.favorite ? '-fill' : '');
                const label = $('span', button); if (label) label.textContent = data.favorite ? 'نشان‌شده' : 'نشان کردن';
                notify(data.favorite ? 'گزارش نشان شد' : 'نشان گزارش برداشته شد');
            }).catch(error => notify(error.message, 'error'))
              .finally(() => { button.disabled = false; });
        });

        $('[data-save-view]')?.addEventListener('click', event => {
            const button = event.currentTarget;
            const name = ($('#presetName') || {}).value?.trim();
            if (!name) return notify('نام نما را وارد کنید', 'warning');
            if (button.disabled) return;
            button.disabled = true;
            api('/reports/api/presets', {method: 'POST', body: JSON.stringify({
                report_key: config.key, name, filters: currentFilters(), columns: selectedColumnKeys()
            })}, config).then(() => {
                notify('نمای گزارش ذخیره شد');
                const modal = bootstrap.Modal.getInstance($('#saveViewModal')); if (modal) modal.hide();
                setTimeout(() => location.reload(), 550);
            }).catch(error => notify(error.message, 'error'))
              .finally(() => { button.disabled = false; });
        });

        $('[data-save-snapshot]')?.addEventListener('click', button => {
            const element = button.currentTarget; element.disabled = true;
            api('/reports/api/snapshots', {method: 'POST', body: JSON.stringify({
                report_key: config.key, filters: currentFilters()
            })}, config).then(() => notify('تصویر شاخص‌های گزارش ذخیره شد'))
              .catch(error => notify(error.message, 'error')).finally(() => { element.disabled = false; });
        });

        $$('[data-delete-preset]').forEach(button => button.addEventListener('click', () => {
            if (!confirm('نمای ذخیره‌شده حذف شود؟')) return;
            api('/reports/api/presets/' + button.dataset.deletePreset, {method: 'DELETE'}, config).then(() => {
                button.closest('.btn-group')?.remove(); notify('نما حذف شد');
            }).catch(error => notify(error.message, 'error'));
        }));

        const scheduleModal = $('#scheduleModal');
        scheduleModal?.addEventListener('show.bs.modal', () => {
            const target = $('#scheduleFilters');
            if (target) {
                const values = currentFilters();
                values.columns = selectedColumnKeys().join(',');
                target.value = JSON.stringify(values);
            }
        });

        $('[data-filter-collapse]')?.addEventListener('click', event => {
            const bodies = $$('[data-filter-body]');
            bodies.forEach(item => item.classList.toggle('d-none'));
            const collapsed = bodies.length ? bodies[0].classList.contains('d-none') : false;
            const icon = $('i', event.currentTarget);
            if (icon) {
                icon.classList.toggle('bi-chevron-down', collapsed);
                icon.classList.toggle('bi-chevron-up', !collapsed);
            }
            event.currentTarget.setAttribute('aria-expanded', String(!collapsed));
        });

        $$('[data-toggle-chart]').forEach(button => button.addEventListener('click', () => {
            const panel = $('#reportChartPanel');
            const body = $('.report-panel-body', panel || document);
            if (!panel || !body) return;
            const collapsed = body.classList.toggle('d-none');
            $$('#reportChartPanel [data-toggle-chart] i').forEach(icon => {
                icon.classList.toggle('bi-chevron-down', collapsed);
                icon.classList.toggle('bi-chevron-up', !collapsed);
            });
            $$('[data-toggle-chart]').forEach(control => {
                control.classList.toggle('active', !collapsed);
                control.setAttribute('aria-expanded', String(!collapsed));
            });
        }));
    }

    function rememberReport(key) {
        if (!key) return;
        try {
            const recent = JSON.parse(localStorage.getItem('report-recent') || '[]').filter(x => x !== key);
            recent.unshift(key); localStorage.setItem('report-recent', JSON.stringify(recent.slice(0, 10)));
        } catch (_) {}
    }

    function renderRecentReports() {
        const target = $('#recentReports');
        if (!target) return;
        let keys = [];
        try { keys = JSON.parse(localStorage.getItem('report-recent') || '[]'); } catch (_) {}
        if (!Array.isArray(keys)) keys = [];
        keys.forEach(key => {
            const source = $('[data-report-card][data-key="' + CSS.escape(key) + '"]');
            if (!source) return;
            const clone = source.cloneNode(true);
            clone.removeAttribute('data-report-card');
            clone.addEventListener('click', () => rememberReport(key));
            target.appendChild(clone);
        });
        $('#recentReportsEmpty')?.classList.toggle('d-none', target.children.length > 0);
    }

    function initHome(config) {
        initTabs(); initCatalog(); renderRecentReports(); initFavorites(config);
        buildChart($('#executiveChart'), config.chart);
        $$('[data-report-card]').forEach(card => card.addEventListener('click', () => rememberReport(card.dataset.key)));
    }

    function initView(config) {
        if (config.printMode && typeof Chart !== 'undefined') Chart.defaults.animation = false;
        rememberReport(config.key);
        initDatePresets(); initFiscalPeriod(); initColumnPicker(config); initDeliveryFields(); initViewActions(config);
        $$('[data-sort-key]').forEach(header => {
            header.addEventListener('click', () => sort(header.dataset.sortKey));
        });
        buildChart($('#reportChart'), config.chart);
    }

    function sort(key) {
        const field = $('#reportSort'); const direction = $('#reportDirection'); const form = $('#reportFilterForm');
        if (!field || !direction || !form) return;
        if (field.value === key) direction.value = direction.value === 'asc' ? 'desc' : 'asc';
        else { field.value = key; direction.value = 'asc'; }
        form.submit();
    }

    window.ReportCentre = {initHome, initView, initDeliveryFields, sort};
}());
