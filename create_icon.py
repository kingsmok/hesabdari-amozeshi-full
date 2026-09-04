"""
ساخت آیکون برنامه — Academy Manager Pro
اجرا: python create_icon.py

دو خروجی:
  • icon.ico + favicon.png            برای تب مرورگر و نصب ویندوزی
  • static/images/icons/*.png         برای PWA (192/512، maskable، apple-touch)

پیش‌تر `static/manifest.json` فقط یک SVG را به‌عنوان آیکون معرفی می‌کرد؛
Android/iOS برای «افزودن به صفحه اصلی» به PNG ۱۹۲ و ۵۱۲ نیاز دارند و
`apple-touch-icon` هم در هیچ قالبی نبود ⇒ روی iOS آیکون، اسکرین‌شاتِ کج
می‌شد. نقشه هم با PIL رسم می‌شود (بدون وابستگی به فونت سیستمی).
"""
import os

BRAND_TOP = (13, 71, 161)      # #0d47a1
BRAND_BOTTOM = (0, 200, 83)    # #00c853


def _gradient_tile(size):
    """مربع گرادیانت آبی→سبز با گوشه‌های گرد."""

    from PIL import Image, ImageDraw

    # گرادیانت مورب: روی بوم ۱۶×۱۶ حساب و بعد بزرگ‌نمایی نرم (سریع و بدون حلقه پیکسلی)
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    small = Image.new('RGB', (16, 16))
    for y in range(16):
        for x in range(16):
            ratio = (x + y) / 30
            small.putpixel((x, y), tuple(int(BRAND_TOP[i] + (BRAND_BOTTOM[i] - BRAND_TOP[i]) * ratio)
                                         for i in range(3)))
    base = small.resize((size, size), Image.Resampling.BILINEAR)

    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=max(2, int(size * 0.22)), fill=255)
    img.paste(base, (0, 0), mask)
    return img


def _draw_mark(img, safe=0.0):
    """نشان سفید: سه خط حساب + تیک تأیید. `safe` حاشیه امن برای maskable است."""
    from PIL import ImageDraw

    size = img.width
    margin = int(size * (0.20 + safe))
    inner = size - 2 * margin
    draw = ImageDraw.Draw(img)
    stroke = max(2, int(inner * 0.10))

    # سه خط با طول‌های مختلف (نمارت سطرهای دفتر)
    widths = (1.0, 0.78, 0.58)
    gap = inner * 0.24
    for index, width_ratio in enumerate(widths):
        y = int(margin + gap * index)
        draw.rounded_rectangle([margin, y, int(margin + inner * width_ratio), y + stroke],
                               radius=stroke // 2, fill=(255, 255, 255, 255))

    # تیک تأیید زیر سطرها — عمداً پایین‌تر از آخرین خط رسم می‌شود تا در
    # اندازه‌های کوچک (۴۸/۹۶) به خطوط نچسبد و خوانایی‌اش را از دست ندهد
    tick_y = int(margin + gap * 3.15)
    tick = int(inner * 0.28)
    bottom = min(size - margin - stroke, tick_y + tick)
    draw.line([(margin, tick_y), (margin + tick // 2, bottom),
               (margin + int(tick * 2.1), tick_y - int(tick * 0.35))],
              fill=(255, 255, 255, 255), width=max(2, int(inner * 0.09)), joint='curve')
    return img


def create_icon():
    """ساخت آیکون با Pillow یا SVG"""
    try:
        sizes = [16, 32, 48, 64, 128, 256]
        images = []
        for size in sizes:
            img = _gradient_tile(size)
            if size >= 48:
                _draw_mark(img)
            images.append(img)

        ico_path = os.path.join('static', 'images', 'icon.ico')
        os.makedirs(os.path.dirname(ico_path), exist_ok=True)
        images[-1].save(ico_path, format='ICO', sizes=[(s, s) for s in sizes],
                        append_images=images[:-1])

        png_path = os.path.join('static', 'images', 'favicon.png')
        images[-1].save(png_path, format='PNG')
        print("✓ آیکون ساخته شد (icon.ico + favicon.png)")
        return True
    except ImportError:
        print("⚠ Pillow نصب نیست — آیکون SVG ساخته می‌شود")
        create_simple_ico()
        return False


def create_pwa_icons(sizes=(192, 512), extra=(48, 96, 144, 168, 384)):
    """آیکون‌های PWA: PNG‌های معمولی + maskable + apple-touch-icon (۱۸۰)."""
    try:
        from PIL import Image
    except ImportError:
        print("⚠ Pillow نصب نیست — آیکون‌های PWA ساخته نشدند")
        return []

    out_dir = os.path.join('static', 'images', 'icons')
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for size in list(sizes) + list(extra):
        img = _gradient_tile(size)
        _draw_mark(img)
        path = os.path.join(out_dir, f'icon-{size}.png')
        img.save(path, format='PNG', optimize=True)
        written.append(path)

    for size in (192, 512):
        img = _gradient_tile(size)
        _draw_mark(img, safe=0.10)      # داخل دایره امن آیکون ماسکه‌بل بیفتد
        path = os.path.join(out_dir, f'icon-maskable-{size}.png')
        img.save(path, format='PNG', optimize=True)
        written.append(path)

    # پس‌زمینه کامل برای ماسکه‌بل (Android آن را crop می‌کند)
    img = Image.new('RGBA', (512, 512), BRAND_TOP + (255,))
    _draw_mark(img, safe=0.16)
    path = os.path.join(out_dir, 'icon-maskable-512-solid.png')
    img.save(path, format='PNG', optimize=True)
    written.append(path)

    img = _gradient_tile(180)
    _draw_mark(img)
    path = os.path.join(out_dir, 'apple-touch-icon.png')
    img.save(path, format='PNG', optimize=True)
    written.append(path)

    print(f"✓ {len(written)} آیکون PWA ساخته شد در {out_dir}")
    return written


def create_simple_ico():
    """ساخت آیکون ساده با استفاده از SVG"""
    svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0d47a1"/>
      <stop offset="100%" stop-color="#00c853"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="40" fill="url(#bg)"/>
  <g stroke="white" stroke-width="18" stroke-linecap="round" fill="none">
    <path d="M70 92h116"/><path d="M70 128h90"/><path d="M70 164h64"/>
    <path d="M78 200l22 22 44-46"/>
  </g>
</svg>'''
    svg_path = os.path.join('static', 'images', 'icon.svg')
    os.makedirs(os.path.dirname(svg_path), exist_ok=True)
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    print("✓ آیکون SVG ساخته شد")


if __name__ == '__main__':
    create_icon()
    create_pwa_icons()
