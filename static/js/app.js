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
    initMobileUX();
    
    console.log('✅ Academy Manager Pro — JS loaded');
});


/* ═══════════════════════════════════════════════════════════════
   ۱) انیمیشن ورود عناصر هنگام اسکرول
   ═══════════════════════════════════════════════════════════════ */
function initScrollReveal() {
    const elements = document.querySelectorAll('.stat-box, .card, .table');
    if (!('IntersectionObserver' in window) ||
            window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        elements.forEach(el => { el.style.opacity = '1'; });
        return;
    }
    const revealAllForPrint = () => elements.forEach(el => { el.style.opacity = '1'; });
    window.addEventListener('beforeprint', revealAllForPrint);
    
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
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
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
function setSidebarAccessibility(sidebar, expanded) {
    if (!sidebar) return;
    if (!expanded && sidebar.contains(document.activeElement)) {
        const toggle = document.querySelector('.btn-toggle-sidebar');
        if (toggle) toggle.focus({ preventScroll: true });
    }
    sidebar.setAttribute('aria-hidden', String(!expanded));
    if (expanded) sidebar.removeAttribute('inert');
    else sidebar.setAttribute('inert', '');
}

function readStoredValue(key, fallback = null) {
    try { return localStorage.getItem(key) ?? fallback; }
    catch (_) { return fallback; }
}

function writeStoredValue(key, value) {
    try { localStorage.setItem(key, value); }
    catch (_) {}
}

function removeStoredValue(key) {
    try { localStorage.removeItem(key); }
    catch (_) {}
}

function initSidebar() {
    // باز/بسته زیرمنوها با انیمیشن
    document.querySelectorAll('.nav-link-item[onclick]').forEach(item => {
        item.setAttribute('role', 'button');
        item.setAttribute('tabindex', '0');
        item.setAttribute('aria-expanded', String(item.classList.contains('open')));
        const submenu = item.nextElementSibling;
        if (submenu && submenu.classList.contains('nav-sub')) {
            submenu.id = submenu.id || `sidebar-submenu-${Array.from(document.querySelectorAll('.nav-sub')).indexOf(submenu) + 1}`;
            item.setAttribute('aria-controls', submenu.id);
            submenu.setAttribute('aria-hidden', String(!submenu.classList.contains('show')));
        }
        item.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                this.click();
            }
        });
        item.addEventListener('click', function() {
            const sub = this.nextElementSibling;
            if (sub && sub.classList.contains('nav-sub')) {
                // بستن سایر زیرمنوها
                document.querySelectorAll('.nav-sub.show').forEach(openSub => {
                    if (openSub !== sub) {
                        openSub.classList.remove('show');
                        openSub.setAttribute('aria-hidden', 'true');
                        openSub.previousElementSibling.classList.remove('open');
                        openSub.previousElementSibling.setAttribute('aria-expanded', 'false');
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
            const savedState = readStoredValue('sidebar_collapsed', 'false');
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
        const toggle = document.querySelector('.btn-toggle-sidebar');
        if (toggle) {
            const expanded = isMobile ? sidebar.classList.contains('open') : sidebar.style.width !== '0px' && sidebar.style.width !== '0';
            toggle.setAttribute('aria-expanded', String(expanded));
        }
        const expanded = isMobile ? sidebar.classList.contains('open') : sidebar.style.width !== '0px' && sidebar.style.width !== '0';
        setSidebarAccessibility(sidebar, expanded);
    }
    // بستن سایدبار با کلیک روی اورلی / لینک / Escape
    let sidebarWasMobile = window.innerWidth <= 992;
    window.addEventListener('resize', function() {
        const isMobile = window.innerWidth <= 992;
        if (isMobile === sidebarWasMobile) return;
        sidebarWasMobile = isMobile;
        if (!isMobile) {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('mobileOverlay');
            const mainWrap = document.getElementById('mainWrap');
            const collapsed = readStoredValue('sidebar_collapsed', 'false') === 'true';
            if (overlay) overlay.classList.remove('visible');
            document.body.style.overflow = '';
            if (sidebar) {
                sidebar.classList.remove('open');
                sidebar.style.width = collapsed ? '0' : 'var(--sidebar-w)';
                setSidebarAccessibility(sidebar, !collapsed);
            }
            if (mainWrap) mainWrap.style.marginRight = collapsed ? '0' : 'var(--sidebar-w)';
            const toggle = document.querySelector('.btn-toggle-sidebar');
            if (toggle) toggle.setAttribute('aria-expanded', String(!collapsed));
        } else {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('mobileOverlay');
            const mainWrap = document.getElementById('mainWrap');
            if (sidebar) {
                sidebar.classList.remove('open');
                sidebar.style.width = 'var(--sidebar-w)';
                setSidebarAccessibility(sidebar, false);
            }
            if (overlay) overlay.classList.remove('visible');
            if (mainWrap) mainWrap.style.marginRight = '0';
            document.body.style.overflow = '';
            const toggle = document.querySelector('.btn-toggle-sidebar');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
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
    if (window.innerWidth <= 992) {
        setSidebarAccessibility(sidebar, false);
        const toggle = document.querySelector('.btn-toggle-sidebar');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainWrap = document.getElementById('mainWrap');
    const overlay = document.getElementById('mobileOverlay');
    const isMobile = window.innerWidth <= 992;
    if (!sidebar || !mainWrap) return;

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
        const collapsed = readStoredValue('sidebar_collapsed', 'false') === 'true';
        const currentlyCollapsed = sidebar.style.width === '0px' || sidebar.style.width === '0';
        if (collapsed || currentlyCollapsed) {
            sidebar.style.width = 'var(--sidebar-w)';
            mainWrap.style.marginRight = 'var(--sidebar-w)';
            writeStoredValue('sidebar_collapsed', 'false');
        } else {
            sidebar.style.width = '0';
            mainWrap.style.marginRight = '0';
            writeStoredValue('sidebar_collapsed', 'true');
        }
    }
    const toggle = document.querySelector('.btn-toggle-sidebar');
    if (toggle) {
        const expanded = isMobile ? sidebar.classList.contains('open') : sidebar.style.width !== '0px' && sidebar.style.width !== '0';
        toggle.setAttribute('aria-expanded', String(expanded));
        setSidebarAccessibility(sidebar, expanded);
    }
}

function toggleNav(el) {
    el.classList.toggle('open');
    el.setAttribute('aria-expanded', String(el.classList.contains('open')));
    const sub = el.nextElementSibling;
    if (sub && sub.classList.contains('nav-sub')) {
        sub.classList.toggle('show');
        sub.setAttribute('aria-hidden', String(!sub.classList.contains('show')));
    }
}


/* ═══════════════════════════════════════════════════════════════
   ۴) جستجوی سراسری همه بخش‌ها
   ═══════════════════════════════════════════════════════════════ */
let searchTimer;
let globalSearchRequest;
let globalSearchSequence = 0;
let globalSearchActiveIndex = -1;

function initGlobalSearch() {
    const input = document.getElementById('globalSearch');
    const box = document.getElementById('searchResults');
    if (!input || !box) return;

    input.addEventListener('input', function() { globalSearch(this.value); });
    input.addEventListener('focus', function() {
        if (this.value.trim().length >= 2) globalSearch(this.value);
    });
    input.addEventListener('keydown', function(e) {
        const items = Array.from(box.querySelectorAll('.global-search-item'));
        if (e.key === 'ArrowDown' && items.length) {
            e.preventDefault();
            globalSearchActiveIndex = (globalSearchActiveIndex + 1) % items.length;
            setGlobalSearchActive(items);
        } else if (e.key === 'ArrowUp' && items.length) {
            e.preventDefault();
            globalSearchActiveIndex = (globalSearchActiveIndex - 1 + items.length) % items.length;
            setGlobalSearchActive(items);
        } else if ((e.key === 'Home' || e.key === 'End') && items.length) {
            e.preventDefault();
            globalSearchActiveIndex = e.key === 'Home' ? 0 : items.length - 1;
            setGlobalSearchActive(items);
        } else if (e.key === 'Enter' && globalSearchActiveIndex >= 0 && items[globalSearchActiveIndex]) {
            e.preventDefault(); items[globalSearchActiveIndex].click();
        } else if (e.key === 'Escape') {
            hideGlobalSearch(); this.blur();
        }
    });

    const wrap = input.closest('.global-search-wrap');
    if (wrap) {
        wrap.addEventListener('focusout', () => window.setTimeout(() => {
            if (!wrap.contains(document.activeElement)) hideGlobalSearch();
        }, 0));
    }
    document.addEventListener('click', e => {
        if (!e.target.closest('.global-search-wrap')) hideGlobalSearch();
    });
}

function setGlobalSearchActive(items) {
    items.forEach((item, index) => {
        const active = index === globalSearchActiveIndex;
        item.classList.toggle('active', active);
        item.setAttribute('aria-selected', String(active));
    });
    const active = items[globalSearchActiveIndex];
    const input = document.getElementById('globalSearch');
    if (active) {
        active.scrollIntoView({block: 'nearest'});
        if (input) input.setAttribute('aria-activedescendant', active.id);
    }
}

function hideGlobalSearch() {
    clearTimeout(searchTimer);
    globalSearchSequence += 1;
    if (globalSearchRequest) { globalSearchRequest.abort(); globalSearchRequest = null; }
    const box = document.getElementById('searchResults');
    const input = document.getElementById('globalSearch');
    if (box) box.style.display = 'none';
    if (input) {
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant');
    }
    globalSearchActiveIndex = -1;
}

function globalSearch(q) {
    clearTimeout(searchTimer);
    if (globalSearchRequest) { globalSearchRequest.abort(); globalSearchRequest = null; }
    const box = document.getElementById('searchResults');
    const input = document.getElementById('globalSearch');
    if (!box || !input) return;
    q = String(q || '').trim();
    if (q.length < 2) { hideGlobalSearch(); return; }
    const sequence = ++globalSearchSequence;

    box.innerHTML = '<div class="global-search-loading"><div class="spinner-border spinner-border-sm text-primary" role="status"></div><div class="mt-2 text-muted small">در حال جستجو در همه بخش‌ها...</div></div>';
    box.style.display = 'block';
    input.setAttribute('aria-expanded', 'true');
    input.removeAttribute('aria-activedescendant');
    globalSearchActiveIndex = -1;

    searchTimer = setTimeout(() => {
        const controller = new AbortController();
        globalSearchRequest = controller;
        fetch('/api/search?q=' + encodeURIComponent(q), {
            signal: controller.signal,
            headers: { 'Accept': 'application/json' }
        })
            .then(r => { if (!r.ok) throw new Error('search failed'); return r.json(); })
            .then(data => {
                if (sequence === globalSearchSequence && input.value.trim() === q) {
                    renderGlobalSearchResults(data, q);
                }
            })
            .catch(error => {
                if (error.name === 'AbortError' || sequence !== globalSearchSequence) return;
                box.innerHTML = '<div class="global-search-empty"><i class="bi bi-wifi-off"></i>خطا در دریافت نتیجه؛ دوباره تلاش کنید</div>';
            })
            .finally(() => {
                if (globalSearchRequest === controller) globalSearchRequest = null;
            });
    }, 260);
}

function renderGlobalSearchResults(data, query) {
    const box = document.getElementById('searchResults');
    if (!box) return;
    const results = data && Array.isArray(data.results) ? data.results : [];
    if (!results.length) {
        box.innerHTML = '<div class="global-search-empty"><i class="bi bi-search"></i><strong>نتیجه‌ای پیدا نشد</strong><br>نام، کد، شماره سند، مبلغ یا موبایل را بررسی کنید</div>';
        box.style.display = 'block';
        return;
    }
    const groupLabels = {
        reports:'گزارش‌ها', students:'هنرجویان', registrations:'ثبت‌نام‌ها',
        finance:'مالی، اقساط و چک', accounting:'حسابداری', courses:'دوره‌ها و رشته‌ها',
        classes:'کلاس‌ها و اتاق‌ها', teachers:'مدرسین', exams:'آزمون و سؤال',
        certificates:'گواهینامه‌ها', payroll:'حقوق و دستمزد',
        messages:'پیام‌ها', users:'کاربران', support:'پشتیبانی'
    };
    let lastGroup = null;
    let html = `<div class="global-search-head"><span><i class="bi bi-search me-1"></i>نتایج «${escapeHtml(query)}»</span><strong>${new Intl.NumberFormat('fa-IR').format(data.count || results.length)} مورد</strong></div>`;
    results.forEach((result, index) => {
        if (result.group !== lastGroup) {
            lastGroup = result.group;
            html += `<div class="global-search-group-title">${escapeHtml(groupLabels[lastGroup] || result.type || lastGroup)}</div>`;
        }
        const href = safeInternalUrl(result.url);
        const color = /^#[0-9a-f]{6}$/i.test(String(result.color || '')) ? result.color : '#64748b';
        const icon = /^[a-z0-9-]+$/i.test(String(result.icon || '')) ? result.icon : 'search';
        html += `<a class="global-search-item" id="global-search-option-${index}" role="option" aria-selected="false" href="${escapeHtml(href)}">
            <span class="global-search-item-icon" style="background:${color}"><i class="bi bi-${icon}"></i></span>
            <span class="global-search-item-main"><span class="global-search-item-name">${escapeHtml(result.name || '')}</span><span class="global-search-item-detail">${escapeHtml(result.detail || '')}</span></span>
            <span class="global-search-item-type">${escapeHtml(result.type || '')}</span>
        </a>`;
    });
    html += '<div class="global-search-footer"><span>↑↓ انتخاب · Enter بازکردن</span><span>Esc بستن</span></div>';
    box.innerHTML = html;
    box.style.display = 'block';
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

let darkModeRequestInFlight = false;
function toggleDarkMode() {
    if (darkModeRequestInFlight) return;
    darkModeRequestInFlight = true;
    fetch('/api/dark-mode', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCSRFToken() }
    })
    .then(r => {
        if (!r.ok) throw new Error('ذخیره حالت نمایش ناموفق بود');
        return r.json();
    })
    .then(data => {
        if (data.dark_mode === 'on') {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
    })
    .catch(error => showToast(error.message, 'error'))
    .finally(() => { darkModeRequestInFlight = false; });
}


/* ═══════════════════════════════════════════════════════════════
   ۶) میانبرهای صفحه‌کلید
   ═══════════════════════════════════════════════════════════════ */
function initKeyboardShortcuts() {
    const config = document.getElementById('keyboardShortcutConfig');
    const destinations = config ? {
        Digit1: config.dataset.dashboardUrl,
        Digit2: config.dataset.studentUrl,
        Digit3: config.dataset.registrationUrl,
        Digit4: config.dataset.paymentUrl,
        Digit0: config.dataset.helpUrl
    } : {};

    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd+K is the conventional in-app command palette shortcut.
        if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') {
            const search = document.getElementById('globalSearch');
            if (search) {
                e.preventDefault();
                search.focus();
            }
        }

        // Use a three-key chord so browser New/Reload/Print/Bookmark shortcuts
        // are never replaced.  Missing destinations are omitted server-side
        // when the user lacks create permission.
        if ((e.ctrlKey || e.metaKey) && e.altKey && !e.shiftKey && !e.repeat) {
            const destination = safeInternalUrl(destinations[e.code]);
            if (destination !== '#') {
                e.preventDefault();
                window.location.assign(destination);
            }
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
        const saved = readStoredValue('autosave_' + key);
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
            writeStoredValue('autosave_' + key, JSON.stringify(data));
        }, 500));
        
        // پاک کردن بعد از ارسال
        form.addEventListener('submit', () => {
            removeStoredValue('autosave_' + key);
        });
    });
}


/* ═══════════════════════════════════════════════════════════════
   ۱۰) انیمیشن نمودارها
   ═══════════════════════════════════════════════════════════════ */
function initChartAnimations() {
    // تنظیمات پیش‌فرض Chart.js
    if (typeof Chart !== 'undefined') {
        Chart.defaults.animation = window.matchMedia('(prefers-reduced-motion: reduce)').matches
            ? false
            : { duration: 1500, easing: 'easeOutQuart' };
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
}

function wrapTablesForMobile() {
    document.querySelectorAll('table').forEach(function(table) {
        if (table.closest('.table-responsive')) return;
        if (table.closest('.jalali-picker, .ss-dropdown')) return;
        var wrap = document.createElement('div');
        wrap.className = 'table-responsive';
        table.parentNode.insertBefore(wrap, table);
        wrap.appendChild(table);
    });
}

function initUserMenuTouch() {
    var chip = document.getElementById('userChip') || document.querySelector('.user-chip');
    if (!chip) return;
    var links = Array.from(chip.querySelectorAll('.user-dropdown a'));
    function setOpen(open) {
        chip.classList.toggle('show-menu', open);
        chip.setAttribute('aria-expanded', String(open));
    }

    const usesHover = () => window.matchMedia('(hover: hover) and (pointer: fine)').matches && window.innerWidth > 992;
    chip.addEventListener('mouseenter', function() {
        if (usesHover()) setOpen(true);
    });
    chip.addEventListener('mouseleave', function() {
        if (usesHover() && !chip.contains(document.activeElement)) setOpen(false);
    });
    chip.addEventListener('click', function(e) {
        if (e.target.closest('.user-dropdown a')) return;
        if (usesHover()) return;
        e.preventDefault();
        e.stopPropagation();
        setOpen(!chip.classList.contains('show-menu'));
    });
    chip.addEventListener('keydown', function(e) {
        const focusedLink = e.target.closest('.user-dropdown a');
        if (focusedLink) {
            const index = links.indexOf(focusedLink);
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                const step = e.key === 'ArrowDown' ? 1 : -1;
                links[(index + step + links.length) % links.length]?.focus();
            } else if (e.key === 'Home' || e.key === 'End') {
                e.preventDefault();
                links[e.key === 'Home' ? 0 : links.length - 1]?.focus();
            } else if (e.key === 'Escape') {
                e.preventDefault(); setOpen(false); chip.focus();
            }
            return;
        }
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
            e.preventDefault();
            setOpen(true);
            if (links[0]) links[0].focus();
        } else if (e.key === 'Escape') {
            setOpen(false);
        }
    });

    chip.addEventListener('focusout', function() {
        window.setTimeout(function() {
            if (!chip.contains(document.activeElement)) setOpen(false);
        }, 0);
    });
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.user-chip')) setOpen(false);
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

function safeInternalUrl(value) {
    const raw = String(value || '');
    if (!raw.startsWith('/') || raw.startsWith('//')) return '#';
    try {
        const parsed = new URL(raw, window.location.origin);
        if (parsed.origin !== window.location.origin) return '#';
        return parsed.pathname + parsed.search + parsed.hash;
    } catch (_) {
        return '#';
    }
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
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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
        animation: ${reduceMotion ? 'none' : 'fadeInLeft 0.3s ease-out'};
        direction: rtl;
    `;
    const toastIcon = document.createElement('i');
    toastIcon.className = `bi bi-${icons[type] || icons.info}`;
    toastIcon.setAttribute('aria-hidden', 'true');
    toast.appendChild(toastIcon);
    toast.appendChild(document.createTextNode(String(message == null ? '' : message)));
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    
    document.getElementById('toastContainer').appendChild(toast);
    
    setTimeout(() => {
        if (reduceMotion) {
            toast.remove();
            return;
        }
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
