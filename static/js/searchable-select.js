/**
 * کامپوننت انتخاب جستجوپذیر — Searchable Select
 * جایگزین سبک Select2 بدون وابستگی خارجی
 */
class SearchableSelect {
    constructor(select, options = {}) {
        if (select.dataset.searchableSelectInitialized === 'true') return;

        this.original = select;
        this.placeholder = options.placeholder || 'جستجو کنید...';
        this.api = options.api || null;
        this.minChars = options.minChars || 1;
        this.isOpen = false;
        this._reposition = () => this._position();

        this._build();
        this._bindEvents();
    }

    _build() {
        this.original.dataset.searchableSelectInitialized = 'true';
        this.original.style.display = 'none';

        // بخش نمایشی در جای select اصلی باقی می‌ماند.
        this.container = document.createElement('div');
        this.container.className = 'ss-container';

        this.display = document.createElement('div');
        this.display.className = 'ss-display';
        this.display.tabIndex = 0;
        this.display.setAttribute('role', 'combobox');
        this.display.setAttribute('aria-haspopup', 'listbox');
        this.display.setAttribute('aria-expanded', 'false');

        // dropdown به body منتقل می‌شود تا زیر کارت بعدی نرود و توسط overflow بریده نشود.
        this.dropdown = document.createElement('div');
        this.dropdown.className = 'ss-dropdown';
        this.dropdown.setAttribute('role', 'listbox');
        this.dropdown.style.display = 'none';

        this.searchInput = document.createElement('input');
        this.searchInput.type = 'text';
        this.searchInput.className = 'ss-search';
        this.searchInput.placeholder = this.placeholder;
        this.searchInput.setAttribute('aria-label', 'جستجو در گزینه‌ها');
        this.searchInput.setAttribute('autocomplete', 'off');

        this.optionsList = document.createElement('div');
        this.optionsList.className = 'ss-options';

        this.emptyMsg = document.createElement('div');
        this.emptyMsg.className = 'ss-empty';
        this.emptyMsg.textContent = 'گزینه‌ای یافت نشد';

        this.dropdown.appendChild(this.searchInput);
        this.dropdown.appendChild(this.optionsList);
        this.dropdown.appendChild(this.emptyMsg);

        this.container.appendChild(this.display);
        this.original.parentNode.insertBefore(this.container, this.original);
        document.body.appendChild(this.dropdown);

        this._loadOptions();
        this._syncDisplay();
    }

    _setDisplay(text, isPlaceholder = false) {
        this.display.replaceChildren();

        const label = document.createElement('span');
        label.textContent = text;
        if (isPlaceholder) label.className = 'ss-placeholder';

        const icon = document.createElement('i');
        icon.className = 'bi bi-chevron-down ss-chevron';
        icon.setAttribute('aria-hidden', 'true');

        this.display.appendChild(label);
        this.display.appendChild(icon);
    }

    _syncDisplay() {
        const selected = this.original.options[this.original.selectedIndex];
        if (selected && (selected.value || !selected.disabled)) {
            this._setDisplay(selected.textContent.trim());
        } else {
            this._setDisplay(this.placeholder, true);
        }
    }

    _loadOptions() {
        this.allOptions = [];
        this.original.querySelectorAll('option').forEach(option => {
            if (option.value && !option.disabled) {
                this.allOptions.push({
                    value: option.value,
                    text: option.textContent.trim()
                });
            }
        });
        this._renderOptions(this.allOptions);
    }

    _renderOptions(options) {
        this.optionsList.innerHTML = '';

        if (options.length === 0) {
            this.emptyMsg.style.display = 'block';
            return;
        }
        this.emptyMsg.style.display = 'none';

        options.forEach(option => {
            const item = document.createElement('div');
            item.className = 'ss-option';
            item.textContent = option.text;
            item.dataset.value = option.value;
            item.setAttribute('role', 'option');
            item.setAttribute('aria-selected', option.value === this.original.value ? 'true' : 'false');

            if (option.value === this.original.value) item.classList.add('selected');

            item.addEventListener('click', () => this._select(option));
            this.optionsList.appendChild(item);
        });
    }

    _select(option) {
        this.original.value = option.value;
        this._setDisplay(option.text);
        this.display.classList.remove('is-invalid');
        this.close();
        this.original.dispatchEvent(new Event('change', { bubbles: true }));
    }

    open() {
        if (this.original.disabled) return;
        if (SearchableSelect.active && SearchableSelect.active !== this) {
            SearchableSelect.active.close();
        }

        SearchableSelect.active = this;
        this.isOpen = true;
        this.container.classList.add('open');
        this.display.setAttribute('aria-expanded', 'true');
        this.dropdown.style.display = 'block';
        this.searchInput.value = '';
        this._loadOptions();
        this._position();

        requestAnimationFrame(() => {
            this._position();
            this.searchInput.focus({ preventScroll: true });
        });
    }

    close() {
        this.isOpen = false;
        this.container.classList.remove('open');
        this.display.setAttribute('aria-expanded', 'false');
        this.dropdown.style.display = 'none';
        if (SearchableSelect.active === this) SearchableSelect.active = null;
    }

