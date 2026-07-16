"""
ساخت آیکون برنامه — Academy Manager Pro
اجرا: python create_icon.py
"""
import os

def create_icon():
    """ساخت آیکون با Pillow یا SVG"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        sizes = [16, 32, 48, 64, 128, 256]
        images = []
        
        for size in sizes:
            img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # پس‌زمینه گرادیانت سبز-آبی
            for i in range(size):
                r = int(0 + (0 - 0) * i / size)
                g = int(71 + (200 - 71) * i / size)
                b = int(161 + (83 - 161) * i / size)
                draw.line([(0, i), (size, i)], fill=(r, g, b, 255))
            
            # گوشه‌های گرد
            mask = Image.new('L', (size, size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([(0, 0), (size-1, size-1)], 
                                         radius=size//6, fill=255)
            img.putalpha(mask)
            
            # متن AM
            try:
                font_size = size // 3
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                font = ImageFont.load_default()
            
            text = "AM"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (size - text_w) // 2
            y = (size - text_h) // 2 - bbox[1]
            draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
            
            images.append(img)
        
        # ذخیره ICO
        ico_path = os.path.join('static', 'images', 'icon.ico')
        os.makedirs(os.path.dirname(ico_path), exist_ok=True)
        images[-1].save(ico_path, format='ICO', 
                       sizes=[(s, s) for s in sizes],
                       append_images=images[:-1])
        
        # ذخیره PNG برای favicon
        png_path = os.path.join('static', 'images', 'favicon.png')
        images[-1].save(png_path, format='PNG')
        
        print("✓ آیکون ساخته شد (icon.ico + favicon.png)")
        return True
        
    except ImportError:
        print("⚠ Pillow نصب نیست — آیکون پیش‌فرض استفاده می‌شود")
        # ساخت آیکون ساده بدون Pillow
        create_simple_ico()
        return False

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
  <text x="128" y="150" font-family="Arial,sans-serif" font-size="100" 
        font-weight="bold" fill="white" text-anchor="middle">AM</text>
</svg>'''
    
    svg_path = os.path.join('static', 'images', 'icon.svg')
    os.makedirs(os.path.dirname(svg_path), exist_ok=True)
    with open(svg_path, 'w') as f:
        f.write(svg_content)
    print("✓ آیکون SVG ساخته شد")

if __name__ == '__main__':
    create_icon()
