/* ═══════════════════════════════════════════════════════════════
   Service Worker — Academy Manager Pro
   ───────────────────────────────────────────────────────────────
   هدف: «افزودن به صفحه اصلی» روی موبایل فقط یک تب مرورگر نبود (نه آفلاین،
   نه اسپلش، نه آیکون درست). این SW داده‌ها را آفلاین نمی‌کند —
   فقط پوسته و فایل‌های استاتیک را کش می‌کند تا:
     • باز شدن صفحه روی شبکه ضعیف/قطع داده سریع‌تر باشد،
     • با قطع سرور، به‌جای صفحه خطای مرورگر، پیام «سرور در دسترس نیست»
       نمایش داده شود (offline.html).
   سیاست: شبکه‌اول برای HTML (تا داده قدیمی به کاربر نشان داده نشود)،
   کش‌اول برای استاتیکِ نسخه‌دار (asset() با ?v= → بی‌خطر).
   ═══════════════════════════════════════════════════════════════ */
const VERSION = 'v1';
const SHELL_CACHE = `acm-shell-${VERSION}`;
const RUNTIME_CACHE = `acm-runtime-${VERSION}`;
const OFFLINE_URL = '/offline';
const PRECACHE = [
    OFFLINE_URL,
    '/static/css/responsive.css',
    '/static/css/animations.css',
    '/static/css/jalali-picker.css',
    '/static/css/searchable-select.css',
    '/static/js/app.js',
    '/static/js/jalali-picker.js',
    '/static/js/searchable-select.js',
    '/static/images/icons/icon-192.png',
    '/static/images/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(SHELL_CACHE)
            .then((cache) => cache.addAll(PRECACHE))
            .catch(() => undefined)      // فایل جابه‌جا شده باشد، نصب نشکند
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((key) => key !== SHELL_CACHE && key !== RUNTIME_CACHE)
                    .map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;              // نوشتن هرگز کش نمی‌شود

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;  // CDNهای بیرونی دست‌نخورده

    // استاتیک: کش‌اول (URL نسخه‌دار است، پس کهنه‌شدن معنا ندارد)
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request).then((cached) => cached || fetch(request).then((response) => {
                if (response && response.ok) {
                    const copy = response.clone();
                    caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
                }
                return response;
            }))
        );
        return;
    }

    // صفحات: همیشه شبکه — در نرم‌افزار مالی، نشان دادن صفحه کش‌شدهٔ کهنه
    // (لیست پرداخت‌های دیروز) بدتر از پیام «آفلاین» است. فقط fallback آفلاین.
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).catch(() => caches.match(OFFLINE_URL))
        );
    }
});
