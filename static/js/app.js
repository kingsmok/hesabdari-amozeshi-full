/* ═══════════════════════════════════════════════════════════════
   فایل اصلی JavaScript — Academy Manager Pro
   ═══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', function() {
    
    // ═══ ۱) انیمیشن ورود عناصر هنگام اسکرول ═══
    initScrollReveal();
    
    // ═══ ۲) شمارش اعداد (Count Up) ═══
    initCountUp();
    
    // ═══ ۳) انیمیشن سایدبار ═══
    initSidebar();
    
    // ═══ ۴) جستجوی سراسری ═══
    initGlobalSearch();
    
    // ═══ ۵) Dark Mode ═══
    initDarkMode();
    
    // ═══ ۶) میانبرهای صفحه‌کلید ═══
    initKeyboardShortcuts();
    
    // ═══ ۷) تولتیپ‌ها ═══
    initTooltips();
    
    // ═══ ۸) تأیید حذف ═══
    initDeleteConfirm();
    
    // ═══ ۹) ذخیره خودکار فرم‌ها ═══
    initAutoSave();
    
    // ═══ ۱۰) انیمیشن نمودارها ═══
    initChartAnimations();
    
    // ═══ ۱۱) پاپ‌آورها ═══
    initPopovers();
    
    // ═══ ۱۲) ساعت زنده ═══
    initLiveClock();

    // ═══ ۱۳) تجربه موبایل / شبکه ═══
    safeInit(initMobileUX, 'mobile-ux');

    // ═══ ۱۴) ورودی‌های عددی: ارقام فارسی، جداکننده هزارگان، enterkeyhint ═══
    safeInit(initNumericInputs, 'numeric-inputs');

    // ═══ ۱۵) لیبل‌های بی‌for + کلیک‌های قابل‌دسترس با کیبورد ═══
    safeInit(initLabelTargets, 'label-targets');
    safeInit(initClickableA11y, 'clickable-a11y');

    // ═══ ۱۶) Service Worker (PWA آفلاینِ استاتیک) ═══
    safeInit(registerServiceWorker, 'service-worker');

    console.log('✅ Academy Manager Pro — JS loaded');
});


/* ═══════════════════════════════════════════════════════════════
   ۱) انیمیشن ورود عناصر هنگام اسکرول
   ═══════════════════════════════════════════════════════════════ */
function initScrollReveal() {
    const elements = document.querySelectorAll('.stat-box, .card, .table');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.classList.add('anim-fade-up');
                    entry.target.style.opacity = '1';
                }, index * 50);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });
    
    elements.forEach(el => {
        el.style.opacity = '0';
        observer.observe(el);
    });
}


/* ═══════════════════════════════════════════════════════════════
   ۲) شمارش اعداد (Count Up Animation)
   ═══════════════════════════════════════════════════════════════ */
function initCountUp() {
    const counters = document.querySelectorAll('.stat-val');
    
    counters.forEach(counter => {
        const text = counter.textContent.trim();
        const numMatch = text.match(/[\d,]+/);
        
        if (numMatch) {
            const target = parseInt(numMatch[0].replace(/,/g, ''));
            if (target > 0 && target < 1000000000) {
                counter.textContent = '0';
                animateCounter(counter, target, text);
            }
        }
    });
}

function animateCounter(element, target, originalText) {
    const duration = 1000;
    const steps = 30;
    const stepTime = duration / steps;
    let current = 0;
    const increment = target / steps;
    
    const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
            clearInterval(timer);
            element.textContent = originalText;
        } else {
            const formatted = Math.floor(current).toLocaleString('fa-IR');
            // حفظ واحدهای اضافی مثل «تومان»
            const suffix = originalText.replace(/[\d,]+/, '').trim();
            element.textContent = formatted + (suffix ? ' ' + suffix : '');
        }
    }, stepTime);
}


/* ═══════════════════════════════════════════════════════════════
   ۳) مدیریت سایدبار
   ═══════════════════════════════════════════════════════════════ */
