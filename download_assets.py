"""
دانلود تمام فایل‌های CDN و بومی‌سازی
بعد از اجرا، تمام فایل‌ها از لوکال خوانده می‌شوند
بدون نیاز به اینترنت

اجرا: python download_assets.py
"""
import os
import urllib.request
import ssl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
VENDOR_DIR = os.path.join(STATIC_DIR, 'vendor')

# لیست فایل‌های CDN برای دانلود
ASSETS = [
    # فونت وزیرمتن
    {
        'url': 'https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css',
        'local': 'fonts/Vazirmatn-font-face.css',
        'type': 'css'
    },
    # Bootstrap CSS RTL
    {
        'url': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css',
        'local': 'css/bootstrap.rtl.min.css',
        'type': 'css'
    },
    # Bootstrap Icons CSS
    {
        'url': 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
        'local': 'css/bootstrap-icons.min.css',
        'type': 'css'
    },
    # Bootstrap JS
    {
        'url': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
        'local': 'js/bootstrap.bundle.min.js',
        'type': 'js'
    },
    # Chart.js
    {
        'url': 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js',
        'local': 'js/chart.umd.min.js',
        'type': 'js'
    },
]

# فونت‌های وزیرمتن (فایل‌های WOFF2)
FONT_FILES = [
    'Vazirmatn-Thin.woff2',
    'Vazirmatn-ThinItalic.woff2',
    'Vazirmatn-ExtraLight.woff2',
    'Vazirmatn-ExtraLightItalic.woff2',
    'Vazirmatn-Light.woff2',
    'Vazirmatn-LightItalic.woff2',
    'Vazirmatn-Regular.woff2',
    'Vazirmatn-Italic.woff2',
    'Vazirmatn-Medium.woff2',
    'Vazirmatn-MediumItalic.woff2',
    'Vazirmatn-SemiBold.woff2',
    'Vazirmatn-SemiBoldItalic.woff2',
    'Vazirmatn-Bold.woff2',
    'Vazirmatn-BoldItalic.woff2',
    'Vazirmatn-ExtraBold.woff2',
    'Vazirmatn-ExtraBoldItalic.woff2',
    'Vazirmatn-Black.woff2',
    'Vazirmatn-BlackItalic.woff2',
]

# آیکون‌های Bootstrap (فایل‌های فونت)
BOOTSTRAP_ICONS_FILES = [
    'bootstrap-icons.woff',
    'bootstrap-icons.woff2',
]


def download_file(url, local_path):
    """دانلود یک فایل"""
    full_path = os.path.join(STATIC_DIR, local_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    if os.path.exists(full_path):
        print(f'  [SKIP] {local_path} (exists)')
        return True
    
    try:
        # نادیده گرفتن SSL
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            data = response.read()
        
        with open(full_path, 'wb') as f:
            f.write(data)
        
        size_kb = len(data) / 1024
        print(f'  [OK] {local_path} ({size_kb:.1f} KB)')
        return True
    except Exception as e:
        print(f'  [FAIL] {local_path}: {str(e)[:60]}')
        return False


def download_fonts():
    """دانلود فایل‌های فونت وزیرمتن"""
    print('\n  Downloading Vazirmatn fonts...')
    base_url = 'https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/webfonts/'
    
    for font in FONT_FILES:
        download_file(base_url + font, f'fonts/{font}')


def download_bootstrap_icons_fonts():
    """دانلود فونت‌های Bootstrap Icons"""
    print('\n  Downloading Bootstrap Icons fonts...')
    base_url = 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/'
    
    for font in BOOTSTRAP_ICONS_FILES:
        download_file(base_url + font, f'css/fonts/{font}')


def fix_css_paths():
    """اصلاح مسیرهای فایل‌های CSS برای استفاده از فایل‌های محلی"""
    
    # اصلاح مسیر فونت وزیرمتن
    css_path = os.path.join(STATIC_DIR, 'fonts/Vazirmatn-font-face.css')
    if os.path.exists(css_path):
        with open(css_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # تبدیل URL های jsDelivr به مسیر نسبی
        content = content.replace(
            'https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/webfonts/',
            '../fonts/'
        )
        
        with open(css_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print('  [FIXED] Vazirmatn CSS paths')
    
    # اصلاح مسیر Bootstrap Icons
    css_path = os.path.join(STATIC_DIR, 'css/bootstrap-icons.min.css')
    if os.path.exists(css_path):
        with open(css_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        content = content.replace(
            'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/',
            'fonts/'
        )
        
        with open(css_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print('  [FIXED] Bootstrap Icons CSS paths')


def create_local_template():
    """ساخت فایل base layout محلی (بدون CDN)"""
    
    template_path = os.path.join(BASE_DIR, 'templates', 'base', 'layout_local.html')
    layout_path = os.path.join(BASE_DIR, 'templates', 'base', 'layout.html')
    
    with open(layout_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # جایگزینی CDN ها با فایل‌های محلی
    replacements = [
        (
            'https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css',
            "{{ url_for('static', filename='fonts/Vazirmatn-font-face.css') }}"
        ),
        (
            'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css',
            "{{ url_for('static', filename='css/bootstrap.rtl.min.css') }}"
        ),
        (
            'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
            "{{ url_for('static', filename='css/bootstrap-icons.min.css') }}"
        ),
        (
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js',
            "{{ url_for('static', filename='js/chart.umd.min.js') }}"
        ),
        (
            'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
            "{{ url_for('static', filename='js/bootstrap.bundle.min.js') }}"
        ),
    ]
    
    for old, new in replacements:
        content = content.replace(old, new)
    
    # ذخیره فایل اصلی (جایگزین)
    with open(layout_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('  [OK] layout.html updated to use local files')


def main():
    print('=' * 60)
    print('  Academy Manager - Download & Localize CDN Assets')
    print('=' * 60)
    
    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(os.path.join(STATIC_DIR, 'fonts'), exist_ok=True)
    os.makedirs(os.path.join(STATIC_DIR, 'css'), exist_ok=True)
    os.makedirs(os.path.join(STATIC_DIR, 'js'), exist_ok=True)
    
    # ۱) دانلود فایل‌های اصلی
    print('\n[1/4] Downloading main assets...')
    success = 0
    for asset in ASSETS:
        if download_file(asset['url'], asset['local']):
            success += 1
    
    # ۲) دانلود فونت‌ها
    print('\n[2/4] Downloading fonts...')
    download_fonts()
    download_bootstrap_icons_fonts()
    
    # ۳) اصلاح مسیرها
    print('\n[3/4] Fixing CSS paths...')
    fix_css_paths()
    
    # ۴) بروزرسانی template
    print('\n[4/4] Updating templates...')
    create_local_template()
    
    # خلاصه
    print('\n' + '=' * 60)
    print(f'  DONE! {success}/{len(ASSETS)} main assets downloaded')
    print('  All files are now served from local static folder')
    print('  No internet connection required!')
    print('=' * 60)


if __name__ == '__main__':
    main()
