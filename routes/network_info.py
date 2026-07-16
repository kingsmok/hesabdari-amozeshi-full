"""
مسیر اطلاعات شبکه — نمایش آدرس‌های دقیق اتصال
"""
import socket
import platform
import os
from datetime import datetime
from flask import Blueprint, render_template, jsonify
from flask_login import login_required
from extensions import db

network_bp = Blueprint('network', __name__)


def get_network_info():
    """جمع‌آوری اطلاعات شبکه"""
    hostname = socket.gethostname()
    
    # IP محلی
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"
    
    # تمام IP‌ها
    all_ips = []
    try:
        all_ips = socket.gethostbyname_ex(hostname)[2]
    except:
        pass
    
    # پورت‌های باز
    port = 5000  # پورت پیش‌فرض Flask
    
    return {
        'hostname': hostname,
        'local_ip': local_ip,
        'all_ips': all_ips,
        'port': port,
        'platform': platform.system(),
        'platform_release': platform.release(),
        'platform_version': platform.version(),
        'python_version': platform.python_version(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'urls': {
            'local': f'http://localhost:{port}',
            'network': f'http://{local_ip}:{port}',
            'network_info': f'http://{local_ip}:{port}/network-info',
            'login': f'http://{local_ip}:{port}/login',
        }
    }


@network_bp.route('/network-info')
def network_info():
    """صفحه اطلاعات شبکه"""
    info = get_network_info()
    return render_template('network/info.html', info=info)


@network_bp.route('/api/network')
@login_required
def api_network():
    """API اطلاعات شبکه"""
    return jsonify(get_network_info())
