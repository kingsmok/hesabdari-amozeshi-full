/* انتخاب‌گر جستجوپذیر، دسترس‌پذیر و سازگار با گزینه‌های پویا */
(() => {
    'use strict';

    let instanceCounter = 0;
    const instances = new Set();

    const normalise = value => String(value == null ? '' : value)
        .toLocaleLowerCase('fa-IR')
        .replace(/ي/g, 'ی')
        .replace(/ك/g, 'ک')
        .trim();

    class SearchableSelect {
        constructor(select) {
            if (!(select instanceof HTMLSelectElement) || select.multiple || select.size > 1) return null;
            if (select._searchableSelect) return select._searchableSelect;

            this.select = select;
            this.id = `searchable-select-${++instanceCounter}`;
            this.activeIndex = -1;
            this.isOpen = false;
            this.positionFrame = null;
            this.optionItems = [];

            select._searchableSelect = this;
            select.dataset.searchableInitialized = 'true';
            this.createElements();
            this.bindEvents();
            this.refreshFromSelect();
            this.observeSelect();
            instances.add(this);
        }

        createElements() {
            this.container = document.createElement('div');
            this.container.className = 'ss-container';

            this.display = document.createElement('div');
            this.display.className = 'ss-display';
            this.display.setAttribute('role', 'combobox');
            this.display.setAttribute('aria-haspopup', 'listbox');
            this.display.setAttribute('aria-expanded', 'false');
            this.display.setAttribute('aria-controls', `${this.id}-listbox`);
            this.display.tabIndex = 0;

            this.displayText = document.createElement('span');
            this.chevron = document.createElement('i');
            this.chevron.className = 'bi bi-chevron-down ss-chevron';
            this.chevron.setAttribute('aria-hidden', 'true');
            this.display.append(this.displayText, this.chevron);

            this.dropdown = document.createElement('div');
            this.dropdown.className = 'ss-dropdown';
            this.dropdown.id = `${this.id}-popup`;

            this.searchInput = document.createElement('input');
            this.searchInput.type = 'search';
            this.searchInput.className = 'ss-search';
            this.searchInput.placeholder = this.select.dataset.placeholder || 'جستجو...';
            this.searchInput.autocomplete = 'off';
            this.searchInput.maxLength = 200;
            this.searchInput.setAttribute('aria-label', 'جستجو در گزینه‌ها');
            this.searchInput.setAttribute('aria-controls', `${this.id}-listbox`);

            this.optionsList = document.createElement('div');
            this.optionsList.className = 'ss-options';
            this.optionsList.id = `${this.id}-listbox`;
            this.optionsList.setAttribute('role', 'listbox');

            this.emptyState = document.createElement('div');
            this.emptyState.className = 'ss-empty';
            this.emptyState.textContent = 'موردی یافت نشد';
            this.emptyState.hidden = true;

            this.dropdown.append(this.searchInput, this.optionsList, this.emptyState);
            this.originalTabIndex = this.select.getAttribute('tabindex');
            this.select.classList.add('ss-native-select');
            this.select.setAttribute('aria-hidden', 'true');
            this.select.tabIndex = -1;
            this.select.insertAdjacentElement('afterend', this.container);
            this.container.appendChild(this.display);
            document.body.appendChild(this.dropdown);
        }

        bindEvents() {
            this.display.addEventListener('click', () => this.toggle());
            this.display.addEventListener('keydown', event => this.onDisplayKeydown(event));
            this.searchInput.addEventListener('input', () => this.filter(this.searchInput.value));
            this.searchInput.addEventListener('keydown', event => this.onSearchKeydown(event));

            this.onNativeChange = () => this.syncSelection();
            this.select.addEventListener('change', this.onNativeChange);
            this.select.addEventListener('input', this.onNativeChange);
            this.onNativeInvalid = () => {
                this.display.classList.add('is-invalid');
                this.display.focus({ preventScroll: true });
            };
            this.select.addEventListener('invalid', this.onNativeInvalid, true);
            if (this.select.form) {
                this.onFormReset = () => window.setTimeout(() => {
                    if (document.documentElement.contains(this.select)) this.refreshFromSelect();
                }, 0);
                this.select.form.addEventListener('reset', this.onFormReset);
            }
            this.labelClickHandlers = [];
            Array.from(this.select.labels || []).forEach(label => {
                const handler = event => {
                    if (event.target.closest('.ss-container')) return;
                    event.preventDefault();
                    this.display.focus({ preventScroll: true });
                    this.open();
                };
                label.addEventListener('click', handler);
                this.labelClickHandlers.push([label, handler]);
            });

            this.onDocumentPointerDown = event => {
                if (!this.container.contains(event.target) && !this.dropdown.contains(event.target)) {
                    this.close(false);
                }
            };
            this.onViewportChange = () => {
                if (!this.isOpen || this.positionFrame) return;
                this.positionFrame = window.requestAnimationFrame(() => {
                    this.positionFrame = null;
                    this.positionDropdown();
                });
            };
            document.addEventListener('pointerdown', this.onDocumentPointerDown);
            window.addEventListener('resize', this.onViewportChange, { passive: true });
            window.addEventListener('scroll', this.onViewportChange, { passive: true, capture: true });

            const closeAfterFocusLeaves = () => window.setTimeout(() => {
                const active = document.activeElement;
                if (!this.container.contains(active) && !this.dropdown.contains(active)) this.close(false);
            }, 0);
            this.container.addEventListener('focusout', closeAfterFocusLeaves);
            this.dropdown.addEventListener('focusout', closeAfterFocusLeaves);
        }

        observeSelect() {
            this.selectObserver = new MutationObserver(() => this.refreshFromSelect());
            this.selectObserver.observe(this.select, {
                childList: true,
                subtree: true,
                characterData: true,
                attributes: true,
                attributeFilter: ['disabled', 'label', 'selected', 'value']
            });
        }

        refreshFromSelect() {
            const previousQuery = this.searchInput.value;
            this.optionItems = Array.from(this.select.options).map((option, index) => ({
                option,
                index,
                text: option.textContent.trim(),
                searchText: normalise(`${option.textContent} ${option.value}`),
                element: null
            }));
            this.optionsList.replaceChildren();

            this.optionItems.forEach(item => {
                const element = document.createElement('div');
                element.className = 'ss-option';
                element.id = `${this.id}-option-${item.index}`;
                element.setAttribute('role', 'option');
                element.textContent = item.text;
                element.dataset.index = String(item.index);
                if (item.option.disabled) {
                    element.setAttribute('aria-disabled', 'true');
                    element.classList.add('disabled');
                }
                element.addEventListener('pointerdown', event => event.preventDefault());
                element.addEventListener('click', () => this.selectItem(item.index));
                item.element = element;
                this.optionsList.appendChild(element);
            });

            const labels = this.select.labels ? Array.from(this.select.labels) : [];
            const accessibleName = this.select.getAttribute('aria-label') ||
                labels.map(label => label.textContent.trim()).filter(Boolean).join(' ') || 'انتخاب گزینه';
            this.display.setAttribute('aria-label', accessibleName);
            this.container.classList.toggle('disabled', this.select.disabled);
            if (this.select.disabled && this.isOpen) this.close(false);
            this.display.setAttribute('aria-disabled', String(this.select.disabled));
            this.display.tabIndex = this.select.disabled ? -1 : 0;
            this.syncSelection();
            this.filter(previousQuery);
            if (this.isOpen) this.positionDropdown();
        }

        syncSelection() {
            const selectedIndex = this.select.selectedIndex;
            const selected = selectedIndex >= 0 ? this.select.options[selectedIndex] : null;
            const isPlaceholder = !selected || (selected.value === '' && selectedIndex === 0);
            this.displayText.textContent = selected ? selected.textContent.trim() : 'انتخاب کنید';
            this.displayText.className = isPlaceholder ? 'ss-placeholder' : '';
            if (this.select.validity.valid) this.display.classList.remove('is-invalid');

            this.optionItems.forEach(item => {
                const chosen = item.index === selectedIndex;
                item.element.classList.toggle('selected', chosen);
                item.element.setAttribute('aria-selected', String(chosen));
            });
            if (selectedIndex >= 0) this.activeIndex = selectedIndex;
            this.updateActiveDescendant();
        }

        filter(query) {
            const needle = normalise(query);
            const visible = [];
            this.optionItems.forEach(item => {
                const matches = !needle || item.searchText.includes(needle);
                item.element.hidden = !matches;
                if (matches && !item.option.disabled) visible.push(item.index);
            });
            this.emptyState.hidden = visible.length !== 0;

            if (!visible.includes(this.activeIndex)) {
                const selected = this.select.selectedIndex;
                this.activeIndex = visible.includes(selected) ? selected : (visible[0] ?? -1);
            }
            this.updateActiveDescendant();
        }

        toggle() {
            if (this.select.disabled) return;
            if (this.isOpen) this.close(true);
            else this.open();
        }

        open() {
            if (this.select.disabled || this.isOpen) return;
            instances.forEach(instance => {
                if (instance !== this) instance.close(false);
            });
            this.isOpen = true;
            this.container.classList.add('open');
            this.display.setAttribute('aria-expanded', 'true');
            this.dropdown.style.display = 'block';
            this.searchInput.value = '';
            this.filter('');
            const visible = this.visibleIndexes();
            this.activeIndex = visible.includes(this.select.selectedIndex)
                ? this.select.selectedIndex
                : (visible[0] ?? -1);
            this.updateActiveDescendant();
            this.positionDropdown();
            window.requestAnimationFrame(() => {
                if (!this.isOpen) return;
                this.searchInput.focus({ preventScroll: true });
                this.scrollActiveIntoView();
            });
        }

        close(returnFocus = false) {
            if (!this.isOpen) return;
            this.isOpen = false;
            this.container.classList.remove('open');
            this.display.setAttribute('aria-expanded', 'false');
            this.display.removeAttribute('aria-activedescendant');
            this.searchInput.removeAttribute('aria-activedescendant');
            this.dropdown.style.display = 'none';
            if (returnFocus && document.body.contains(this.display)) {
                this.display.focus({ preventScroll: true });
            }
        }

        positionDropdown() {
            if (!this.isOpen) return;
            const rect = this.display.getBoundingClientRect();
            const mobile = window.innerWidth <= 768;
            this.dropdown.classList.toggle('ss-mobile', mobile);
            if (mobile) {
                this.dropdown.style.left = '12px';
                this.dropdown.style.right = '12px';
                this.dropdown.style.bottom = '12px';
                this.dropdown.style.top = 'auto';
                this.dropdown.style.width = 'auto';
                return;
            }

            const gap = 5;
            const desiredHeight = Math.min(300, this.dropdown.scrollHeight || 300);
            const roomBelow = window.innerHeight - rect.bottom - gap;
            const roomAbove = rect.top - gap;
            const placeAbove = roomBelow < desiredHeight && roomAbove > roomBelow;
            const width = Math.min(rect.width, window.innerWidth - 16);
            const left = Math.min(Math.max(8, rect.left), window.innerWidth - width - 8);
            this.dropdown.style.left = `${left}px`;
            this.dropdown.style.right = 'auto';
            this.dropdown.style.bottom = 'auto';
            this.dropdown.style.width = `${width}px`;
            this.dropdown.style.top = placeAbove
                ? `${Math.max(8, rect.top - desiredHeight - gap)}px`
                : `${Math.max(8, Math.min(window.innerHeight - desiredHeight - 8, rect.bottom + gap))}px`;
        }

        selectItem(index) {
            const item = this.optionItems[index];
            if (!item || item.option.disabled) return;
            this.select.selectedIndex = item.index;
            this.select.dispatchEvent(new Event('input', { bubbles: true }));
            this.select.dispatchEvent(new Event('change', { bubbles: true }));
            this.syncSelection();
            this.close(true);
        }

        onDisplayKeydown(event) {
            if (this.select.disabled) return;
            if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                this.open();
            }
        }

        onSearchKeydown(event) {
            if (event.key === 'Escape') {
                event.preventDefault();
                this.close(true);
                return;
            }
            if (event.key === 'Tab') {
                this.close(false);
                return;
            }
            if (event.key === 'Enter') {
                event.preventDefault();
                if (this.activeIndex >= 0) this.selectItem(this.activeIndex);
                return;
            }
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Home' || event.key === 'End') {
                event.preventDefault();
                this.moveActive(event.key);
            }
        }

        visibleIndexes() {
            return this.optionItems
                .filter(item => !item.element.hidden && !item.option.disabled)
                .map(item => item.index);
        }

        firstVisibleIndex() {
            return this.visibleIndexes()[0] ?? -1;
        }

        moveActive(key) {
            const visible = this.visibleIndexes();
            if (!visible.length) {
                this.activeIndex = -1;
            } else if (key === 'Home') {
                this.activeIndex = visible[0];
            } else if (key === 'End') {
                this.activeIndex = visible[visible.length - 1];
            } else {
                const current = visible.indexOf(this.activeIndex);
                const direction = key === 'ArrowDown' ? 1 : -1;
                const start = current < 0 ? (direction > 0 ? -1 : 0) : current;
                this.activeIndex = visible[(start + direction + visible.length) % visible.length];
            }
            this.updateActiveDescendant();
            this.scrollActiveIntoView();
        }

        updateActiveDescendant() {
            this.optionItems.forEach(item => item.element.classList.toggle('active', item.index === this.activeIndex));
            const active = this.optionItems[this.activeIndex];
            if (active && !active.element.hidden) {
                this.searchInput.setAttribute('aria-activedescendant', active.element.id);
                if (this.isOpen) this.display.setAttribute('aria-activedescendant', active.element.id);
            } else {
                this.searchInput.removeAttribute('aria-activedescendant');
                this.display.removeAttribute('aria-activedescendant');
            }
        }

        scrollActiveIntoView() {
            const active = this.optionItems[this.activeIndex];
            if (active && !active.element.hidden) active.element.scrollIntoView({ block: 'nearest' });
        }

        destroy() {
            this.close(false);
            this.selectObserver?.disconnect();
            this.select.removeEventListener('change', this.onNativeChange);
            this.select.removeEventListener('input', this.onNativeChange);
            this.select.removeEventListener('invalid', this.onNativeInvalid, true);
            document.removeEventListener('pointerdown', this.onDocumentPointerDown);
            window.removeEventListener('resize', this.onViewportChange);
            window.removeEventListener('scroll', this.onViewportChange, { capture: true });
            if (this.select.form && this.onFormReset) {
                this.select.form.removeEventListener('reset', this.onFormReset);
            }
            (this.labelClickHandlers || []).forEach(([label, handler]) => {
                label.removeEventListener('click', handler);
            });
            if (this.positionFrame) window.cancelAnimationFrame(this.positionFrame);
            this.dropdown.remove();
            this.container.remove();
            this.select.classList.remove('ss-native-select');
            this.select.removeAttribute('aria-hidden');
            if (this.originalTabIndex == null) this.select.removeAttribute('tabindex');
            else this.select.setAttribute('tabindex', this.originalTabIndex);
            delete this.select.dataset.searchableInitialized;
            delete this.select._searchableSelect;
            instances.delete(this);
        }
    }

    function initialiseSelects(root = document) {
        if (root instanceof HTMLSelectElement && !root.dataset.searchableInitialized &&
                root.dataset.searchable !== 'false') {
            new SearchableSelect(root);
        }
        if (!root.querySelectorAll) return;
        root.querySelectorAll('select:not([data-searchable-initialized])').forEach(select => {
            if (select.dataset.searchable !== 'false') new SearchableSelect(select);
        });
    }

    function start() {
        initialiseSelects();
        const pageObserver = new MutationObserver(mutations => {
            mutations.forEach(mutation => {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === Node.ELEMENT_NODE) initialiseSelects(node);
                });
                mutation.removedNodes.forEach(node => {
                    if (node.nodeType !== Node.ELEMENT_NODE) return;
                    const removedSelects = [];
                    if (node instanceof HTMLSelectElement) removedSelects.push(node);
                    if (node.querySelectorAll) {
                        removedSelects.push(...node.querySelectorAll('select[data-searchable-initialized]'));
                    }
                    removedSelects.forEach(select => {
                        if (!select.isConnected) select._searchableSelect?.destroy();
                    });
                });
            });
        });
        pageObserver.observe(document.body, { childList: true, subtree: true });
    }

    window.SearchableSelect = SearchableSelect;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
