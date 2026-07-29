/**
 * تقویم شمسی — Jalali Date Picker v2 (Fixed)
 * الگوریتم تبدیل تست‌شده
 */

class JalaliPicker {
    constructor(input) {
        this.input = input;
        this.today = this._today();
        this.isOpen = false;
        this._reposition = () => this._position();
        
        // مقدار قبلی
        this.selY = this.today.y;
        this.selM = this.today.m;
        this.selD = this.today.d;
        
        this.initialValueWasGregorian = false;
        if (input.value) {
            const normalizedInitial = this._asciiDigits(String(input.value)).replace(/-/g, '/');
            const initialYear = Number(normalizedInitial.split('/')[0]);
            this.initialValueWasGregorian = initialYear > 1700;
            const p = this._parse(normalizedInitial);
            if (p) { this.selY = p.y; this.selM = p.m; this.selD = p.d; }
        }
        
        this.viewY = this.selY;
        this.viewM = this.selM;
        
        this._build();
        this._events();
    }
    
    // ═══ تاریخ امروز شمسی ═══
    _today() {
        const g = new Date();
        return this._g2j(g.getFullYear(), g.getMonth() + 1, g.getDate());
    }
    
    // ═══ میلادی → شمسی ═══
    _g2j(gy, gm, gd) {
        const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
        let gy2 = gm > 2 ? gy + 1 : gy;
        let days = 355666 + (365 * gy) + Math.floor((gy2 + 3) / 4) -
                   Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) +
                   gd + g_d_m[gm - 1];
        let jy = -1595 + (33 * Math.floor(days / 12053));
        days %= 12053;
        jy += 4 * Math.floor(days / 1461);
        days %= 1461;
        if (days > 365) {
            jy += Math.floor((days - 1) / 365);
            days = (days - 1) % 365;
        }
        let jm, jd;
        if (days < 186) {
            jm = 1 + Math.floor(days / 31);
            jd = 1 + (days % 31);
        } else {
            jm = 7 + Math.floor((days - 186) / 30);
            jd = 1 + ((days - 186) % 30);
        }
        return { y: jy, m: jm, d: jd };
    }
    
    // ═══ شمسی → میلادی ═══
    _j2g(jy, jm, jd) {
        jy += 1595;
        let days = -355668 + (365 * jy) + (Math.floor(jy / 33) * 8) +
                   Math.floor(((jy % 33) + 3) / 4) + jd +
                   (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
        let gy = 400 * Math.floor(days / 146097);
        days %= 146097;
        if (days > 36524) {
            days--;
            gy += 100 * Math.floor(days / 36524);
            days %= 36524;
            if (days >= 365) days++;
        }
        gy += 4 * Math.floor(days / 1461);
        days %= 1461;
        if (days > 365) {
            gy += Math.floor((days - 1) / 365);
            days = (days - 1) % 365;
        }
        let gd = days + 1;
        const ms = [0, 31, (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0 ? 29 : 28,
                    31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        let gm = 0;
        for (gm = 1; gm <= 12; gm++) {
            if (gd <= ms[gm]) break;
            gd -= ms[gm];
        }
        return { y: gy, m: gm, d: gd };
    }
    
    // ═══ تعداد روزهای ماه شمسی ═══
    _days(y, m) {
        if (m <= 6) return 31;
        if (m <= 11) return 30;

        // برای اسفند، تبدیل رفت‌وبرگشت از الگوی تقریبی ۳۳ ساله مطمئن‌تر است.
        const g = this._j2g(y, 12, 30);
        const j = this._g2j(g.y, g.m, g.d);
        return j.y === y && j.m === 12 && j.d === 30 ? 30 : 29;
    }
    
    // ═══ روز هفته اول ماه (0=شنبه) ═══
    _firstDay(jy, jm) {
        const g = this._j2g(jy, jm, 1);
        const d = new Date(g.y, g.m - 1, g.d);
        return (d.getDay() + 1) % 7;
    }
    
    // ═══ پردازش ورودی ═══
    _parse(s) {
        if (!s) return null;

        // ورودی با اعداد فارسی، عربی و انگلیسی پذیرفته می‌شود.
        s = this._asciiDigits(String(s).trim()).replace(/-/g, '/');
        const match = s.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
        if (!match) return null;

        const y = Number(match[1]);
        const m = Number(match[2]);
        const d = Number(match[3]);
        if (m < 1 || m > 12 || d < 1) return null;

        // value قدیمی input[type=date] میلادی است؛ برای نمایش به شمسی برگردانده می‌شود.
        if (y > 1700) {
            const maxGregorianDay = new Date(y, m, 0).getDate();
            if (d > maxGregorianDay) return null;
            return this._g2j(y, m, d);
        }

        if (y < 1200 || y > 1600 || d > this._days(y, m)) return null;
        return { y, m, d };
    }

    _asciiDigits(value) {
        return value
            .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
            .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)));
    }
    
    // ═══ عدد فارسی ═══
    _fa(n) {
        return String(n).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
    }
    
    // ═══ نام ماه ═══
    _mName(m) {
        return ['', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
                'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'][m] || '';
    }
    
    // ═══ ساخت پیکر ═══
    _build() {
        this.wrap = document.createElement('div');
        this.wrap.className = 'jalali-picker-wrapper';
        this.wrap.setAttribute('role', 'dialog');
        this.wrap.setAttribute('aria-label', 'تقویم شمسی');
        this.wrap.style.cssText = `
            position:fixed;top:0;left:0;right:auto;z-index:2147483000;
            background:#fff;border:1px solid #e0e4e8;
            border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.15);
            display:none;direction:rtl;width:300px;user-select:none;
            font-family:Vazirmatn,Tahoma,sans-serif;
        `;

        /*
         * قرار گرفتن popup داخل والد input باعث می‌شد overflow:hidden و transform
         * کارت‌ها آن را ببُرند یا زیر کارت بعدی نمایش دهند. Portal به body این
         * stacking-context را کاملاً دور می‌زند.
         */
        document.body.appendChild(this.wrap);

        // یک والد کوچک فقط دور خود input می‌سازیم تا آیکون با label جابه‌جا نشود.
        const currentParent = this.input.parentElement;
        if (currentParent && !currentParent.classList.contains('jalali-input-wrapper')) {
            this.inputHost = document.createElement('div');
            this.inputHost.className = 'jalali-input-wrapper';
            currentParent.insertBefore(this.inputHost, this.input);
            this.inputHost.appendChild(this.input);
        } else {
            this.inputHost = currentParent;
        }

        // آیکون
        this.icon = document.createElement('button');
        this.icon.type = 'button';
        this.icon.className = 'jp-input-icon';
        this.icon.tabIndex = -1;
        this.icon.setAttribute('aria-label', 'باز کردن تقویم شمسی');
        this.icon.innerHTML = '<i class="bi bi-calendar3" aria-hidden="true"></i>';
        if (this.inputHost) this.inputHost.appendChild(this.icon);

        // تنظیم input
        this.input.type = 'text';
        if (this.initialValueWasGregorian) {
            this.input.dataset.gregorian = this._asciiDigits(this.input.value).replace(/\//g, '-');
            this.input.value = `${this.selY}/${String(this.selM).padStart(2, '0')}/${String(this.selD).padStart(2, '0')}`;
        }
        this.input.classList.add('jalali-date');
        this.input.dataset.jalaliPickerInitialized = 'true';
        this.input.placeholder = '۱۴۰۵/۰۱/۱۶';
        this.input.style.paddingLeft = '42px';
        this.input.style.direction = 'ltr';
        this.input.style.textAlign = 'center';
        this.input.setAttribute('autocomplete', 'off');
        this.input.setAttribute('aria-haspopup', 'dialog');
        this.input.setAttribute('aria-expanded', 'false');

        this._render();
    }
    
    // ═══ رندر تقویم ═══
    _render() {
        const days = this._days(this.viewY, this.viewM);
        const start = this._firstDay(this.viewY, this.viewM);
        
        let h = '<div style="padding:12px">';
        
        // هدر
        h += `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">`;
        h += `<button type="button" class="jp-prev" style="background:none;border:none;font-size:20px;cursor:pointer;color:#0d47a1;padding:4px 8px;border-radius:6px">&#8249;</button>`;
        h += `<div style="display:flex;gap:6px;align-items:center">`;
        
        // سال
        h += `<select class="jp-year" style="border:1px solid #ddd;border-radius:6px;padding:4px 8px;font-family:Vazirmatn;font-size:12px">`;
        for (let y = this.today.y - 10; y <= this.today.y + 10; y++)
            h += `<option value="${y}" ${y === this.viewY ? 'selected' : ''}>${this._fa(y)}</option>`;
        h += `</select>`;
        
        // ماه
        h += `<select class="jp-month" style="border:1px solid #ddd;border-radius:6px;padding:4px 8px;font-family:Vazirmatn;font-size:12px">`;
        for (let m = 1; m <= 12; m++)
            h += `<option value="${m}" ${m === this.viewM ? 'selected' : ''}>${this._mName(m)}</option>`;
        h += `</select></div>`;
        
        h += `<button type="button" class="jp-next" style="background:none;border:none;font-size:20px;cursor:pointer;color:#0d47a1;padding:4px 8px;border-radius:6px">&#8250;</button>`;
        h += `</div>`;
        
        // روزهای هفته
        h += `<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin-bottom:4px">`;
        ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'].forEach((d, i) => {
            h += `<div style="text-align:center;font-size:11px;color:${i === 0 || i === 6 ? '#e74c3c' : '#546e7a'};font-weight:700;padding:4px">${d}</div>`;
        });
        h += `</div>`;
        
        // روزها
        h += `<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px">`;
        
        for (let i = 0; i < start; i++) h += `<div style="padding:8px"></div>`;
        
        for (let d = 1; d <= days; d++) {
            const sel = d === this.selD && this.viewM === this.selM && this.viewY === this.selY;
            const now = d === this.today.d && this.viewM === this.today.m && this.viewY === this.today.y;
            const dow = (start + d - 1) % 7;
            const fri = dow === 6;
            
            let bg = '', cl = '#37474f', fw = '400', bd = 'none';
            if (sel) { bg = '#0d47a1'; cl = '#fff'; fw = '700'; }
            else if (now) { bg = '#e3f2fd'; cl = '#0d47a1'; fw = '700'; bd = '1px solid #0d47a1'; }
            else if (fri) { cl = '#e74c3c'; }
            
            h += `<div class="jp-day" data-day="${d}" style="text-align:center;padding:8px 4px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:${fw};background:${bg};color:${cl};border:${bd};transition:all .15s">${this._fa(d)}</div>`;
        }
        
        h += `</div>`;
        
        // دکمه‌ها
        h += `<div style="display:flex;justify-content:space-between;margin-top:12px;padding-top:8px;border-top:1px solid #f0f0f0">`;
        h += `<button type="button" class="jp-today" style="background:#e3f2fd;color:#0d47a1;border:none;padding:6px 14px;border-radius:6px;font-size:12px;cursor:pointer;font-family:Vazirmatn;font-weight:600">امروز</button>`;
        h += `<button type="button" class="jp-clear" style="background:#ffebee;color:#c62828;border:none;padding:6px 14px;border-radius:6px;font-size:12px;cursor:pointer;font-family:Vazirmatn;font-weight:600">پاک کردن</button>`;
        h += `</div></div>`;
        
        this.wrap.innerHTML = h;
        this._bind();

        // ارتفاع ماه‌ها ممکن است فرق کند؛ بعد از هر رندر جای popup دوباره محاسبه شود.
        if (this.isOpen) requestAnimationFrame(() => this._position());
    }
    
    // ═══ رویدادها ═══
    _bind() {
        const $ = s => this.wrap.querySelector(s);
        const $$ = s => this.wrap.querySelectorAll(s);
        
        $('.jp-prev').onclick = e => {
            e.preventDefault();
            this.viewM--;
            if (this.viewM < 1) { this.viewM = 12; this.viewY--; }
            this._render();
        };
        
        $('.jp-next').onclick = e => {
            e.preventDefault();
            this.viewM++;
            if (this.viewM > 12) { this.viewM = 1; this.viewY++; }
            this._render();
        };
        
        $('.jp-year').onchange = e => { this.viewY = +e.target.value; this._render(); };
        $('.jp-month').onchange = e => { this.viewM = +e.target.value; this._render(); };
        
        $$('.jp-day').forEach(el => {
            el.onclick = () => {
                this.selY = this.viewY;
                this.selM = this.viewM;
                this.selD = +el.dataset.day;
                this._update();
                this._render();
                this.hide();
            };
            el.onmouseenter = () => { if (!el.style.background) el.style.background = '#f0f4f8'; };
            el.onmouseleave = () => { if (el.style.background === 'rgb(240, 244, 248)') el.style.background = ''; };
        });
        
        $('.jp-today').onclick = () => {
            this.selY = this.today.y; this.selM = this.today.m; this.selD = this.today.d;
            this.viewY = this.today.y; this.viewM = this.today.m;
            this._update(); this._render(); this.hide();
        };
        
        $('.jp-clear').onclick = () => {
            this.input.value = '';
            this.input.dataset.gregorian = '';
            this.input.dispatchEvent(new Event('input', { bubbles: true }));
            this.input.dispatchEvent(new Event('change', { bubbles: true }));
            this.hide();
        };
    }
    
    _events() {
        // focus قبل از click اجرا می‌شود؛ استفاده از show (نه toggle) جلوی بسته‌شدن فوری را می‌گیرد.
        this.input.addEventListener('click', () => this.show());
        this.input.addEventListener('focus', () => this.show());
        this.input.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                e.preventDefault();
                this.hide();
                this.input.blur();
            }
        });

        if (this.icon) {
            this.icon.addEventListener('click', e => {
                e.preventDefault();
                e.stopPropagation();
                this.show();
                this.input.focus({ preventScroll: true });
            });
        }

        document.addEventListener('click', e => {
            if (!this.wrap.contains(e.target) && e.target !== this.input && e.target !== this.icon)
                this.hide();
        });

        this.input.addEventListener('input', () => {
            let v = this._asciiDigits(this.input.value)
                .replace(/-/g, '/')
                .replace(/[^\d\/]/g, '')
                .slice(0, 10);
            this.input.value = v;
            const p = this._parse(v);
            if (p) {
                this.selY = p.y;
                this.selM = p.m;
                this.selD = p.d;
                this.viewY = p.y;
                this.viewM = p.m;
                if (this.isOpen) this._render();
            }
        });

        // position:fixed باید هنگام اسکرول هر نوع container و تغییر اندازه به‌روز شود.
        window.addEventListener('resize', this._reposition);
        window.addEventListener('scroll', this._reposition, true);
    }
    
    _update() {
        const y = String(this.selY);
        const m = String(this.selM).padStart(2, '0');
        const d = String(this.selD).padStart(2, '0');
        this.input.value = `${y}/${m}/${d}`;
        
        const g = this._j2g(this.selY, this.selM, this.selD);
        this.input.dataset.gregorian = `${g.y}-${String(g.m).padStart(2, '0')}-${String(g.d).padStart(2, '0')}`;
        this.input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    _position() {
        if (!this.isOpen) return;

        const rect = this.input.getBoundingClientRect();
        const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
        const viewportHeight = document.documentElement.clientHeight || window.innerHeight;
        const margin = viewportWidth <= 360 ? 4 : 8;
        const gap = 6;

        // اگر input کاملاً از viewport خارج شد popup باز باقی نماند.
        if (rect.bottom < 0 || rect.top > viewportHeight || rect.right < 0 || rect.left > viewportWidth) {
            this.hide();
            return;
        }

        const width = Math.min(300, viewportWidth - (margin * 2));
        this.wrap.style.width = `${width}px`;
        this.wrap.style.maxHeight = `${Math.max(120, viewportHeight - (margin * 2))}px`;

        const pickerHeight = this.wrap.offsetHeight;
        const spaceBelow = viewportHeight - rect.bottom - margin;
        const spaceAbove = rect.top - margin;
        const openAbove = spaceBelow < pickerHeight + gap && spaceAbove > spaceBelow;

        let top = openAbove ? rect.top - pickerHeight - gap : rect.bottom + gap;
        top = Math.max(margin, Math.min(top, viewportHeight - pickerHeight - margin));

        // در RTL لبه راست popup با لبه راست input هم‌راستا می‌شود.
        let left = rect.right - width;
        left = Math.max(margin, Math.min(left, viewportWidth - width - margin));

        this.wrap.style.top = `${Math.round(top)}px`;
        this.wrap.style.left = `${Math.round(left)}px`;
    }
    
    show() {
        if (this.input.disabled || this.input.readOnly) return;
        if (JalaliPicker.active && JalaliPicker.active !== this) JalaliPicker.active.hide();

        JalaliPicker.active = this;
        this.isOpen = true;
        this.wrap.style.display = 'block';
        this.input.setAttribute('aria-expanded', 'true');
        this._render();
        this._position();
    }

    hide() {
        this.isOpen = false;
        this.wrap.style.display = 'none';
        this.input.setAttribute('aria-expanded', 'false');
        if (JalaliPicker.active === this) JalaliPicker.active = null;
    }

    toggle() { this.isOpen ? this.hide() : this.show(); }
}

// ═══ مقداردهی خودکار ═══
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.jalali-date, input[type="date"]').forEach(input => {
        if (input.dataset.jalaliPickerInitialized !== 'true') new JalaliPicker(input);
    });
});
