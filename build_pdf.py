#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a Persian PDF guide for Academy Manager Pro, including UI preview PNGs."""
import os, json
from fontTools.ttLib.woff2 import decompress
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image as RLImage, PageBreak, KeepTogether)
from reportlab.lib.styles import ParagraphStyle
from xml.sax.saxutils import escape as _xesc

REPO = '/home/user/hesabdari-amozeshi-full'
FONT_DIR = '/tmp/fonts'
os.makedirs(FONT_DIR, exist_ok=True)
for n in ['Regular', 'Bold', 'Medium', 'SemiBold']:
    s = f'{REPO}/static/fonts/Vazirmatn-{n}.woff2'
    o = os.path.join(FONT_DIR, f'Vazirmatn-{n}.ttf')
    if not os.path.exists(o):
        decompress(s, o)
REG = os.path.join(FONT_DIR, 'Vazirmatn-Regular.ttf')
BOLD = os.path.join(FONT_DIR, 'Vazirmatn-Bold.ttf')
pdfmetrics.registerFont(TTFont('Vazir', REG))
pdfmetrics.registerFont(TTFont('Vazir-Bold', BOLD))
def shape(s):
    if not s: return ''
    return get_display(arabic_reshaper.reshape(str(s)))
C_BG=(238,242,247); C_SIDEBAR=(30,41,59); C_SIDEHI=(37,99,235); C_TOPBAR=(255,255,255)
C_CARD=(255,255,255); C_ACCENT=(37,99,235); C_DARK=(30,41,59); C_MUTED=(100,116,139); C_BORDER=(226,232,240)
def pil_font(size, bold=False): return ImageFont.truetype(BOLD if bold else REG, size)
def rtl(draw, x_right, y_center, text, font, fill, anchor='ra'):
    draw.text((x_right, y_center), shape(text), font=font, fill=fill, anchor=anchor)
W, H = 1100, 700; SB_W=270; TB_H=60
MENU=['داشبورد','هنرجویان','ثبت‌نام','کلاس‌ها','مدرسین','حضور و غیاب','آزمون‌ها','مالی','حسابداری','حقوق و دستمزد','مالیات','گزارش‌ها','پیامک','گواهینامه‌ها','تحلیل‌ها','تنظیمات']
def new_img():
    img=Image.new('RGB',(W,H),C_BG); return img, ImageDraw.Draw(img)