function initSidebar() {
    // باز/بسته زیرمنوها با انیمیشن
    document.querySelectorAll('.nav-link-item[onclick]').forEach(item => {
        item.addEventListener('click', function() {
            const sub = this.nextElementSibling;
            if (sub && sub.classList.contains('nav-sub')) {
                // بستن سایر زیرمنوها
                document.querySelectorAll('.nav-sub.show').forEach(openSub => {
                    if (openSub !== sub) {
                        openSub.classList.remove('show');
                        openSub.previousElementSibling.classList.remove('open');
                    }
                });
            }
        });
    });
    
    // ذخیره وضعیت سایدبار
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        const isMobile = window.innerWidth <= 992;
        if (!isMobile) {
            const savedState = localStorage.getItem('sidebar_collapsed');
            if (savedState === 'true') {
                sidebar.style.width = '0';
                document.getElementById('mainWrap').style.marginRight = '0';
            } else {
                sidebar.style.width = 'var(--sidebar-w)';
                document.getElementById('mainWrap').style.marginRight = 'var(--sidebar-w)';
            }
        } else {
            // روی موبایل فقط حالت باز/بسته با کلاس open کنترل می‌شود
            sidebar.classList.remove('open');
            sidebar.style.width = 'var(--sidebar-w)';
        }
    }
    // بستن سایدبار با کلیک روی اورلی / لینک / Escape
    window.addEventListener('resize', function() {
        if (window.innerWidth > 992) {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('mobileOverlay');
            if (overlay) overlay.classList.remove('visible');
            document.body.style.overflow = '';
            if (sidebar) {
                sidebar.classList.remove('open');
                sidebar.style.width = '';
            }
            const mainWrap = document.getElementById('mainWrap');
            if (mainWrap) mainWrap.style.marginRight = '';
        }
    });

    document.querySelectorAll('.sidebar a.nav-link-item').forEach(function(link) {
        link.addEventListener('click', function() {
            if (window.innerWidth <= 992) {
                closeMobileSidebar();
            }
        });
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeMobileSidebar();
    });
}

function closeMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobileOverlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('visible');
    document.body.style.overflow = '';
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainWrap = document.getElementById('mainWrap');
    const overlay = document.getElementById('mobileOverlay');
    const isMobile = window.innerWidth <= 992;

    if (isMobile) {
        const isOpen = sidebar.classList.contains('open');
        if (isOpen) {
            sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('visible');
            document.body.style.overflow = '';
        } else {
            sidebar.classList.add('open');
            if (overlay) overlay.classList.add('visible');
            document.body.style.overflow = 'hidden';
        }
    } else {
        const collapsed = localStorage.getItem('sidebar_collapsed') === 'true';
        const currentlyCollapsed = sidebar.style.width === '0px' || sidebar.style.width === '0';
        if (collapsed || currentlyCollapsed) {
            sidebar.style.width = 'var(--sidebar-w)';
            mainWrap.style.marginRight = 'var(--sidebar-w)';
            localStorage.setItem('sidebar_collapsed', 'false');
        } else {
            sidebar.style.width = '0';
            mainWrap.style.marginRight = '0';
            localStorage.setItem('sidebar_collapsed', 'true');
        }
    }
}

function toggleNav(el) {
    el.classList.toggle('open');
    const sub = el.nextElementSibling;
    if (sub && sub.classList.contains('nav-sub')) {
        sub.classList.toggle('show');
    }
}


/* ═══════════════════════════════════════════════════════════════
   ۴) جستجوی سراسری
   ═══════════════════════════════════════════════════════════════ */
let searchTimer;

function initGlobalSearch() {
    const input = document.getElementById('globalSearch');
    if (!input) return;
    
    input.addEventListener('input', function() {
        globalSearch(this.value);
    });
    
    // بستن نتایج با کلیک بیرون
    document.addEventListener('click', e => {
        const results = document.getElementById('searchResults');
        if (results && !e.target.closest('#globalSearch') && !e.target.closest('#searchResults')) {
            results.style.display = 'none';
        }
    });
    
    // بستن با Escape
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.getElementById('searchResults').style.display = 'none';
            this.blur();
        }
    });
}

// شماره‌ی توالی + AbortController: پاسخِ دیرِ جستجوی قبلی، نتیجه‌ی جدید را
// بازنویسی نمی‌کند (باگ race در ورودی سریع کاربر)
let searchAbort = null;
let searchSeq = 0;

