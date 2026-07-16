/**
 * کامپوننت انتخاب جستوپذیر — Searchable Select
 * جایگزین ساده Select2 بدون وابستگی خارجی
 */
class SearchableSelect {
    constructor(select, options = {}) {
        this.original = select;
        this.placeholder = options.placeholder || 'جستجو کنید...';
        this.api = options.api || null;  // URL برای جستجوی AJAX
        this.minChars = options.minChars || 1;
        
        this._build();
        this._bindEvents();
    }
    
    _build() {
        // مخفی کردن select اصلی
        this.original.style.display = 'none';
        
        // ساخت container
        this.container = document.createElement('div');
        this.container.className = 'ss-container';
        this.container.style.cssText = 'position: relative; width: 100%;';
        
        // input نمایشی
        this.display = document.createElement('div');
        this.display.className = 'ss-display';
        this.display.style.cssText = `
            display: flex; align-items: center; justify-content: space-between;
            padding: 9px 14px; border: 1.5px solid #e0e4e8; border-radius: 8px;
            background: #fff; cursor: pointer; font-size: 13px; min-height: 40px;
            transition: all 0.2s;
        `;
        this.display.innerHTML = `<span class="ss-placeholder" style="color: #b0bec5;">${this.placeholder}</span><i class="bi bi-chevron-down" style="font-size: 10px; color: #b0bec5;"></i>`;
        
        // dropdown
        this.dropdown = document.createElement('div');
        this.dropdown.className = 'ss-dropdown';
        this.dropdown.style.cssText = `
            display: none; position: absolute; top: 100%; left: 0; right: 0;
            background: #fff; border: 1px solid #e0e4e8; border-radius: 8px;
            box-shadow: 0 8px 24px rgba(0,0,0,.12); z-index: 1000;
            max-height: 300px; overflow: hidden; margin-top: 4px;
        `;
        
        // input جستجو
        this.searchInput = document.createElement('input');
        this.searchInput.type = 'text';
        this.searchInput.className = 'ss-search';
        this.searchInput.placeholder = this.placeholder;
        this.searchInput.style.cssText = `
            width: 100%; padding: 10px 14px; border: none; border-bottom: 1px solid #f0f0f0;
            font-size: 13px; font-family: Vazirmatn, Tahoma; outline: none;
            box-sizing: border-box;
        `;
        
        // لیست گزینه‌ها
        this.optionsList = document.createElement('div');
        this.optionsList.className = 'ss-options';
        this.optionsList.style.cssText = 'max-height: 240px; overflow-y: auto; padding: 4px;';
        
        // پیام خالی
        this.emptyMsg = document.createElement('div');
        this.emptyMsg.style.cssText = 'padding: 16px; text-align: center; color: #b0bec5; font-size: 12px; display: none;';
        this.emptyMsg.textContent = 'نتیجه‌ای یافت نشد';
        
        this.dropdown.appendChild(this.searchInput);
        this.dropdown.appendChild(this.optionsList);
        this.dropdown.appendChild(this.emptyMsg);
        
        this.container.appendChild(this.display);
        this.container.appendChild(this.dropdown);
        
        this.original.parentNode.insertBefore(this.container, this.original);
        
        // بارگذاری اولیه گزینه‌ها
        this._loadOptions();
        
        // اگر مقدار قبلی دارد
        if (this.original.value) {
            const opt = this.original.querySelector(`option[value="${this.original.value}"]`);
            if (opt) {
                this.display.innerHTML = `<span>${opt.textContent}</span><i class="bi bi-chevron-down" style="font-size: 10px; color: #b0bec5;"></i>`;
            }
        }
    }
    
    _loadOptions() {
        this.allOptions = [];
        const options = this.original.querySelectorAll('option');
        options.forEach(opt => {
            if (opt.value) {
                this.allOptions.push({
                    value: opt.value,
                    text: opt.textContent.trim(),
                    selected: opt.selected
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
        
        options.forEach(opt => {
            const item = document.createElement('div');
            item.className = 'ss-option';
            item.style.cssText = `
                padding: 10px 14px; cursor: pointer; border-radius: 6px;
                font-size: 13px; transition: all 0.15s; margin: 2px 0;
            `;
            item.textContent = opt.text;
            item.dataset.value = opt.value;
            
            if (opt.value == this.original.value) {
                item.style.background = '#e3f2fd';
                item.style.color = '#0d47a1';
                item.style.fontWeight = '700';
            }
            
            item.onmouseenter = () => {
                item.style.background = '#f5f5f5';
            };
            item.onmouseleave = () => {
                if (item.dataset.value != this.original.value) {
                    item.style.background = '';
                } else {
                    item.style.background = '#e3f2fd';
                }
            };
            item.onclick = () => {
                this._select(opt);
            };
            
            this.optionsList.appendChild(item);
        });
    }
    
    _select(opt) {
        this.original.value = opt.value;
        this.display.innerHTML = `<span>${opt.text}</span><i class="bi bi-chevron-down" style="font-size: 10px; color: #b0bec5;"></i>`;
        this.display.style.borderColor = '#0d47a1';
        this.dropdown.style.display = 'none';
        this.original.dispatchEvent(new Event('change'));
    }
    
    _bindEvents() {
        // باز/بسته dropdown
        this.display.onclick = () => {
            const isOpen = this.dropdown.style.display === 'block';
            this.dropdown.style.display = isOpen ? 'none' : 'block';
            if (!isOpen) {
                this.searchInput.value = '';
                this.searchInput.focus();
                this._renderOptions(this.allOptions);
            }
        };
        
        // جستجو
        this.searchInput.oninput = () => {
            const q = this.searchInput.value.trim().toLowerCase();
            if (this.api && q.length >= this.minChars) {
                this._searchAPI(q);
            } else {
                const filtered = this.allOptions.filter(o => 
                    o.text.toLowerCase().includes(q)
                );
                this._renderOptions(filtered);
            }
        };
        
        // بستن با کلیک بیرون
        document.addEventListener('click', (e) => {
            if (!this.container.contains(e.target)) {
                this.dropdown.style.display = 'none';
            }
        });
        
        // کیبورد
        this.searchInput.onkeydown = (e) => {
            if (e.key === 'Escape') {
                this.dropdown.style.display = 'none';
            }
        };
    }
    
    _searchAPI(q) {
        // جستجوی AJAX
        fetch(`${this.api}?q=${encodeURIComponent(q)}`)
            .then(r => r.json())
            .then(data => {
                const options = data.map(item => ({
                    value: item.id,
                    text: item.name
                }));
                this._renderOptions(options);
            })
            .catch(() => {
                // fallback to local search
                const filtered = this.allOptions.filter(o => 
                    o.text.toLowerCase().includes(q)
                );
                this._renderOptions(filtered);
            });
    }
}

// ═══ مقداردهی خودکار ═══
document.addEventListener('DOMContentLoaded', () => {
    // تمام select هایی که کلاس searchable دارن
    document.querySelectorAll('select.searchable').forEach(sel => {
        new SearchableSelect(sel, {
            placeholder: sel.dataset.placeholder || 'جستجو کنید...',
            api: sel.dataset.api || null
        });
    });
    
    // تبدیل خودکار select های مرتبط
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
        'select[name="target_class_id"]',
    ];
    
    autoSelectors.forEach(selector => {
        document.querySelectorAll(selector).forEach(sel => {
            if (!sel.classList.contains('searchable') && sel.options.length > 5) {
                sel.classList.add('searchable');
                new SearchableSelect(sel, {
                    placeholder: 'جستجو و انتخاب کنید...'
                });
            }
        });
    });
});
