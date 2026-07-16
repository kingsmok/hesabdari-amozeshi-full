"""Messaging routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from utils.form_helpers import get_jalali_date, safe_float, safe_int
from models.system import Message, MessageTemplate, InternalMessage, Notification
from models.student import Student
from models.teacher import Teacher
from datetime import datetime

messaging_bp = Blueprint('messaging', __name__)


@messaging_bp.route('/sms')
@login_required
def sms():
    page = request.args.get('page', 1, type=int)
    messages = Message.query.order_by(Message.created_at.desc()).paginate(page=page, per_page=30)
    return render_template('messaging/sms.html', messages=messages)


@messaging_bp.route('/sms/send', methods=['GET', 'POST'])
@login_required
def send_sms():
    if request.method == 'POST':
        recipient_type = request.form.get('recipient_type')
        message_text = request.form['message_text']
        phones = request.form.getlist('phones')
        
        if not phones:
            phone = request.form.get('phone')
            if phone:
                phones = [phone]
        
        for phone in phones:
            msg = Message(
                recipient_type=recipient_type,
                phone=phone,
                message_text=message_text,
                send_type='manual',
                status='pending',
                created_by=current_user.id
            )
            db.session.add(msg)
        
        db.session.commit()
        flash(f'{len(phones)} پیامک ارسال شد', 'success')
        return redirect(url_for('messaging.sms'))
    
    students = Student.query.filter_by(status='active').all()
    teachers = Teacher.query.filter_by(is_active=True).all()
    templates = MessageTemplate.query.filter_by(is_active=True).all()
    
    return render_template('messaging/send_sms.html', students=students, teachers=teachers, templates=templates)


@messaging_bp.route('/sms/group', methods=['GET', 'POST'])
@login_required
def group_sms():
    if request.method == 'POST':
        target = request.form.get('target')  # class, all_students, all_teachers
        class_id = request.form.get('class_id')
        message_text = request.form['message_text']
        
        phones = []
        if target == 'class' and class_id:
            from models.registration import Registration
            regs = Registration.query.filter_by(class_id=class_id, status='active').all()
            phones = [r.student.mobile for r in regs if r.student.mobile]
        elif target == 'all_students':
            students = Student.query.filter_by(status='active').all()
            phones = [s.mobile for s in students if s.mobile]
        elif target == 'all_teachers':
            teachers = Teacher.query.filter_by(is_active=True).all()
            phones = [t.mobile for t in teachers if t.mobile]
        
        for phone in phones:
            msg = Message(
                recipient_type='group',
                phone=phone,
                message_text=message_text,
                send_type='manual',
                status='pending',
                created_by=current_user.id
            )
            db.session.add(msg)
        
        db.session.commit()
        flash(f'{len(phones)} پیامک ارسال شد', 'success')
        return redirect(url_for('messaging.sms'))
    
    from models.classes import ClassGroup
    classes = ClassGroup.query.filter_by(status='active').all()
    return render_template('messaging/group_sms.html', classes=classes)


# ===== Internal Messaging =====
@messaging_bp.route('/inbox')
@login_required
def inbox():
    messages = InternalMessage.query.filter_by(receiver_id=current_user.id).order_by(
        InternalMessage.created_at.desc()
    ).all()
    return render_template('messaging/inbox.html', messages=messages)


@messaging_bp.route('/sent')
@login_required
def sent():
    messages = InternalMessage.query.filter_by(sender_id=current_user.id).order_by(
        InternalMessage.created_at.desc()
    ).all()
    return render_template('messaging/sent.html', messages=messages)


@messaging_bp.route('/compose', methods=['GET', 'POST'])
@login_required
def compose():
    if request.method == 'POST':
        msg = InternalMessage(
            sender_id=current_user.id,
            receiver_id=safe_int(request.form.get('receiver_id')),
            subject=request.form.get('subject'),
            body=request.form['body']
        )
        db.session.add(msg)
        db.session.commit()
        flash('پیام ارسال شد', 'success')
        return redirect(url_for('messaging.inbox'))
    
    from models.user import User
    users = User.query.filter(User.id != current_user.id, User.is_active == True).all()
    return render_template('messaging/compose.html', users=users)


@messaging_bp.route('/message/<int:id>')
@login_required
def view_message(id):
    msg = InternalMessage.query.get_or_404(id)
    if msg.receiver_id == current_user.id and not msg.is_read:
        msg.is_read = True
        msg.read_at = datetime.utcnow()
        db.session.commit()
    return render_template('messaging/view_message.html', message=msg)


# ===== Notifications =====
@messaging_bp.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    
    # Mark as read
    for n in notifs:
        if not n.is_read:
            n.is_read = True
            n.read_at = datetime.utcnow()
    db.session.commit()
    
    return render_template('messaging/notifications.html', notifications=notifs)