function globalSearch(q) {
    clearTimeout(searchTimer);
    const box = document.getElementById('searchResults');
    if (!box) return;
    
    if (q.length < 2) { box.style.display = 'none'; return; }
    
    // نمایش لودینگ
    box.innerHTML = '<div style="padding: 16px; text-align: center;"><div class="spinner-border spinner-border-sm text-primary" role="status"></div></div>';
    box.style.display = 'block';
    
    searchTimer = setTimeout(() => {
        const seq = ++searchSeq;
        if (searchAbort) searchAbort.abort();
        searchAbort = new AbortController();
        fetch('/api/search?q=' + encodeURIComponent(q), { signal: searchAbort.signal })
            .then(r => {
                if (!r.ok) throw new Error('search-failed');
                return r.json();
            })
            .then(data => {
                if (seq !== searchSeq) return;   // پاسخ قدیمی است؛ دور ریخته می‌شود
                if (data.results.length === 0) {
                if (data.results.length === 0) {
                    box.innerHTML = '<div style="padding: 16px; text-align: center; color: #b0bec5; font-size: 12px;">نتیجه‌ای یافت نشد</div>';
                } else {
                    box.innerHTML = data.results.map((r, i) =>
                        `<a href="${escapeHtml(r.url || '#')}" style="display: flex; align-items: center; gap: 10px; padding: 10px 14px; text-decoration: none; color: #37474f; border-bottom: 1px solid #f5f5f5; animation: fadeInUp 0.3s ease-out ${i * 0.05}s both;">
                            <span style="background: ${escapeHtml(r.color || '#e3f2fd')}; padding: 2px 8px; border-radius: 4px; font-size: 10px; color: #fff;">${escapeHtml(r.type || '')}</span>
                            <span style="font-weight: 600; font-size: 12px;">${escapeHtml(r.name || '')}</span>
                            <span style="font-size: 10px; color: #b0bec5;">${escapeHtml(r.detail || '')}</span>
                        </a>`
                    ).join('');
                }
                box.style.display = 'block';
            })
            .catch(() => {
                box.innerHTML = '<div style="padding: 16px; text-align: center; color: #c62828; font-size: 12px;">خطا در جستجو</div>';
            });
    }, 300);
}


/* ═══════════════════════════════════════════════════════════════
   ۵) Dark Mode
   ═══════════════════════════════════════════════════════════════ */
function initDarkMode() {
    const darkMode = getCookie('dark_mode');
    if (darkMode === 'on') {
        document.body.classList.add('dark-mode');
    }
}

function toggleDarkMode() {
    fetch('/api/dark-mode', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCSRFToken() }
    })
    .then(r => r.json())
    .then(data => {
        if (data.dark_mode === 'on') {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
    })
    .catch(() => {
        // خطای شبکه نباید UI را بی‌پاسخ بگذارد؛ حالت محلی را برعکس می‌کنیم
        const isOn = document.body.classList.toggle('dark-mode');
        setCookie('dark_mode', isOn ? 'on' : 'off', 365);
    });
}

// ذخیرهٔ کوکی (برای حالت آفلاینِ dark-mode بدون سرور)
function setCookie(name, value, days) {
    const expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = `${name}=${value}; expires=${expires}; path=/; SameSite=Lax`;
}


/* ═══════════════════════════════════════════════════════════════
   ۶) میانبرهای صفحه‌کلید
   ═══════════════════════════════════════════════════════════════ */
function initKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Ctrl+K = جستجو
        if (e.ctrlKey && e.key === 'k') {
            e.preventDefault();
            const search = document.getElementById('globalSearch');
            if (search) search.focus();
        }
        
        // Ctrl+N = هنرجو جدید
        if (e.ctrlKey && e.key === 'n') {
            e.preventDefault();
            window.location.href = '/students/add';
        }
        
        // Ctrl+D = داشبورد
        if (e.ctrlKey && e.key === 'd') {
            e.preventDefault();
            window.location.href = '/';
        }
        
        // Ctrl+R = ثبت‌نام
        if (e.ctrlKey && e.key === 'r') {
            e.preventDefault();
            window.location.href = '/registration/add';
        }
        
        // Escape = بستن مودال
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.show').forEach(modal => {
                bootstrap.Modal.getInstance(modal)?.hide();
            });
        }
    });
}


/* ═══════════════════════════════════════════════════════════════
   ۷) تولتیپ‌ها
   ═══════════════════════════════════════════════════════════════ */
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(el => new bootstrap.Tooltip(el));
}


/* ═══════════════════════════════════════════════════════════════
   ۸) تأیید حذف
   ═══════════════════════════════════════════════════════════════ */