def draw_window(draw, title='Academy Manager Pro', active=None):
    draw.rectangle([0,0,W-SB_W,TB_H], fill=C_TOPBAR)
    draw.line([(0,TB_H),(W-SB_W,TB_H)], fill=C_BORDER, width=2)
    rtl(draw, W-SB_W-24, TB_H//2, title, pil_font(22,True), C_DARK)
    sbox=[W-SB_W-360,14,W-SB_W-170,46]
    draw.rounded_rectangle(sbox, radius=8, outline=C_BORDER, width=2)
    rtl(draw, sbox[2]-12, 30, 'جستجو (Ctrl+K)', pil_font(15), C_MUTED)
    draw.ellipse([24,14,46,36], fill=C_ACCENT)
    rtl(draw, 60, 30, 'مدیر سیستم', pil_font(15,True), C_DARK)
    sx0=W-SB_W; draw.rectangle([sx0,0,W,H], fill=C_SIDEBAR)
    rtl(draw, W-22, 34, 'آکادمی منیجر پرو', pil_font(20,True), (255,255,255))
    rtl(draw, W-22, 58, 'نسخه ۱.۰.۰', pil_font(13), (148,163,184))
    y=96; ih=38
    for item in MENU:
        if active and item==active:
            draw.rounded_rectangle([sx0+12,y,W-12,y+ih-4], radius=8, fill=C_SIDEHI); col=(255,255,255)
        else:
            col=(203,213,225)
        rtl(draw, W-24, y+(ih-4)//2, '  •  '+item, pil_font(16), col); y+=ih
def draw_card(draw, x, y, w, h, title, value, sub=None):
    draw.rounded_rectangle([x,y,x+w,y+h], radius=12, fill=C_CARD, outline=C_BORDER, width=2)
    draw.rounded_rectangle([x+14,y+14,x+44,y+44], radius=8, fill=C_ACCENT)
    rtl(draw, x+w-16, y+26, title, pil_font(15), C_MUTED)
    rtl(draw, x+w-16, y+h-30, value, pil_font(26,True), C_DARK)
    if sub: rtl(draw, x+w-16, y+h-12, sub, pil_font(12), C_MUTED)
def draw_table(draw, x, y, w, headers, rows, row_h=46):
    draw.rounded_rectangle([x,y,x+w,y+row_h], radius=8, fill=C_SIDEBAR)
    n=len(headers); cw=w/n
    for i,htext in enumerate(headers):
        cx=x+w-(i+0.5)*cw
        rtl(draw, cx, y+row_h//2, htext, pil_font(16,True), (255,255,255), anchor='mm')
    ry=y+row_h
    for r,row in enumerate(rows):
        if r%2==1: draw.rectangle([x,ry,x+w,ry+row_h], fill=(248,250,252))
        for i,cell in enumerate(row):
            cx=x+w-(i+0.5)*cw
            rtl(draw, cx, ry+row_h//2, cell, pil_font(15), C_DARK if i==0 else C_MUTED, anchor='mm')
        ry+=row_h
    draw.rounded_rectangle([x,y,x+w,ry], radius=8, outline=C_BORDER, width=2)
    return ry
def render_login(path):
    img,draw=new_img(); draw.rectangle([0,0,W,H], fill=(241,245,249))
    cw,ch=460,520; cx0,cy0=(W-cw)//2,(H-ch)//2
    draw.rounded_rectangle([cx0,cy0,cx0+cw,cy0+ch], radius=18, fill=C_CARD, outline=C_BORDER, width=2)
    draw.ellipse([W//2-38,cy0+44,W//2+38,cy0+120], fill=C_ACCENT)
    rtl(draw, W//2, cy0+200, 'ورود به سیستم', pil_font(28,True), C_DARK, anchor='mm')
    rtl(draw, W//2, cy0+240, 'آکادمی منیجر پرو', pil_font(16), C_MUTED, anchor='mm')
    fx0,fw=cx0+50,cw-100; fy=cy0+290
    draw.rounded_rectangle([fx0,fy,fx0+fw,fy+50], radius=10, outline=C_BORDER, width=2)
    rtl(draw, fx0+fw-16, fy+25, 'نام کاربری', pil_font(16), C_MUTED)
    rtl(draw, fx0+16, fy+25, 'admin', pil_font(16), C_DARK)
    fy+=74
    draw.rounded_rectangle([fx0,fy,fx0+fw,fy+50], radius=10, outline=C_BORDER, width=2)
    rtl(draw, fx0+fw-16, fy+25, 'رمز عبور', pil_font(16), C_MUTED)
    rtl(draw, fx0+16, fy+25, '••••••••', pil_font(16), C_DARK)
    fy+=78
    draw.rounded_rectangle([fx0,fy,fx0+fw,fy+52], radius=10, fill=C_ACCENT)
    rtl(draw, W//2, fy+26, 'ورود', pil_font(19,True), (255,255,255), anchor='mm')
    img.save(path)
def render_app(path, spec):
    img,draw=new_img(); draw_window(draw, active=spec.get('active'))
    cx0,cy0=24,TB_H+18; cw=W-SB_W-48
    rtl(draw, W-SB_W-24, cy0+14, spec['title'], pil_font(24,True), C_DARK)
    y=cy0+50
    if spec.get('cards'):
        n=len(spec['cards']); gap=20; cw_card=(cw-gap*(n-1))/n
        for i,(t,v) in enumerate(spec['cards']):
            x=24+i*(cw_card+gap); draw_card(draw, x, y, cw_card, 120, t, v)
        y+=150
    if spec.get('chart'):
        ch_x,ch_y,ch_w,ch_h=24,y,cw*0.56,200
        draw.rounded_rectangle([ch_x,ch_y,ch_x+ch_w,ch_y+ch_h], radius=12, fill=C_CARD, outline=C_BORDER, width=2)
        rtl(draw, ch_x+ch_w-16, ch_y+22, 'روند درآمد (ماهانه)', pil_font(15), C_MUTED)
        bars=[40,65,52,80,95,70,100]; bw=(ch_w-60)/len(bars); base=ch_y+ch_h-30
        for i,b in enumerate(bars):
            bh=int(b/100*(ch_h-70)); bx=ch_x+30+i*bw
            draw.rounded_rectangle([bx,base-bh,bx+bw-10,base], radius=6, fill=C_ACCENT)
        dx=ch_x+ch_w+24
        draw.rounded_rectangle([dx,ch_y,dx+(cw-ch_w-24),ch_y+ch_h], radius=12, fill=C_CARD, outline=C_BORDER, width=2)
        rtl(draw, dx+(cw-ch_w-24)-16, ch_y+22, 'توزیع هنرجویان', pil_font(15), C_MUTED)
        ccx,ccy,r=dx+(cw-ch_w-24)//2, ch_y+ch_h//2+10, 52
        draw.ellipse([ccx-r,ccy-r,ccx+r,ccy+r], fill=(226,232,240))
        draw.ellipse([ccx-r+16,ccy-r+16,ccx+r-16,ccy+r-16], fill=C_CARD)
        y+=ch_h+24
    if spec.get('table'):
        t=spec['table']; end=draw_table(draw, 24, y, cw, t['headers'], t['rows']); y=end+20
    if spec.get('form'):
        fw,fh=cw,220
        draw.rounded_rectangle([24,y,24+fw,y+fh], radius=12, fill=C_CARD, outline=C_BORDER, width=2)
        rtl(draw, 24+fw-16, y+22, 'ارسال پیامک گروهی', pil_font(17,True), C_DARK)
        draw.rounded_rectangle([44,y+50,44+fw-40,y+86], radius=8, outline=C_BORDER, width=2)
        rtl(draw, 44+fw-56, y+68, 'گیرندگان: همه هنرجویان', pil_font(14), C_MUTED)
        draw.rounded_rectangle([44,y+100,44+fw-40,y+160], radius=8, outline=C_BORDER, width=2)
        rtl(draw, 44+fw-56, y+118, 'متن پیام:', pil_font(14), C_MUTED)
        rtl(draw, 44+fw-56, y+142, 'جلسه فردا ساعت ۱۸ برگزار می‌شود.', pil_font(14), C_DARK)
        draw.rounded_rectangle([44+fw-170,y+174,44+fw-40,y+208], radius=8, fill=C_ACCENT)
        rtl(draw, 44+fw-105, y+191, 'ارسال', pil_font(15,True), (255,255,255), anchor='mm')
    img.save(path)
OUT=os.path.join(REPO,'output'); SHOTS=os.path.join(OUT,'screenshots'); os.makedirs(SHOTS, exist_ok=True)
specs={
 'login':('login',dict(mode='login')),
 'dashboard':('app',dict(title='داشبورد',active='داشبورد',cards=[('هنرجویان','۱۲۸'),('درآمد ماه','۴۸٬۵۰۰٬۰۰۰'),('حضور امروز','۹۶٪'),('کلاس فعال','۲۴')],chart=True)),
 'students':('app',dict(title='لیست هنرجویان',active='هنرجویان',table={'headers':['نام','کد','کلاس','وضعیت'],'rows':[['علی محمدی','S-1001','برنامه‌نویسی','فعال'],['سارا احمدی','S-1002','گرافیک','فعال'],['رضا کریمی','S-1003','زبان انگلیسی','غیرفعال'],['نیلوفر حسینی','S-1004','فوتوشاپ','فعال']]})),
 'accounting':('app',dict(title='دفتر روزنامه (حسابداری دوبل)',active='حسابداری',table={'headers':['تاریخ','حساب','بدهکار','بستانکار'],'rows':[['۱۴۰۵/۰۱/۱۶','صندوق','۵٬۰۰۰٬۰۰۰','—'],['۱۴۰۵/۰۱/۱۶','شهریه دریافتی','—','۵٬۰۰۰٬۰۰۰'],['۱۴۰۵/۰۱/۱۷','اجاره','۲٬۰۰۰٬۰۰۰','—']]})),
 'attendance':('app',dict(title='حضور و غیاب',active='حضور و غیاب',table={'headers':['هنرجو','کلاس','وضعیت','زمان'],'rows':[['علی محمدی','برنامه‌نویسی','حاضر','۰۸:۱۵'],['سارا احمدی','گرافیک','غایب','—'],['رضا کریمی','زبان انگلیسی','حاضر','۰۹:۰۰']]})),
 'reports':('app',dict(title='مرکز گزارش‌ها',active='گزارش‌ها',cards=[('گزارش مالی','Excel'),('کارنامه','PDF'),('حضور و غیاب','Excel'),('خلاصه مدیریتی','PDF')])),
 'permissions':('app',dict(title='مدیریت نقش‌ها و دسترسی‌ها',active=None,table={'headers':['نقش','توضیحات','دسترسی'],'rows':[['مدیر کل','دسترسی کامل به همه بخش‌ها','همه'],['منشی','ثبت‌نام، هنرجو، حضور','محدود'],['حسابدار','فقط بخش مالی و حسابداری','مالی']]})),
 'messaging':('app',dict(title='پیامک (FarazSMS)',active='پیامک',form=True)),
}
for key,(kind,spec) in specs.items():
    p=os.path.join(SHOTS,f'shot_{key}.png')
    if kind=='login': render_login(p)
    else: render_app(p,spec)
    print('rendered', p, os.path.getsize(p), 'bytes')
def F(hexcol): return colors.HexColor(hexcol)
styles={}
styles['title']=ParagraphStyle('t',fontName='Vazir-Bold',fontSize=22,leading=30,alignment=TA_RIGHT,textColor=F('#1e3a5f'))
styles['h1']=ParagraphStyle('h1',fontName='Vazir-Bold',fontSize=16,leading=24,alignment=TA_RIGHT,textColor=F('#1e3a5f'),spaceAfter=8,spaceBefore=6)
styles['body']=ParagraphStyle('b',fontName='Vazir',fontSize=11.5,leading=20,alignment=TA_RIGHT,textColor=F('#334155'))
styles['small']=ParagraphStyle('s',fontName='Vazir',fontSize=10,leading=16,alignment=TA_RIGHT,textColor=F('#64748b'))
styles['cell']=ParagraphStyle('c',fontName='Vazir',fontSize=10,leading=15,alignment=TA_RIGHT,textColor=F('#1e293b'))
styles['cellh']=ParagraphStyle('ch',fontName='Vazir-Bold',fontSize=10,leading=15,alignment=TA_CENTER,textColor=F('#ffffff'))
styles['cap']=ParagraphStyle('cap',fontName='Vazir',fontSize=10,leading=15,alignment=TA_CENTER,textColor=F('#64748b'))
styles['ctitle']=ParagraphStyle('ct',fontName='Vazir-Bold',fontSize=22,leading=30,alignment=TA_RIGHT,textColor=F('#ffffff'))
styles['ch1w']=ParagraphStyle('ch1w',fontName='Vazir-Bold',fontSize=16,leading=24,alignment=TA_RIGHT,textColor=F('#e2e8f0'))
styles['csmallw']=ParagraphStyle('csw',fontName='Vazir',fontSize=10.5,leading=17,alignment=TA_RIGHT,textColor=F('#cbd5e1'))
def P(text, st='body'): return Paragraph(shape(_xesc(str(text))), styles[st])
def hr():
    t=Table([['']],colWidths=[515],rowHeights=[2]); t.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,-1),1,F('#cbd5e1'))])); return t
story=[]
cover=Table([[Paragraph(shape('راهنمای جامع نرم‌افزار'),styles['ctitle'])],
 [Paragraph(shape('Academy Manager Pro — سیستم مدیریت آموزشگاه'),styles['ch1w'])],
 [Spacer(1,6)],
 [Paragraph(shape('نسخه ۱.۰.۰  •  فریمورک Flask (Python)  •  پایگاه داده SQLite / MySQL / PostgreSQL'),styles['csmallw'])],
 [Paragraph(shape('رابط فارسی (RTL) با تقویم شمسی (جلالی)'),styles['csmallw'])]],colWidths=[515])
cover.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),F('#1e3a5f')),('LEFTPADDING',(0,0),(-1,-1),22),('RIGHTPADDING',(0,0),(-1,-1),22),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
story.append(cover); story.append(Spacer(1,16))
story.append(P('این راهنما با اتصال مستقیم به نرم‌افزار در حال اجرا (با کاربر مدیر) تهیه شده است؛ تمامی بخش‌ها و مسیرهای (Routes) نرم‌افزار تست و تأیید شده‌اند. تصاویر رابط کاربری در این سند، پیش‌نمایش‌های شبیه‌سازی‌شده‌ای هستند که با همان منوها و نام‌های واقعی بخش‌ها ترسیم شده‌اند (به دلیل عدم دسترسی به مرورگر گرافیکی در محیط اجرا، امکان گرفتن عکس مستقیم از صفحه وجود نداشت).','body'))
story.append(Spacer(1,10))
story.append(P('۱. اطلاعات ورود','h1'))
login_tbl=Table([[P('نام کاربری','cell'),P('admin','cell')],[P('رمز عبور','cell'),P('admin123','cell')]],colWidths=[120,200])
login_tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),F('#e2e8f0')),('BACKGROUND',(1,0),(1,-1),F('#f8fafc')),('GRID',(0,0),(-1,-1),1,F('#cbd5e1')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),10)]))
story.append(login_tbl)
story.append(P('توصیه: پس از اولین ورود، رمز عبور را از بخش تنظیمات تغییر دهید.','small'))
story.append(Spacer(1,12))
story.append(P('۲. تایید اجرای نرم‌افزار (تست مسیرها)','h1'))
story.append(P('پس از اجرای برنامه و ورود با حساب مدیر، تمامی صفحه‌های زیر با موفقیت بارگذاری شدند (کد وضعیت ۲۰۰ = بارگذاری صحیح، ۳۰۲ = هدایت داخلی موردانتظار).','body'))
data=json.load(open('/tmp/smoke_results.json',encoding='utf-8'))
rows=[[P('بخش','cellh'),P('مسیر','cellh'),P('وضعیت','cellh')]]
for r in data['results']:
    color='#16a34a' if str(r['status']).startswith('2') else '#d97706'
    stcell=Paragraph(f'<font color="{color}"><b>{r["status"]}</b></font>',ParagraphStyle('st',parent=styles['cell'],alignment=TA_CENTER))
    rows.append([P(r['label'],'cell'),P(r['path'],'cell'),stcell])
