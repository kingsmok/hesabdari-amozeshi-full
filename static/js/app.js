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
    // بستن سایدبار با کلیک روی اورلی
    window.addEventListener('resize', function() {
        if (window.innerWidth > 992) {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('mobileOverlay');
            if (overlay) overlay.classList.remove('visible');
            document.body.style.overflow = '';
            if (sidebar) sidebar.classList.remove('open');
        }
    });
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

function globalSearch(q) {
    clearTimeout(searchTimer);
    const box = document.getElementById('searchResults');
    if (!box) return;
    
    if (q.length < 2) { box.style.display = 'none'; return; }
    
    // نمایش لودینگ
    box.innerHTML = '<div style="padding: 16px; text-align: center;"><div class="spinner-border spinner-border-sm text-primary" role="status"></div></div>';
    box.style.display = 'block';
    
    searchTimer = setTimeout(() => {
        fetch('/api/search?q=' + encodeURIComponent(q))
            .then(r => r.json())
            .then(data => {
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
    });
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