function initDeleteConfirm() {
    document.querySelectorAll('[data-confirm]').forEach(el => {
        el.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm') || 'آیا مطمئن هستید؟';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}


/* ═══════════════════════════════════════════════════════════════
   ۹) ذخیره خودکار فرم‌ها
   ═══════════════════════════════════════════════════════════════ */
function initAutoSave() {
    document.querySelectorAll('form[data-autosave]').forEach(form => {
        const key = form.getAttribute('data-autosave');
        
        // بازیابی داده‌های ذخیره شده
        const saved = localStorage.getItem('autosave_' + key);
        if (saved) {
            try {
                const data = JSON.parse(saved);
                for (const [name, value] of Object.entries(data)) {
                    const input = form.querySelector(`[name="${name}"]`);
                    if (input) input.value = value;
                }
            } catch (e) {}
        }
        
        // ذخیره خودکار هنگام تایپ
        form.addEventListener('input', debounce(() => {
            const data = {};
            new FormData(form).forEach((value, name) => {
                data[name] = value;
            });
            localStorage.setItem('autosave_' + key, JSON.stringify(data));
        }, 500));
        
        // پاک کردن بعد از ارسال
        form.addEventListener('submit', () => {
            localStorage.removeItem('autosave_' + key);
        });
    });
}


/* ═══════════════════════════════════════════════════════════════
   ۱۰) انیمیشن نمودارها
   ═══════════════════════════════════════════════════════════════ */
function initChartAnimations() {
    // تنظیمات پیش‌فرض Chart.js
    if (typeof Chart !== 'undefined') {
        Chart.defaults.animation = {
            duration: 1500,
            easing: 'easeOutQuart'
        };
        Chart.defaults.font.family = 'Vazirmatn, Tahoma, sans-serif';
        Chart.defaults.plugins.legend.labels.usePointStyle = true;
    }
}


/* ═══════════════════════════════════════════════════════════════
   ۱۱) پاپ‌آورها
   ═══════════════════════════════════════════════════════════════ */
function initPopovers() {
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(el => new bootstrap.Popover(el));
}


/* ═══════════════════════════════════════════════════════════════
   ۱۲) ساعت زنده
   ═══════════════════════════════════════════════════════════════ */
function initLiveClock() {
    const clockEl = document.getElementById('liveClock');
    const dateEl = document.getElementById('liveJalaliDate');
    
    function updateClock() {
        const now = new Date();
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        if (clockEl) clockEl.textContent = `${hours}:${minutes}:${seconds}`;
    }
    
    function updateJalaliDate() {
        if (!dateEl) return;
        const now = new Date();
        // تبدیل میلادی به شمسی
        const jalali = gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
        const weekdays = ['یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه', 'شنبه'];
        const months = ['', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
        const weekday = weekdays[now.getDay()];
        dateEl.textContent = `${weekday}، ${jalali[2]} ${months[jalali[1]]} ${jalali[0]}`;
    }
    
    updateClock();
    updateJalaliDate();
    setInterval(updateClock, 1000);
    // بروزرسانی تاریخ هر دقیقه
    setInterval(updateJalaliDate, 60000);
}

// تبدیل میلادی به شمسی (محاسباتی)
function gregorianToJalali(gy, gm, gd) {
    var g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    var gy2 = (gm > 2) ? (gy + 1) : gy;
    var days = 355666 + (365 * gy) + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) + gd + g_d_m[gm - 1];
    var jy = -1595 + (33 * Math.floor(days / 12053));
    days %= 12053;
    jy += 4 * Math.floor(days / 1461);
    days %= 1461;
    if (days > 365) {
        jy += Math.floor((days - 1) / 365);
        days = (days - 1) % 365;
    }
    var jm, jd;
    if (days < 186) {
        jm = 1 + Math.floor(days / 31);
        jd = 1 + (days % 31);
    } else {
        jm = 7 + Math.floor((days - 186) / 30);
        jd = 1 + ((days - 186) % 30);
    }
    return [jy, jm, jd];
}


/* ═══════════════════════════════════════════════════════════════
   ۱۳) موبایل: جداول اسکرول‌پذیر، منوی کاربر با لمس
   ═══════════════════════════════════════════════════════════════ */
function initMobileUX() {
    wrapTablesForMobile();
    initUserMenuTouch();

    // جداولی که بعداً با fetch تزریق می‌شوند (سریع‌جستجو، مودال‌ها، خروجی
    // گزارش‌ها) قبلاً بدون اسکرول می‌ماندند؛ یک MutationObserver کافی است
    var main = document.querySelector('.main-wrap, .content, main') || document.body;
    if (window.MutationObserver) {
        var schedule = null;
        new MutationObserver(function() {
            if (schedule) return;
            schedule = requestAnimationFrame(function() {
                schedule = null;
                wrapTablesForMobile();
            });
        }).observe(main, { childList: true, subtree: true });
    }
}

function wrapTablesForMobile() {
    // جداول لیست‌ها (شهریه، اقساط، حقوق) روی موبایل از قاب بیرون می‌زدند؛
    // برخی قالب‌ها .table-responsive دارند و بعضی نه — اینجا پوشش کامل می‌شود.
    document.querySelectorAll('table').forEach(function(table) {
        if (table.closest('.table-responsive')) return;
        if (table.closest('td, th')) return;          // جدول تودرتو ⇒ دست نزن
        if (table.closest('.jalali-picker, .ss-dropdown')) return;
        if (table.classList.contains('table-nowrap-mobile')) return;
        var wrap = document.createElement('div');
        wrap.className = 'table-responsive table-wrap-mobile';
        table.parentNode.insertBefore(wrap, table);
        wrap.appendChild(table);
    });
}

function initUserMenuTouch() {
    var chip = document.getElementById('userChip') || document.querySelector('.user-chip');
    if (!chip) return;

    chip.addEventListener('click', function(e) {
        if (e.target.closest('.user-dropdown a')) return;
        if (window.matchMedia('(hover: hover) and (pointer: fine)').matches && window.innerWidth > 992) {
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        chip.classList.toggle('show-menu');
    });

    document.addEventListener('click', function(e) {
        if (!e.target.closest('.user-chip')) {
            chip.classList.remove('show-menu');
        }
    });
}


/* ═══════════════════════════════════════════════════════════════
   توابع کمکی
   ═══════════════════════════════════════════════════════════════ */

// فرمت عدد فارسی
function fmtNum(n) {
    return new Intl.NumberFormat('fa-IR').format(n);
}

// فرمت ارزی
function fmtCurrency(n) {
    return new Intl.NumberFormat('fa-IR', { 
        style: 'decimal', 
        maximumFractionDigits: 0 
    }).format(n) + ' تومان';
}

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Debounce
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// دریافت CSRF Token
function getCSRFToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    
    const input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;
    
    return '';
}

// دریافت کوکی
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}

// نمایش Toast
function showToast(message, type = 'success') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        const container = document.createElement('div');
        container.id = 'toastContainer';
        container.style.cssText = 'position: fixed; top: 20px; left: 20px; z-index: 9999;';
        document.body.appendChild(container);
    }
    
    const colors = {
        success: '#2e7d32',
        error: '#c62828',
        warning: '#ff8f00',
        info: '#1565c0'
    };
    
    const icons = {
        success: 'check-circle',
        error: 'x-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };
    
    const toast = document.createElement('div');
    toast.style.cssText = `
        background: ${colors[type] || colors.info};
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        margin-bottom: 8px;
        font-size: 13px;
        font-family: Vazirmatn, Tahoma;
        display: flex;
        align-items: center;
        gap: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        animation: fadeInLeft 0.3s ease-out;
        direction: rtl;
    `;
    toast.innerHTML = `<i class="bi bi-${icons[type]}"></i> ${message}`;
    
    document.getElementById('toastContainer').appendChild(toast);
    
    setTimeout(() => {
        toast.style.transition = 'all 0.3s';
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(-20px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// فرمت تاریخ شمسی
function toJalali(dateStr) {
    // ساده — فقط نمایش
    return dateStr;
}

// انیمیشن حذف ردیف جدول
function animateRowDelete(row) {
    row.style.transition = 'all 0.3s';
    row.style.opacity = '0';
    row.style.transform = 'translateX(20px)';
    setTimeout(() => row.remove(), 300);
}

// انیمیشن اضافه کردن ردیف
function animateRowAdd(row) {
    row.style.opacity = '0';
    row.style.transform = 'translateX(-20px)';
    requestAnimationFrame(() => {
        row.style.transition = 'all 0.3s';
        row.style.opacity = '1';
        row.style.transform = 'translateX(0)';
    });
}

// کپی به کلیپ‌بورد
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('کپی شد!', 'success');
    }).catch(() => {
        // fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('کپی شد!', 'success');
    });
}


/* ═══════════════════════════════════════════════════════════════
   ۱۴) ورودی‌های عددی و پولی
   ───────────────────────────────────────────────────────────────
   ۹۷ ورودی type="number" در قالب‌ها بود و هیچ inputmode/enterkeyhintی نداشت:
   الف) type="number" ارقام فارسی را «مقدار نامعتبر» می‌کند ⇒ فرم بی‌صدا
      submit نمی‌شد (کاربر ایرانی ۵۰۰۰۰۰ را با ارقام فارسی تایپ می‌کند)؛
   ب) روی موبایل کیبورد عددی درست باز نمی‌شد و کلید «بعدی» کار نمی‌کرد.
   اینجا بدون دست‌زدن به قالب‌ها حل می‌شود: نوع به text+inputmode تبدیل و
   ارقام فارسی/جداکننده‌ها نرمال می‌گردند. سمت سرور هم همان منع را دارد
   (utils/form_helpers.parse_number)، پس JS فقط بهبود است نه تنها راه.
   ═══════════════════════════════════════════════════════════════ */

var FA_DIGITS = {
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
};

function toLatinDigits(text) {
    // هر دو مجموعه رقم: فارسی ۰-۹ (U+06F0..) و عربی ٠-٩ (U+0660..) — کیبورد
    // «Arabic» اندروید گروه دوم را تولید می‌کند.
    return String(text == null ? '' : text).replace(/[\u06f0-\u06f9\u0660-\u0669]/g, function(ch) {
        return FA_DIGITS[ch] || ch;
    });
}

// تبدیل رشته‌ای مثل «۱۲,۵۰,۰۰۰» یا «12.500.000» به عدد (یا خالی اگر نامعتبر)
function parseGroupedNumber(text) {
    var raw = (text === undefined || text === null) ? '' : String(text);
    var clean = toLatinDigits(raw)
        .replace(/[\s\u200e\u200f_]/g, '')
        .replace(/\u066B/g, '.')                       // ٫ ممیز فارسی
        .replace(/[\u060C\u066C\u064C]/g, ',');      // ٬ و ، ویرگول فارسی/عربی
    if (!clean) return '';

    var negative = /^[\u2212-]/.test(clean);            // − یا -
    clean = clean.replace(/^[\u2212-]/, '');

    var lastComma = clean.lastIndexOf(',');
    var lastDot = clean.lastIndexOf('.');
    if (lastComma !== -1 && lastDot !== -1) {
        // هر دو علامت هست ⇒ آن که آخر آمده جداکننده اعشار است، بقیه هزارگان
        if (lastDot > lastComma) {
            clean = clean.replace(/,/g, '');            // 1,200.50
        } else {
            clean = clean.replace(/\./g, '').replace(/,/g, '.');   // 1.200,50
        }
    } else if (lastComma !== -1) {
        var parts = clean.split(',');
        var isGrouping = parts.length > 1 && parts[0].length <= 3 &&
            parts.slice(1).every(function (group) { return /^[0-9]{3}$/.test(group); });
        // «1,200,000» ⇒ هزارگان؛  «12,5» ⇒ ممیزِ دستی کاربر فارسی‌زبان
        clean = isGrouping ? parts.join('') : parts.join('.');
    }

    var dot = clean.indexOf('.');
    var intPart = (dot === -1 ? clean : clean.slice(0, dot)).replace(/[^0-9]/g, '');
    var fracPart = dot === -1 ? '' : clean.slice(dot + 1).replace(/[^0-9]/g, '');
    if (!intPart && !fracPart) return '';

    var value = parseFloat((intPart || '0') + (fracPart ? '.' + fracPart : ''));
    if (!isFinite(value)) return '';
    return (negative ? '-' : '') + String(value);
}

function formatGroupedNumber(value) {
    if (value === '' || value === null || value === undefined) return '';
    var numeric = Number(String(value).replace(/,/g, ''));
    if (isNaN(numeric)) return String(value);
    var split = String(numeric).split('.');
    split[0] = split[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return split.join('.');
}

function isNumericish(input) {
    if (!input || input.tagName !== 'INPUT') return false;
    var mode = (input.getAttribute('inputmode') || '').toLowerCase();
    return input.type === 'number' || mode === 'numeric' || mode === 'decimal' ||
        input.classList.contains('money') || input.dataset.money !== undefined;
}

/* «۱۲٬۵۰۰٬۰۰۰ تومان» زیر فیلد — خواندن مرتبه عدد روی موبایل را راحت می‌کند؛
   فقط نمایشی است و به مقدار فرم دست نمی‌زند (no-print تا چاپ نشود). */
function updateMoneyEcho(input) {
    if (!input || !input.dataset || input.dataset.money === undefined) return;
    var echo = input.parentNode && input.parentNode.querySelector(':scope > .money-echo');
    var parsed = parseGroupedNumber(input.value);
    if (parsed === '') {
        if (echo) echo.textContent = '';
        return;
    }
    var grouped = formatGroupedNumber(parsed);
    if (!grouped) return;
    var unit = /rial|ریال/i.test((input.name || '') + (input.dataset.unit || '')) ? ' ریال' : ' تومان';
    if (!echo) {
        echo = document.createElement('span');
        echo.className = 'money-echo no-print';
        (input.parentNode || input).appendChild(echo);
    }
    echo.textContent = grouped + unit;
}

function initNumericInputs() {
    // الف) type="number" → text + inputmode؛ مقدار حفظ می‌شود
    document.querySelectorAll('input[type="number"]').forEach(function(input) {
        var min = input.getAttribute('min');
        var max = input.getAttribute('max');
        var step = input.getAttribute('step');
        try { input.type = 'text'; } catch (e) { return; }
        var isDecimal = step && (step.indexOf('.') !== -1 || step === 'any');
        input.setAttribute('inputmode', isDecimal ? 'decimal' : 'numeric');
        input.classList.add('num-input');
        if (min !== null) input.dataset.min = min;
        if (max !== null) input.dataset.max = max;
        if (step !== null) input.dataset.step = step;
        if (min !== null && Number(min) >= 0) input.dataset.noNegative = '1';
        // نوع فیلد را نگه می‌داریم تا فرم همچنان داده درست بفرستد
        input.dataset.numeric = '1';
    });

    // ب) enterkeyhint خودکار: در هر فرم، «بعدی» روی همه و «پایان» روی آخرین فیلد
    document.querySelectorAll('form').forEach(function(form) {
        var fields = Array.prototype.filter.call(form.querySelectorAll(
            'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]), select, textarea:not([readonly])'),
            function(el) { return !el.disabled && el.offsetParent !== null; });
        if (fields.length < 2) return;
        fields.forEach(function(el, index) {
            if (el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') return;
            if (el.hasAttribute('enterkeyhint')) return;
            el.setAttribute('enterkeyhint', index === fields.length - 1 ? 'done' : 'next');
        });
    });

    // پ) نرمال‌سازی رقم در حین تایپ و چسباندن
    document.addEventListener('input', function(event) {
        var input = event.target;
        if (!isNumericish(input)) return;
        var raw = input.value;
        // ۱) ارقام فارسی/عربی → لاتین   ۲) ٫ → .   ۳) ویرگول = هزارگان ⇒ حذف
        // (قبلاً همان مرحله ۳ همه‌چیزِ غیررقم را با regex پاک می‌کرد و «۱۲٫۵»
        //  به «۱۲۵» تبدیل می‌شد — یعنی اعشارِ تایپ‌شده وسط کار از دست می‌رفت)
        var clean = toLatinDigits(raw)
            .replace(/\u066B/g, '.')
            .replace(/,/g, '')
            .replace(/[^0-9.\-]/g, '');
        // فقط یک نقطه اعشار و یک منفیِ ابتدایی
        var dotAt = clean.indexOf('.');
        if (dotAt !== -1) {
            clean = clean.slice(0, dotAt + 1) + clean.slice(dotAt + 1).replace(/\./g, '');
        }
        if (clean.indexOf('-') !== -1) {
            clean = '-' + clean.replace(/-/g, '');
        }
        if (input.dataset.noNegative === '1') clean = clean.replace(/-/g, '');
        // تعداد رقم اعشار را مطابق step محدود می‌کنیم (step=0.01 ⇒ دو رقم)
        var step = input.dataset.step || '';
        var stepMatch = step.match(/^0*\.(\d+)$/);
        if (stepMatch && clean.indexOf('.') !== -1) {
            var allowed = stepMatch[1].length;
            var pos = clean.indexOf('.');
            clean = clean.slice(0, pos + 1 + allowed);
        }
        if (clean !== raw) {
            input.value = clean;
            // خطای native «Please enter a number» را پاک می‌کنیم
            if (input.setCustomValidity) input.setCustomValidity('');
            updateMoneyEcho(input);
        }
    }, true);

    document.addEventListener('paste', function(event) {
        var input = event.target;
        if (!isNumericish(input)) return;
        var text = (event.clipboardData || window.clipboardData).getData('text');
        var parsed = parseGroupedNumber(text);
        if (parsed !== '') {
            event.preventDefault();
            input.value = input.value.slice(0, input.selectionStart) + parsed +
                input.value.slice(input.selectionEnd);
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }, true);

    // ت) در blur: نرمال‌سازی نهایی + رعایت min/max.
    //    عمداً جداکننده هزارگان داخل value نمی‌گذاریم: در همین پروژه ده‌ها
    //    اسکریپت inline با parseFloat(input.value) جمع کل را حساب می‌کنند و
    //    «1,200» را ۱ می‌خوانند ⇒ مبلغ خرد می‌شد. عدد خام می‌ماند؛ قرت‌پذیری
    //    با tabular-nums و راست‌چین کردن انجام می‌شود.
    document.addEventListener('blur', function(event) {
        var input = event.target;
        if (!isNumericish(input)) return;
        var parsed = parseGroupedNumber(input.value);
        if (parsed === '') { input.value = ''; return; }
        var value = Number(parsed);
        if (isNaN(value)) { input.value = ''; return; }
        if (input.dataset.noNegative === '1' && value < 0) value = Math.abs(value);
        if (input.dataset.min !== undefined && value < Number(input.dataset.min)) value = Number(input.dataset.min);
        if (input.dataset.max !== undefined && value > Number(input.dataset.max)) value = Number(input.dataset.max);
        input.value = String(value);
        updateMoneyEcho(input);
    }, true);

    // ث) پیش از submit، مبالغ جداکننده‌دار به عدد خام تبدیل شوند
    document.addEventListener('submit', function(event) {
        var form = event.target;
        if (!form || !form.querySelectorAll) return;
        form.querySelectorAll('input').forEach(function(input) {
            if (!isNumericish(input) || input.value === '' || input.dataset.money === undefined) return;
            var parsed = parseGroupedNumber(input.value);
            if (parsed !== '') input.value = parsed;
        });
    });

    // ج) کلاس .money برای فیلدهای پولی — نام، id، placeholder و <label> بررسی
    //    می‌شود؛ سال/نسبت/درصد/ماه استثنا هستند (جداکننده هزارگان معنا ندارد)
    var MONEY_RE = /amount|price|fee|cost|debt|credit|money|toman|rial|salary|wage|total|mablag|hazine|پرداخت|مبلغ|هزینه|قیمت|حقوق|بدهی|مانده|بودجه/;
    var NOT_MONEY_RE = /year|month|percent|ratio|score|count|number_of|days|sal|mah|درصد|سال|تعداد|روز/;
    document.querySelectorAll('input').forEach(function(input) {
        if (!isNumericish(input)) return;
        var label = '';
        if (input.id) {
            var labelEl = document.querySelector('label[for="' + input.id + '"]');
            if (labelEl) label = labelEl.textContent || '';
        }
        var hint = ((input.name || '') + ' ' + (input.id || '') + ' ' +
                    (input.placeholder || '') + ' ' + label).toLowerCase();
        if (NOT_MONEY_RE.test(hint) || !MONEY_RE.test(hint)) return;
        input.dataset.money = '1';
        input.classList.add('money');
        updateMoneyEcho(input);
    });
    window.addEventListener('pageshow', function () {
        document.querySelectorAll('input.money').forEach(updateMoneyEcho);
    });
}

/* ═══════════════════════════════════════════════════════════════
   ۱۴.۱) اطمینان از بوت شدن بقیه افزونه‌ها
   ═══════════════════════════════════════════════════════════════ */
function safeInit(fn, name) {
    // این لایه «بهبود تدریجی» است: اگر قالب عجیبی باعث خطا شد، بقیه
    // رفتارهای صفحه (و ثبت service worker) نباید از کار بیفتند.
    try {
        fn();
    } catch (err) {
        if (window.console && console.warn) console.warn('[ux:' + name + ']', err);
    }
}


/* ═══════════════════════════════════════════════════════════════
   ۱۵) دسترس‌پذیری: لیبل‌ها و کلیک‌های غیردکمه‌ای
   ═══════════════════════════════════════════════════════════════ */
function initLabelTargets() {
    // ۵۳۷ <label> در قالب‌ها بود و فقط ۱۱ تا for= داشت؛ یعنی ضربه به متن
    // لیبل روی موبایل فیلد را فوکوس نمی‌کرد (و صفحه‌کلید باز نمی‌شد).
    // اینجا برای لیبل‌هایی که دقیقاً یک کنترل دارند، for ساخته می‌شود.
    var seq = 0;
    function usable(list) {
        return Array.prototype.filter.call(list, function(el) {
            return el.type !== 'hidden' && !el.disabled;
        });
    }
    document.querySelectorAll('label:not([for])').forEach(function(label) {
        var controls = usable(label.querySelectorAll('input, select, textarea'));
        if (controls.length === 0 && label.parentNode && label.parentNode.querySelectorAll) {
            // الگوی رایج همین پروژه: «<label>…</label><input>» خواهر‌به‌خواهر داخل
            // یک کانتینر. اگر کانتینر دقیقاً یک کنترل داشت، همان را به لیبل می‌دهیم.
            var parentControls = usable(label.parentNode.querySelectorAll('input, select, textarea'));
            if (parentControls.length === 1) controls = parentControls;
        }
        if (controls.length !== 1) return;      // گروه رادیو/چک‌باکس: خود HTML کافی است
        var field = controls[0];
        // کامپوننت‌هایی که select اصلی را مخفی و یک نمایش جایگزین می‌کنند:
        // for دادن به آن‌ها کلیک را به یک کنترل نامرئی می‌برد
        if (field.closest('.ss-container, .ss-display')) return;
        if (field.offsetWidth === 0 && field.offsetHeight === 0 && field.type !== 'hidden') return;
        if (!field.id) {
            seq += 1;
            field.id = 'auto-fld-' + seq + '-' + Math.random().toString(36).slice(2, 6);
        }
        label.setAttribute('for', field.id);
        label.style.cursor = 'pointer';
    });
}

function initClickableA11y() {
    // ۸۵ onclick روی div/span: با کیبورد و screen reader هیچ‌وقت قابل استفاده
    // نبود. ردیف/لیست جدول را دست نمی‌زنیم (role خودشان معنادار است).
    document.querySelectorAll('[onclick]').forEach(function(el) {
        var tag = el.tagName;
        if (tag === 'BUTTON' || tag === 'A' || tag === 'INPUT' || tag === 'SELECT' ||
            tag === 'TEXTAREA' || tag === 'TR' || tag === 'LI' || tag === 'LABEL') return;
        if (el.hasAttribute('tabindex')) return;
        el.setAttribute('role', 'button');
        el.setAttribute('tabindex', '0');
        el.addEventListener('keydown', function(ev) {
            if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
                ev.preventDefault();
                el.click();
            }
        });
    });
}


/* ═══════════════════════════════════════════════════════════════
   ۱۶) Service Worker
   ═══════════════════════════════════════════════════════════════ */
function registerServiceWorker() {
    if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
    // ثبت فقط روی خط خودِ اپ انجام می‌شود (روی http محلی دسکتاپ SW مجاز نیست)
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function() {
            /* محیط‌هایی که SW مجاز نیست (زیر path، http داخلی دسکتاپ) */
        });
    });
}
