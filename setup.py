"""
Academy Manager Pro - Setup & Localize
این فایل را یکبار اجرا کنید:
  python setup.py

تمام فایل‌های CSS, JS, Font را دانلود و بومی می‌کند
بعد از اجرا، نرم‌افزار بدون اینترنت کار می‌کند
"""
import os
import sys
import urllib.request
import ssl
import re

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, 'static')


def download(url, path):
    """دانلود فایل"""
    full = os.path.join(STATIC, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if os.path.exists(full):
        return True
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            data = r.read()
        with open(full, 'wb') as f:
            f.write(data)
        print(f'  OK: {path} ({len(data)//1024} KB)')
        return True
    except Exception as e:
        print(f'  FAIL: {path} - {str(e)[:50]}')
        return False


def fix_vazirmatn_css():
    """اصلاح مسیرهای فونت وزیرمتن"""
    css = os.path.join(STATIC, 'fonts/Vazirmatn-font-face.css')
    if not os.path.exists(css):
        return
    with open(css, 'r', encoding='utf-8') as f:
        c = f.read()
    # حذف تمام مسیرهای اضافی
    c = c.replace('fonts/webfonts/', '')
    c = c.replace('../fonts/', '')
    c = c.replace('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/webfonts/', '')
    # حذف فونت‌های ایتالیک
    blocks = c.split('@font-face')
    clean = [blocks[0]]
    for b in blocks[1:]:
        if 'Italic' not in b:
            clean.append('@font-face' + b)
    with open(css, 'w', encoding='utf-8') as f:
        f.write(''.join(clean))
    print('  Fixed: Vazirmatn CSS')


def fix_bootstrap_icons_css():
    """اصلاح مسیرهای آیکون"""
    css = os.path.join(STATIC, 'css/bootstrap-icons.min.css')
    if not os.path.exists(css):
        return
    with open(css, 'r', encoding='utf-8') as f:
        c = f.read()
    # مسیر صحیح: فونت‌ها در css/fonts/ هستن
    c = c.replace('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/', 'fonts/')
    with open(css, 'w', encoding='utf-8') as f:
        f.write(c)
    print('  Fixed: Bootstrap Icons CSS')


def update_templates():
    """آپدیت تمام فایل‌های HTML برای استفاده از فایل‌های محلی"""
    templates_dir = os.path.join(BASE, 'templates')
    
    replacements = [
        ('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css',
         "/static/fonts/Vazirmatn-font-face.css"),
        ('https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css',
         "/static/css/bootstrap.rtl.min.css"),
        ('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
         "/static/css/bootstrap-icons.min.css"),
        ('https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js',
         "/static/js/chart.umd.min.js"),
        ('https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
         "/static/js/bootstrap.bundle.min.js"),
    ]
    
    count = 0
    for root, dirs, files in os.walk(templates_dir):
        for fname in files:
            if fname.endswith('.html'):
                fpath = os.path.join(root, fname)
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                changed = False
                for old, new in replacements:
                    if old in content:
                        content = content.replace(old, new)
                        changed = True
                
                if changed:
                    with open(fpath, 'w', encoding='utf-8') as f:
                        f.write(content)
                    count += 1
    
    print(f'  Updated: {count} HTML files')


def create_db():
    """ساخت دیتابیس"""
    os.makedirs(os.path.join(BASE, 'instance'), exist_ok=True)
    os.makedirs(os.path.join(BASE, 'backups'), exist_ok=True)
    os.makedirs(os.path.join(BASE, 'static', 'uploads'), exist_ok=True)
    
    try:
        from app import create_app
        create_app()
        print('  Database created OK')
    except Exception as e:
        print(f'  DB error: {str(e)[:60]}')


def main():
    print()
    print('=' * 55)
    print('  Academy Manager Pro - Setup')
    print('=' * 55)
    
    # 1) دانلود فایل‌ها
    print('\n[1/4] Downloading assets...')
    
    assets = [
        ('https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css', 'fonts/Vazirmatn-font-face.css'),
        ('https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css', 'css/bootstrap.rtl.min.css'),
        ('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css', 'css/bootstrap-icons.min.css'),
        ('https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js', 'js/bootstrap.bundle.min.js'),
        ('https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js', 'js/chart.umd.min.js'),
    ]
    
    for url, path in assets:
        download(url, path)
    
    # فونت‌ها
    print('\n[2/4] Downloading fonts...')
    fonts = ['Thin','ExtraLight','Light','Regular','Medium','SemiBold','Bold','ExtraBold','Black']
    base = 'https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/webfonts/'
    for w in fonts:
        download(f'{base}Vazirmatn-{w}.woff2', f'fonts/Vazirmatn-{w}.woff2')
    
    # آیکون‌ها
    icons_base = 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/fonts/'
    download(f'{icons_base}bootstrap-icons.woff', 'css/fonts/bootstrap-icons.woff')
    download(f'{icons_base}bootstrap-icons.woff2', 'css/fonts/bootstrap-icons.woff2')
    
    # 2) اصلاح مسیرها
    print('\n[3/4] Fixing paths...')
    fix_vazirmatn_css()
    fix_bootstrap_icons_css()
    update_templates()
    
    # 3) ساخت دیتابیس
    print('\n[4/4] Creating database...')
    create_db()
    
    print()
    print('=' * 55)
    print('  DONE!')
    print('  Run: python app.py')
    print('  URL: http://localhost:5000  (برای شبکه از آدرس IP سیستم استفاده کنید)')
    try:
        from utils.constants import (default_admin_password,
                                     default_admin_username)
        _admin_hint = f'{default_admin_username()} / {default_admin_password()}'
    except Exception:
        _admin_hint = 'admin / admin123'
    print(f'  User: {_admin_hint}')
    print('=' * 55)
    print()


if __name__ == '__main__':
    main()