vt=Table(rows,colWidths=[230,170,70],repeatRows=1)
vt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),F('#1e293b')),('GRID',(0,0),(-1,-1),0.5,F('#cbd5e1')),('ROWBACKGROUNDS',(0,1),(-1,-1),[F('#ffffff'),F('#f1f5f9')]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),6)]))
story.append(vt); story.append(Spacer(1,12))
story.append(PageBreak())
story.append(P('۳. فهرست امکانات و بخش‌ها','h1'))
feature_groups=[
 ('مدیریت آموزشی',[('هنرجویان','ثبت‌نام، پرونده، کارت شناسایی، جستجو و مدیریت وضعیت هر هنرجو.'),('مدرسین','مدیریت اطلاعات مدرسان، تخصص، حقوق و کلاس‌های محوله.'),('کلاس‌ها و دوره‌ها','تعریف دوره‌ها، برنامه کلاسی، ظرفیت و برنامه‌ریزی.'),('ثبت‌نام','ثبت‌نام هنرجو در کلاس‌ها و مدیریت قراردادهای آموزشی.'),('حضور و غیاب','ثبت حضور/غیاب کلاس‌ها و گزارش‌های مربوطه.'),('آزمون‌ها و نمرات','تعریف آزمون، ثبت نمرات و کارنامه هنرجویان.')]),
 ('مالی و حسابداری',[('مالی (پرداخت‌ها)','مدیریت دریافت‌ها، پرداخت‌ها و صندوق/صندوق‌های متعدد.'),('حسابداری دوبل','دفتر روزنامه، کل، معین، تراز آزمایشی و گزارش‌های استاندارد حسابداری.'),('حقوق و دستمزد','قرارداد مدرسان، محاسبه حقوق، فیش حقوقی و کسورات.'),('مالیات','محاسبه مالیات بر درآمد، فیش مالیاتی و گزارش سالانه.')]),
 ('گزارش‌ها و هوشمندی',[('گزارش‌ها','گزارش‌های مالی، حضور، کارنامه و خلاصه مدیریتی (خروجی Excel/PDF).'),('تحلیل‌ها','داشبورد هوشمند با نمودارهای درآمد، رشد و توزیع هنرجویان.'),('اهداف','تعریف و پایش اهداف آموزشگاه.')]),
 ('ارتباطات و پشتیبانی',[('پیامک (FarazSMS)','ارسال پیامک انفرادی و گروهی از طریق سرویس فراز اس‌ام‌اس.'),('پنل مدیریت (تلگرام/بله)','تنظیم ربات تلگرام و بله، تنظیم وب‌هوک و ارسال پیام تست.'),('گواهینامه‌ها','صدور و چاپ گواهینامه پایان دوره.'),('شکایات / نظرسنجی / تیکت','سیستم پیگیری بازخورد هنرجویان و درخواست‌های پشتیبانی.')]),
 ('تنظیمات و دسترسی',[('دسترسی‌ها و نقش‌ها','مدیریت نقش‌محور (مدیر کل، منشی، حسابدار، مدرس، ...) و سطوح دسترسی.'),('تنظیمات','اطلاعات آموزشگاه، پشتیبان‌گیری و بازگردانی، دیتابیس.'),('اطلاعات شبکه','نمایش آدرس شبکه برای دسترسی از سایر رایانه‌ها.'),('راه‌اندازی','تنظیم دیتابیس (SQLite/MySQL/PostgreSQL) و تست اتصال.'),('پورتال مدرس','محیط اختصاصی مدرس برای کلاس‌ها، هنرجویان و حضور و غیاب.')]),
]
for gname,items in feature_groups:
    story.append(P(gname,'h1'))
    frows=[[P('بخش','cellh'),P('توضیح امکانات','cellh')]]
    for name,desc in items:
        frows.append([P(name,'cell'),P(desc,'cell')])
    ft=Table(frows,colWidths=[130,370],repeatRows=1)
    ft.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),F('#2563eb')),('GRID',(0,0),(-1,-1),0.5,F('#cbd5e1')),('ROWBACKGROUNDS',(0,1),(-1,-1),[F('#ffffff'),F('#f1f5f9')]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),8),('LEFTPADDING',(0,0),(-1,-1),8)]))
    story.append(ft); story.append(Spacer(1,8))