    toggle() {
        this.isOpen ? this.close() : this.open();
    }

    _position() {
        if (!this.isOpen) return;

        const rect = this.display.getBoundingClientRect();
        const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
        const viewportHeight = document.documentElement.clientHeight || window.innerHeight;

        if (rect.bottom < 0 || rect.top > viewportHeight || rect.right < 0 || rect.left > viewportWidth) {
            this.close();
            return;
        }

        // در موبایل dropdown به شکل bottom-sheet نمایش داده می‌شود.
        if (viewportWidth <= 768) {
            this.dropdown.classList.add('ss-mobile');
            this.dropdown.style.left = '0px';
            this.dropdown.style.top = 'auto';
            this.dropdown.style.bottom = '0px';
            this.dropdown.style.width = `${viewportWidth}px`;
            this.dropdown.style.maxHeight = `${Math.max(180, Math.round(viewportHeight * 0.55))}px`;
            return;
        }

        this.dropdown.classList.remove('ss-mobile');
        this.dropdown.style.bottom = 'auto';

        const margin = 8;
        const gap = 5;
        const width = Math.max(rect.width, 220);
        const safeWidth = Math.min(width, viewportWidth - (margin * 2));
        this.dropdown.style.width = `${safeWidth}px`;
        this.dropdown.style.maxHeight = `${Math.min(300, viewportHeight - (margin * 2))}px`;

        const dropdownHeight = this.dropdown.offsetHeight;
        const spaceBelow = viewportHeight - rect.bottom - margin;
        const spaceAbove = rect.top - margin;
        const openAbove = spaceBelow < dropdownHeight + gap && spaceAbove > spaceBelow;

        let top = openAbove ? rect.top - dropdownHeight - gap : rect.bottom + gap;
        top = Math.max(margin, Math.min(top, viewportHeight - dropdownHeight - margin));

        // هم‌ترازی با لبه راست فیلد در صفحات RTL.
        let left = rect.right - safeWidth;
        left = Math.max(margin, Math.min(left, viewportWidth - safeWidth - margin));

        this.dropdown.style.top = `${Math.round(top)}px`;
        this.dropdown.style.left = `${Math.round(left)}px`;
    }

    _bindEvents() {
        this.display.addEventListener('click', () => this.toggle());
        this.display.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
                event.preventDefault();
                this.open();
            } else if (event.key === 'Escape') {
                this.close();
            }
        });

        this.searchInput.addEventListener('input', () => {
            const query = this.searchInput.value.trim().toLocaleLowerCase('fa');
            if (this.api && query.length >= this.minChars) {
                this._searchAPI(query);
            } else {
                const filtered = this.allOptions.filter(option =>
                    option.text.toLocaleLowerCase('fa').includes(query)
                );
                this._renderOptions(filtered);
                this._position();
            }
        });

        this.searchInput.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                event.preventDefault();
                this.close();
                this.display.focus({ preventScroll: true });
            }
        });

        document.addEventListener('click', event => {
            if (!this.container.contains(event.target) && !this.dropdown.contains(event.target)) {
                this.close();
            }
        });

        // پیام اعتبارسنجی select مخفی روی کنترل قابل مشاهده نشان داده شود.
        this.original.addEventListener('invalid', event => {
            event.preventDefault();
            this.display.classList.add('is-invalid');
            this.display.focus({ preventScroll: true });
            this.open();
        });

        this.original.addEventListener('change', () => this._syncDisplay());
        window.addEventListener('resize', this._reposition);
        window.addEventListener('scroll', this._reposition, true);
    }

    _searchAPI(query) {
        fetch(`${this.api}?q=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(data => {
                const options = data.map(item => ({
                    value: String(item.id),
                    text: item.name
                }));
                this._renderOptions(options);
                this._position();
            })
            .catch(() => {
                const filtered = this.allOptions.filter(option =>
                    option.text.toLocaleLowerCase('fa').includes(query)
                );
                this._renderOptions(filtered);
                this._position();
            });
    }
}

// ═══ مقداردهی خودکار ═══
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('select.searchable').forEach(select => {
        if (select.dataset.searchableSelectInitialized !== 'true') {
            new SearchableSelect(select, {
                placeholder: select.dataset.placeholder || 'جستجو کنید...',
                api: select.dataset.api || null
            });
        }
    });

    const autoSelectors = [
        'select[name="student_id"]',
        'select[name="course_id"]',
        'select[name="teacher_id"]',
        'select[name="class_id"]',
        'select[name="room_id"]',
        'select[name="field_id"]',
        'select[name="branch_id"]',
        'select[name="category_id"]',
        'select[name="receiver_id"]',
        'select[name="person_id"]',
        'select[name="new_teacher_id"]',
        'select[name="target_class_id"]'
    ];

    autoSelectors.forEach(selector => {
        document.querySelectorAll(selector).forEach(select => {
            if (select.dataset.searchableSelectInitialized !== 'true' && select.options.length > 5) {
                select.classList.add('searchable');
                new SearchableSelect(select, {
                    placeholder: select.dataset.placeholder || 'جستجو و انتخاب کنید...'
                });
            }
        });
    });
});
