/* ═══════════════════════════════════════════════════════════════
   UI Core — مدیریت یکپارچهٔ وضعیت رابط کاربری (State Management)
   ═══════════════════════════════════════════════════════════════
   قبل از این، هر جا fetch مستقیم می‌زد (جستجو، dark-mode، جاهای دیگر)،
   اطلاعات وضعیت (busy/خطا/توکن CSRF) نقطه‌به‌نقطه تکرار می‌شد و یکپارچه
   نبود. این ماژول یک منبع واحد می‌دهد:
     • ui.api(path, opts)  → fetch با CSRF، JSON، آمار busy و Toast خطا
     • ui.toast(msg, type) → اعلان‌های یکنواخت (same as app.js showToast)
     • ui.busy(on)         → شمارندهٔ مرکزی state (همهٔ درخواست‌ها با هم)
     • ui.confirm(msg, onYes) → تأیید یکپارچه
   برای سازگاری، تابع سراسری showToast قبلی هم به ui.toast سوق داده می‌شود.
*/
(function () {
    'use strict';

    // ── state مرکزی ─────────────────────────────────────────────
    var state = {
        busyCount: 0,
        csrfToken: '',
    };

    var Ui = {
        // دریافت/کش توکن CSRF (meta یا input مخفی)
        csrf: function () {
            if (state.csrfToken) return state.csrfToken;
            var meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) { state.csrfToken = meta.getAttribute('content'); return state.csrfToken; }
            var input = document.querySelector('input[name="csrf_token"]');
            if (input) { state.csrfToken = input.value; }
            return state.csrfToken || '';
        },

        // شمارندهٔ busy مرکزی؛ برای درخواست‌های موازی درست کار می‌کند
        busy: function (on) {
            state.busyCount = Math.max(0, state.busyCount + (on ? 1 : -1));
            var el = document.getElementById('globalBusy');
            if (!el) return;
            if (state.busyCount > 0) {
                el.hidden = false;
                el.classList.add('show');
                // نمایش «در حال پردازش…» بعد از ۳۰۰ms تا پرش نداشته باشیم
                if (!el._t) {
                    el._t = setTimeout(function () {
                        if (state.busyCount > 0) el.textContent = 'در حال پردازش…';
                    }, 300);
                }
            } else {
                el.hidden = true;
                el.classList.remove('show');
                if (el._t) { clearTimeout(el._t); el._t = null; }
                el.textContent = '';
            }
        },

        // اعلان یکنواخت — در نبود container، خودش می‌سازد
        toast: function (message, type) {
            type = type || 'success';
            var container = document.getElementById('toastContainer');
            if (!container) {
                container = document.createElement('div');
                container.id = 'toastContainer';
                container.style.cssText = 'position: fixed; top: 20px; left: 20px; z-index: 9999;';
                document.body.appendChild(container);
            }
            var colors = { success: '#2e7d32', error: '#c62828', warning: '#ff8f00', info: '#1565c0' };
            var icons = { success: 'check-circle', error: 'x-circle', warning: 'exclamation-triangle', info: 'info-circle' };
            var toast = document.createElement('div');
            toast.style.cssText = [
                'background:' + (colors[type] || colors.info),
                'color:#fff', 'padding:12px 20px', 'border-radius:8px',
                'margin-bottom:8px', 'font-size:13px', 'font-family:Vazirmatn, Tahoma',
                'display:flex', 'align-items:center', 'gap:8px',
                'box-shadow:0 4px 12px rgba(0,0,0,.2)', 'animation:fadeInLeft .3s ease-out',
                'direction:rtl'
            ].join(';');
            toast.innerHTML = '<i class="bi bi-' + (icons[type] || icons.info) + '"></i> ' + message;
            container.appendChild(toast);
            setTimeout(function () {
                toast.style.transition = 'all .3s';
                toast.style.opacity = '0';
                setTimeout(function () { toast.remove(); }, 300);
            }, 4000);
        },

        // تأیید یکپارچه — بدون وابستگی به plugin خارجی
        confirm: function (message, onYes) {
            if (window.confirm(message) && typeof onYes === 'function') onYes();
        },

        // fetch مشترک: CSRF + JSON + busy + toast خطا
        // returns: Promise<data> (JSON)؛ در خطا، Promise.reject(err)
        api: function (path, opts) {
            opts = opts || {};
            var method = (opts.method || 'GET').toUpperCase();
            var headers = Object.assign({}, opts.headers || {});
            if (method !== 'GET') headers['X-CSRFToken'] = Ui.csrf();

            var body = opts.body;
            if (body && !(body instanceof FormData) && typeof body === 'object') {
                headers['Content-Type'] = 'application/json';
                body = JSON.stringify(body);
            }

            Ui.busy(true);
            return fetch(path, Object.assign({}, opts, {
                method: method,
                headers: headers,
                body: body,
                credentials: 'same-origin'
            })).then(function (resp) {
                // پاسخ‌های غیر JSON را همان‌طور برمی‌گردانیم
                var ct = (resp.headers.get('content-type') || '');
                if (ct.indexOf('application/json') >= 0) return resp.json();
                return resp.text().then(function (t) { return { ok: resp.ok, status: resp.status, text: t }; });
            }).then(function (data) {
                if (data && data.ok === false) {
                    Ui.toast(data.message || 'عملیات ناموفق بود', 'error');
                    throw data;
                }
                return data;
            }).catch(function (err) {
                // fetch خودش خطای شبکه را پرتاب می‌کند؛ برای ۵۰۰ هم پیام بده
                if (err && err.name === 'AbortError') throw err;
                if (!(err && err.ok === false)) {
                    Ui.toast('خطا در ارتباط با سرور؛ دوباره تلاش کنید', 'error');
                }
                throw err;
            }).finally(function () {
                Ui.busy(false);
            });
        }
    };

    window.Ui = Ui;

    // سازگاری: تابع قدیمی showToast (استفاده در app.js/قالب‌ها)
    window.showToast = Ui.toast;
    window.getCSRFToken = Ui.csrf;
})();