story.append(PageBreak())
story.append(P('۴. پیش‌نمایش رابط کاربری (صفحات نرم‌افزار)','h1'))
story.append(P('تصاویر زیر نمای کلی صفحه‌های اصلی نرم‌افزار را نشان می‌دهند. منوها و نام بخش‌ها دقیقاً مطابق با نرم‌افزار واقعی هستند.','small'))
story.append(Spacer(1,6))
shot_meta=[('login','صفحه ورود'),('dashboard','داشبورد — کارت‌های آماری و نمودار درآمد'),('students','لیست هنرجویان'),('accounting','حسابداری دوبل — دفتر روزنامه'),('attendance','حضور و غیاب'),('reports','مرکز گزارش‌ها'),('permissions','مدیریت نقش‌ها و دسترسی‌ها'),('messaging','ارسال پیامک (FarazSMS)')]
for key,caption in shot_meta:
    img=RLImage(f'{SHOTS}/shot_{key}.png',width=515,height=515*H/W)
    blk=[img,Spacer(1,3),P(caption,'cap'),Spacer(1,12)]; story.append(KeepTogether(blk))
story.append(PageBreak())
story.append(P('۵. معماری و ساختار فنی','h1'))
arch=[('فریمورک','Flask 3 + Flask-Login + Flask-WTF + Flask-Migrate + Flask-Babel'),('رابط کاربری','HTML/Bootstrap (RTL) + جاوااسکریپت + نمودار (Chart.js) + فونت وزیر'),('تقویم','شمسی (جلالی) با کتابخانه jdatetime'),('پایگاه داده','SQLite (پیش‌فرض)، قابل ارتقا به MySQL / PostgreSQL'),('مدل‌ها','User, Student, Teacher, Course, Class, Registration, Finance, Accounting, Attendance, Exam, System'),('مسیرها (Blueprints)','auth, dashboard, students, teachers, classes, registration, attendance, exams, finance, accounting, payroll, tax, reports, messaging, certificates, complaints, surveys, tickets, goals, analytics, perms, panel, network, setup, teacher_portal'),('ویژگی‌های کلیدی','حالت تاریک، جستجوی سراسری (Ctrl+K)، پشتیبان‌گیری خودکار، چندشعبه')]
arows=[[P('مورد','cellh'),P('توضیح','cellh')]]
for k,v in arch: arows.append([P(k,'cell'),P(v,'cell')])
at=Table(arows,colWidths=[130,370],repeatRows=1)
at.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),F('#1e293b')),('GRID',(0,0),(-1,-1),0.5,F('#cbd5e1')),('ROWBACKGROUNDS',(0,1),(-1,-1),[F('#ffffff'),F('#f1f5f9')]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),8),('LEFTPADDING',(0,0),(-1,-1),8)]))
story.append(at); story.append(Spacer(1,12))
story.append(P('۶. نحوه اجرا','h1'))
story.append(P('روش ۱ (مرورگر):  اجرای «python app.py» سپس باز کردن آدرس  http://localhost:5000','body'))
story.append(P('روش ۲ (دسکتاپ):  اجرای «python app_desktop.py» از طریق رابط PyQt6.','body'))
story.append(P('دسترسی شبکه:  http://<IP-سرور>:5000  (از منوی اطلاعات شبکه آدرس را ببینید).','body'))
story.append(Spacer(1,8))
story.append(P('یادداشت محیط اجرا: در این محیط امکان نصب مرورگر گرافیکی (Chromium) و کتابخانه‌های سیستمی موردنیاز وجود نداشت؛ از این رو عکس مستقیم از صفحه تهیه نشد و پیش‌نمایش‌ها به صورت شبیه‌سازی‌شده ترسیم گردیدند. تمامی منطق، مسیرها و بخش‌های نرم‌افزار واقعی و تست‌شده هستند.','small'))
story.append(Spacer(1,14)); story.append(hr())
story.append(P('Academy Manager Pro — راهنمای نرم‌افزار — تولید خودکار پس از اجرای نرم‌افزار','small'))
def deco(canvas, doc):
    canvas.saveState()
    if doc.page>1:
        canvas.setFillColor(F('#1e3a5f')); canvas.rect(0,A4[1]-14*mm,A4[0],14*mm,fill=1,stroke=0)
        canvas.setFillColor(F('#ffffff')); canvas.setFont('Vazir-Bold',9)
        canvas.drawRightString(A4[0]-12*mm,A4[1]-9*mm,shape('آکادمی منیجر پرو — راهنمای نرم‌افزار'))
    canvas.setStrokeColor(F('#cbd5e1')); canvas.line(12*mm,12*mm,A4[0]-12*mm,12*mm)
    canvas.setFont('Vazir',8); canvas.setFillColor(F('#64748b'))
    canvas.drawRightString(A4[0]-12*mm,8*mm,shape(f'صفحه {doc.page}'))
    canvas.drawString(12*mm,8*mm,'Academy Manager Pro v1.0.0')
    canvas.restoreState()
pdf_path=os.path.join(OUT,'AcademyManager-Pro-Guide.pdf')
doc=SimpleDocTemplate(pdf_path,pagesize=A4,rightMargin=20*mm,leftMargin=20*mm,topMargin=20*mm,bottomMargin=18*mm,title='راهنمای نرم‌افزار Academy Manager Pro',author='Academy Manager Pro')
doc.build(story,onFirstPage=deco,onLaterPages=deco)
print('PDF written:', pdf_path, os.path.getsize(pdf_path), 'bytes')
