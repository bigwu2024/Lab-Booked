# -*- coding: utf-8 -*-
"""
实验室超净台预约系统 - 后端服务
Flask + SQLite，提供 RESTful API
支持用户注册/登录、邮件提醒
"""

import os
import re
import json
import sqlite3
import hashlib
import secrets
import threading
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'booking.db')
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'email_config.json')


# ==================== 数据库工具 ====================

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT DEFAULT '',
            status TEXT DEFAULT 'available' CHECK(status IN ('available', 'maintenance', 'offline')),
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            real_name TEXT DEFAULT '',
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            group_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            role TEXT DEFAULT 'user' CHECK(role IN ('admin', 'user')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            purpose TEXT DEFAULT '',
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'cancelled', 'completed')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (equipment_id) REFERENCES equipment(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        -- 创建索引加速查询（不依赖 email 列的索引放在迁移之后）
        CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date);
        CREATE INDEX IF NOT EXISTS idx_bookings_equipment ON bookings(equipment_id);
        CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
    ''')

    # 如果旧表没有某些字段，自动迁移
    try:
        cols = [r[1] for r in conn.execute('PRAGMA table_info(users)').fetchall()]
        if 'email' not in cols:
            conn.execute('ALTER TABLE users ADD COLUMN email TEXT')
        if 'password_hash' not in cols:
            conn.execute('ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ""')
        if 'real_name' not in cols:
            conn.execute('ALTER TABLE users ADD COLUMN real_name TEXT DEFAULT ""')
    except Exception:
        pass

    # 迁移完成后再创建依赖新列的索引
    try:
        conn.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
    except Exception:
        pass

    conn.commit()

    # 插入默认设备（如果表为空）
    count = conn.execute('SELECT COUNT(*) FROM equipment').fetchone()[0]
    if count == 0:
        conn.executemany(
            'INSERT INTO equipment (name, location, description) VALUES (?, ?, ?)',
            [
                ('超净台 1号', '实验室 A101', '左侧标准超净台'),
                ('超净台 2号', '实验室 A101', '右侧标准超净台'),
                ('超净台 3号', '实验室 A102', '生物安全柜'),
            ]
        )

    # 插入默认管理员（如果表为空）
    count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if count == 0:
        pw_hash = hash_password('admin123')
        conn.execute(
            'INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)',
            ('管理员', 'admin@lab.local', pw_hash, 'admin')
        )

    conn.commit()
    conn.close()


# ==================== 密码工具 ====================

def hash_password(password):
    """SHA-256 哈希密码"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


# ==================== 邮件配置 ====================

def load_email_config():
    """加载邮件配置"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_email_config(config):
    """保存邮件配置"""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def send_email(to_email, subject, html_body):
    """发送邮件"""
    config = load_email_config()
    if not config:
        print(f"[邮件] 未配置邮箱，跳过发送到 {to_email}")
        return False, '邮件未配置'

    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = formataddr((config.get('sender_name', '超净台预约系统'), config['smtp_user']))
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        smtp_host = config['smtp_host']
        smtp_port = config.get('smtp_port', 465)
        smtp_user = config['smtp_user']
        print(f'[邮件] 正在连接 {smtp_host}:{smtp_port} (SSL={config.get("use_ssl", True)})')
        print(f'[邮件] 登录账号: {smtp_user}')

        if config.get('use_ssl', True):
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(config['smtp_host'], config.get('smtp_port', 587), timeout=10)
            server.starttls()

        server.login(config['smtp_user'], config['smtp_pass'])
        server.sendmail(config['smtp_user'], to_email, msg.as_string())
        server.quit()
        print(f"[邮件] 已发送到 {to_email}: {subject}")
        return True, None
    except Exception as e:
        import traceback
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[邮件] 发送失败: {err_msg}")
        traceback.print_exc()
        return False, err_msg


def make_email_html(title, title_color, greeting, description, rows, footer=''):
    """通用邮件模板"""
    rows_html = ''.join(
        f'<tr><td style="padding:10px;background:#f0f2f5;font-weight:600;border-radius:8px 0 0 0;">{r[0]}</td>'
        f'<td style="padding:10px;background:#f0f2f5;border-radius:0 8px 0 0;">{r[1]}</td></tr>'
        if i == 0 else
        f'<tr><td style="padding:10px;background:#f8fafc;font-weight:600;">{r[0]}</td>'
        f'<td style="padding:10px;background:#f8fafc;">{r[1]}</td></tr>'
        for i, r in enumerate(rows)
    )
    return f"""
    <div style="max-width:500px;margin:0 auto;font-family:-apple-system,'Microsoft YaHei',sans-serif;">
        <div style="background:linear-gradient(135deg,{title_color});padding:24px;border-radius:12px 12px 0 0;">
            <h2 style="color:white;margin:0;">{title}</h2>
        </div>
        <div style="background:white;padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;">
            <p style="font-size:16px;">{greeting}</p>
            <p style="color:#6b7280;">{description}</p>
            <table style="width:100%;margin:16px 0;border-collapse:collapse;">{rows_html}</table>
            {footer}
            <p style="color:#9ca3af;font-size:13px;">此邮件由超净台预约系统自动发送，请勿回复。</p>
        </div>
    </div>
    """


def send_booking_created(user_name, user_email, equipment_name, date, start_time, end_time, purpose):
    """预约创建成功通知"""
    if not user_email:
        return
    rows = [
        ('📅 日期', date),
        ('⏰ 时间', f'{start_time} - {end_time}'),
        ('🔬 设备', equipment_name),
    ]
    if purpose:
        rows.append(('📝 用途', purpose))
    html = make_email_html(
        '✅ 预约创建成功', '#22c55e,#16a34a',
        f'你好，<strong>{user_name}</strong>：',
        '你的超净台预约已成功创建：', rows
    )
    send_email(user_email, f'预约成功：{date} {start_time}-{end_time} {equipment_name}', html)


def send_booking_cancelled(user_name, user_email, equipment_name, date, start_time, end_time):
    """预约取消通知"""
    if not user_email:
        return
    html = make_email_html(
        '❌ 预约已取消', '#ef4444,#dc2626',
        f'你好，<strong>{user_name}</strong>：',
        '你的以下预约已被取消：',
        [
            ('📅 日期', date),
            ('⏰ 时间', f'{start_time} - {end_time}'),
            ('🔬 设备', equipment_name),
        ]
    )
    send_email(user_email, f'预约已取消：{date} {start_time}-{end_time} {equipment_name}', html)


def send_booking_reminder(user_name, user_email, equipment_name, date, start_time, end_time, purpose):
    """发送预约提醒邮件（开始前15分钟）"""
    if not user_email:
        return
    rows = [
        ('📅 日期', date),
        ('⏰ 时间', f'{start_time} - {end_time}'),
        ('🔬 设备', equipment_name),
    ]
    if purpose:
        rows.append(('📝 用途', purpose))
    html = make_email_html(
        '🔬 超净台预约提醒', '#4f6ef7,#3a54d4',
        f'你好，<strong>{user_name}</strong>：',
        '你有一个超净台预约即将开始，请提前做好准备：', rows
    )
    send_email(user_email, f'预约提醒：{date} {start_time}-{end_time} {equipment_name}', html)


# ==================== 定时邮件检查 ====================

def reminder_loop():
    """后台线程：每分钟检查并发送即将开始的预约提醒"""
    while True:
        try:
            check_and_send_reminders()
        except Exception as e:
            print(f"[提醒] 检查出错: {e}")
        threading.Event().wait(60)  # 每60秒检查一次


def check_and_send_reminders():
    """检查未来15分钟内开始且未发送过提醒的预约"""
    config = load_email_config()
    if not config:
        return  # 未配置邮件，跳过

    conn = get_db()
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M')

    # 找到今天开始时间在当前时间之后15分钟内的活跃预约
    # 用 reminder_sent 字段避免重复发送（如果没有该字段则忽略）
    try:
        conn.execute("SELECT reminder_sent FROM bookings LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE bookings ADD COLUMN reminder_sent INTEGER DEFAULT 0")
        conn.commit()

    bookings = conn.execute('''
        SELECT b.id, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, u.email, e.name as equipment_name,
               b.date, b.start_time, b.end_time, b.purpose, b.reminder_sent
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN equipment e ON b.equipment_id = e.id
        WHERE b.date = ?
          AND b.status = 'active'
          AND b.reminder_sent = 0
          AND b.start_time >= ?
          AND b.start_time <= ?
    ''', (today, current_time, (now + timedelta(minutes=15)).strftime('%H:%M'))).fetchall()

    for b in bookings:
        send_booking_reminder(
            b['user_name'], b['email'], b['equipment_name'],
            b['date'], b['start_time'], b['end_time'], b['purpose']
        )
        conn.execute('UPDATE bookings SET reminder_sent = 1 WHERE id = ?', (b['id'],))

    conn.commit()
    conn.close()


# ==================== 认证 API ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.json
    name = data.get('name', '').strip()
    real_name = data.get('real_name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    group_name = data.get('group_name', '').strip()
    phone = data.get('phone', '').strip()

    # 验证
    if not name or len(name) < 1:
        return jsonify({'error': '请输入昵称'}), 400
    if not email or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'error': '请输入有效的邮箱地址'}), 400
    if not password or len(password) < 4:
        return jsonify({'error': '密码至少4位'}), 400

    conn = get_db()
    # 检查邮箱是否已注册
    existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': '该邮箱已被注册'}), 400

    pw_hash = hash_password(password)
    # 第一个注册的用户自动成为管理员
    count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    role = 'admin' if count == 0 else 'user'
    cursor = conn.execute(
        'INSERT INTO users (name, real_name, email, password_hash, group_name, phone, role) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (name, real_name, email, pw_hash, group_name, phone, role)
    )
    conn.commit()
    user_id = cursor.lastrowid

    user = conn.execute('SELECT id, name, real_name, email, group_name, phone, role FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()

    return jsonify({
        'message': '注册成功',
        'user': dict(user),
        'token': secrets.token_hex(32)
    }), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.json
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': '请输入邮箱和密码'}), 400

    conn = get_db()
    user = conn.execute(
        'SELECT id, name, real_name, email, password_hash, group_name, phone, role FROM users WHERE email = ?',
        (email,)
    ).fetchone()
    conn.close()

    if not user or user['password_hash'] != hash_password(password):
        return jsonify({'error': '邮箱或密码错误'}), 401

    token = secrets.token_hex(32)
    user_dict = dict(user)
    del user_dict['password_hash']

    return jsonify({
        'message': '登录成功',
        'user': user_dict,
        'token': token
    })


@app.route('/api/auth/profile', methods=['PUT'])
def update_profile():
    """更新个人信息"""
    data = request.json
    uid = data.get('id')
    if not uid:
        return jsonify({'error': '缺少用户ID'}), 400

    conn = get_db()
    # 允许更新的字段
    fields = []
    params = []
    for field in ['name', 'real_name', 'group_name', 'phone']:
        if field in data and data[field] is not None:
            fields.append(f'{field} = ?')
            params.append(data[field].strip())

    if not fields:
        conn.close()
        return jsonify({'error': '没有要更新的内容'}), 400

    params.append(uid)
    conn.execute(f'UPDATE users SET {", ".join(fields)} WHERE id = ?', params)
    conn.commit()

    user = conn.execute('SELECT id, name, real_name, email, group_name, phone, role FROM users WHERE id = ?', (uid,)).fetchone()
    conn.close()

    return jsonify({'message': '信息更新成功', 'user': dict(user)})


@app.route('/api/auth/password', methods=['PUT'])
def change_password():
    """修改密码"""
    data = request.json
    uid = data.get('id')
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not uid or not old_password or not new_password:
        return jsonify({'error': '请填写完整信息'}), 400
    if len(new_password) < 4:
        return jsonify({'error': '新密码至少4位'}), 400

    conn = get_db()
    user = conn.execute('SELECT password_hash FROM users WHERE id = ?', (uid,)).fetchone()
    if not user or user['password_hash'] != hash_password(old_password):
        conn.close()
        return jsonify({'error': '原密码错误'}), 401

    conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (hash_password(new_password), uid))
    conn.commit()
    conn.close()

    return jsonify({'message': '密码修改成功'})


# ==================== 邮件配置 API ====================

@app.route('/api/email-config', methods=['GET'])
def get_email_config_api():
    """获取邮件配置（隐藏密码）"""
    config = load_email_config()
    if config:
        safe = {k: v for k, v in config.items() if k != 'smtp_pass'}
        safe['configured'] = True
        return jsonify(safe)
    return jsonify({'configured': False})


@app.route('/api/email-config', methods=['POST'])
def save_email_config_api():
    """保存邮件配置"""
    data = request.json
    config = {
        'smtp_host': data.get('smtp_host', '').strip(),
        'smtp_port': int(data.get('smtp_port', 465)),
        'smtp_user': data.get('smtp_user', '').strip(),
        'smtp_pass': data.get('smtp_pass', ''),
        'use_ssl': data.get('use_ssl', True),
        'sender_name': data.get('sender_name', '超净台预约系统'),
    }

    if not config['smtp_host'] or not config['smtp_user']:
        return jsonify({'error': '请填写SMTP服务器和发件邮箱'}), 400

    save_email_config(config)
    return jsonify({'message': '邮件配置保存成功'})


@app.route('/api/email-test', methods=['POST'])
def test_email():
    """测试邮件发送"""
    data = request.json
    to = data.get('to_email', '').strip()
    if not to:
        return jsonify({'error': '请输入收件邮箱'}), 400

    success, err_msg = send_email(to, '预约系统邮件测试', '<h3>测试邮件</h3><p>如果你收到这封邮件，说明邮件配置正确！</p>')
    if success:
        return jsonify({'message': '测试邮件已发送，请检查收件箱'})
    return jsonify({'error': f'邮件发送失败：{err_msg}'}), 500


# ==================== 设备 API ====================

@app.route('/api/equipment', methods=['GET'])
def get_equipment():
    """获取所有设备列表"""
    conn = get_db()
    rows = conn.execute('SELECT * FROM equipment ORDER BY id').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/equipment', methods=['POST'])
def add_equipment():
    """添加新设备"""
    data = request.json
    conn = get_db()
    cursor = conn.execute(
        'INSERT INTO equipment (name, location, description) VALUES (?, ?, ?)',
        (data['name'], data.get('location', ''), data.get('description', ''))
    )
    conn.commit()
    equip_id = cursor.lastrowid
    conn.close()
    return jsonify({'id': equip_id, 'message': '设备添加成功'}), 201


@app.route('/api/equipment/<int:eid>', methods=['PUT'])
def update_equipment(eid):
    """更新设备信息"""
    data = request.json
    conn = get_db()
    conn.execute(
        'UPDATE equipment SET name=?, location=?, status=?, description=? WHERE id=?',
        (data['name'], data.get('location', ''), data.get('status', 'available'),
         data.get('description', ''), eid)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': '设备更新成功'})


@app.route('/api/equipment/<int:eid>', methods=['DELETE'])
def delete_equipment(eid):
    """删除设备"""
    conn = get_db()
    bookings = conn.execute(
        'SELECT COUNT(*) FROM bookings WHERE equipment_id=? AND status="active"',
        (eid,)
    ).fetchone()[0]
    if bookings > 0:
        conn.close()
        return jsonify({'error': '该设备有活跃预约，无法删除'}), 400
    conn.execute('DELETE FROM equipment WHERE id=?', (eid,))
    conn.commit()
    conn.close()
    return jsonify({'message': '设备删除成功'})


# ==================== 用户 API ====================

@app.route('/api/users', methods=['GET'])
def get_users():
    """获取所有用户（不返回密码）"""
    conn = get_db()
    rows = conn.execute('SELECT id, name, real_name, email, group_name, phone, role, created_at FROM users ORDER BY id').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/users/<int:uid>', methods=['PUT'])
def update_user(uid):
    """更新用户信息（管理员）"""
    data = request.json
    conn = get_db()
    conn.execute(
        'UPDATE users SET name=?, real_name=?, group_name=?, phone=?, role=? WHERE id=?',
        (data['name'], data.get('real_name', ''), data.get('group_name', ''), data.get('phone', ''),
         data.get('role', 'user'), uid)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': '用户更新成功'})


@app.route('/api/users/<int:uid>', methods=['DELETE'])
def delete_user(uid):
    """删除用户"""
    conn = get_db()
    bookings = conn.execute(
        'SELECT COUNT(*) FROM bookings WHERE user_id=? AND status="active"',
        (uid,)
    ).fetchone()[0]
    if bookings > 0:
        conn.close()
        return jsonify({'error': '该用户有活跃预约，无法删除'}), 400
    conn.execute('DELETE FROM users WHERE id=? AND role != "admin"', (uid,))
    conn.commit()
    conn.close()
    return jsonify({'message': '用户删除成功'})


# ==================== 预约 API ====================

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    """获取预约列表，支持过滤"""
    equipment_id = request.args.get('equipment_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    user_id = request.args.get('user_id')
    status = request.args.get('status', 'active')

    conn = get_db()
    query = '''
        SELECT b.*, e.name as equipment_name, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, u.group_name, u.email
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        JOIN users u ON b.user_id = u.id
        WHERE 1=1
    '''
    params = []

    if equipment_id:
        query += ' AND b.equipment_id = ?'
        params.append(int(equipment_id))
    if date_from:
        query += ' AND b.date >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND b.date <= ?'
        params.append(date_to)
    if user_id:
        query += ' AND b.user_id = ?'
        params.append(int(user_id))
    if status:
        query += ' AND b.status = ?'
        params.append(status)

    query += ' ORDER BY b.date, b.start_time, b.equipment_id'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/bookings/week', methods=['GET'])
def get_week_bookings():
    """获取某周的预约数据（用于周视图渲染）"""
    date_str = request.args.get('date')  # YYYY-MM-DD，可以是周内任意一天
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)

    conn = get_db()
    query = '''
        SELECT b.*, e.name as equipment_name, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, u.group_name
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        JOIN users u ON b.user_id = u.id
        WHERE b.date >= ? AND b.date <= ? AND b.status = 'active'
        ORDER BY b.date, b.start_time, b.equipment_id
    '''
    rows = conn.execute(query, (monday.strftime('%Y-%m-%d'), sunday.strftime('%Y-%m-%d'))).fetchall()
    conn.close()

    return jsonify({
        'week_start': monday.strftime('%Y-%m-%d'),
        'week_end': sunday.strftime('%Y-%m-%d'),
        'bookings': [dict(r) for r in rows]
    })


@app.route('/api/bookings', methods=['POST'])
def create_booking():
    """创建预约"""
    data = request.json
    conn = get_db()

    # 冲突检测
    conflict = conn.execute('''
        SELECT b.id, e.name as equip_name, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, b.start_time, b.end_time
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        JOIN users u ON b.user_id = u.id
        WHERE b.equipment_id = ?
          AND b.date = ?
          AND b.status = 'active'
          AND b.start_time < ?
          AND b.end_time > ?
    ''', (data['equipment_id'], data['date'], data['end_time'], data['start_time'])).fetchone()

    if conflict:
        conn.close()
        return jsonify({
            'error': '时间冲突',
            'detail': f"{conflict['equip_name']} 在 {conflict['start_time']}-{conflict['end_time']} 已被 {conflict['user_name']} 预约"
        }), 409

    # 同一用户同一时间段不能预约多台设备
    same_user_conflict = conn.execute('''
        SELECT b.id, e.name as equip_name
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        WHERE b.user_id = ?
          AND b.date = ?
          AND b.status = 'active'
          AND b.start_time < ?
          AND b.end_time > ?
    ''', (data['user_id'], data['date'], data['end_time'], data['start_time'])).fetchone()

    if same_user_conflict:
        conn.close()
        return jsonify({
            'error': '时间冲突',
            'detail': f"你在 {data['start_time']}-{data['end_time']} 已经预约了 {same_user_conflict['equip_name']}"
        }), 409

    cursor = conn.execute('''
        INSERT INTO bookings (equipment_id, user_id, date, start_time, end_time, purpose)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        data['equipment_id'], data['user_id'], data['date'],
        data['start_time'], data['end_time'], data.get('purpose', '')
    ))
    conn.commit()
    booking_id = cursor.lastrowid

    # 发送预约成功邮件通知
    user = conn.execute('SELECT name, email FROM users WHERE id = ?', (data['user_id'],)).fetchone()
    equip = conn.execute('SELECT name FROM equipment WHERE id = ?', (data['equipment_id'],)).fetchone()
    if user and equip:
        send_booking_created(
            user['name'], user['email'], equip['name'],
            data['date'], data['start_time'], data['end_time'], data.get('purpose', '')
        )

    conn.close()

    return jsonify({'id': booking_id, 'message': '预约成功'}), 201


@app.route('/api/bookings/<int:bid>', methods=['PUT'])
def update_booking(bid):
    """更新预约"""
    data = request.json
    conn = get_db()

    # 冲突检测（排除自身）
    conflict = conn.execute('''
        SELECT b.id, e.name as equip_name, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, b.start_time, b.end_time
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        JOIN users u ON b.user_id = u.id
        WHERE b.equipment_id = ?
          AND b.date = ?
          AND b.status = 'active'
          AND b.start_time < ?
          AND b.end_time > ?
          AND b.id != ?
    ''', (data.get('equipment_id'), data.get('date'),
          data['end_time'], data['start_time'], bid)).fetchone()

    if conflict:
        conn.close()
        return jsonify({
            'error': '时间冲突',
            'detail': f"{conflict['equip_name']} 在 {conflict['start_time']}-{conflict['end_time']} 已被 {conflict['user_name']} 预约"
        }), 409

    conn.execute('''
        UPDATE bookings SET
            equipment_id=?, date=?, start_time=?, end_time=?,
            purpose=?, status=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    ''', (
        data.get('equipment_id'), data.get('date'),
        data['start_time'], data['end_time'],
        data.get('purpose', ''), data.get('status', 'active'), bid
    ))
    conn.commit()
    conn.close()
    return jsonify({'message': '预约更新成功'})


@app.route('/api/bookings/<int:bid>', methods=['DELETE'])
def cancel_booking(bid):
    """取消预约"""
    conn = get_db()

    # 先获取预约信息用于发送邮件
    booking = conn.execute('''
        SELECT b.date, b.start_time, b.end_time, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, u.email, e.name as equip_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN equipment e ON b.equipment_id = e.id
        WHERE b.id = ? AND b.status = 'active'
    ''', (bid,)).fetchone()

    conn.execute(
        "UPDATE bookings SET status='cancelled', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (bid,)
    )
    conn.commit()

    # 发送取消通知邮件
    if booking and booking['email']:
        send_booking_cancelled(
            booking['user_name'], booking['email'], booking['equip_name'],
            booking['date'], booking['start_time'], booking['end_time']
        )

    conn.close()
    return jsonify({'message': '预约已取消'})


# ==================== 统计 API ====================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取预约统计数据"""
    conn = get_db()

    total_bookings = conn.execute(
        'SELECT COUNT(*) FROM bookings WHERE status="active"'
    ).fetchone()[0]

    today = datetime.now().strftime('%Y-%m-%d')
    today_bookings = conn.execute(
        'SELECT COUNT(*) FROM bookings WHERE date=? AND status="active"',
        (today,)
    ).fetchone()[0]

    total_equipment = conn.execute('SELECT COUNT(*) FROM equipment').fetchone()[0]
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]

    # 近7天每天预约数
    week_stats = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        count = conn.execute(
            'SELECT COUNT(*) FROM bookings WHERE date=? AND status="active"',
            (d,)
        ).fetchone()[0]
        week_stats.append({'date': d, 'count': count})

    # 各设备使用率（近7天）
    equipment_usage = conn.execute('''
        SELECT e.id, e.name, COUNT(b.id) as booking_count
        FROM equipment e
        LEFT JOIN bookings b ON e.id = b.equipment_id
            AND b.date >= ? AND b.date <= ? AND b.status = 'active'
        GROUP BY e.id
        ORDER BY booking_count DESC
    ''', (
        (datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d'),
        today
    )).fetchall()

    conn.close()

    return jsonify({
        'total_bookings': total_bookings,
        'today_bookings': today_bookings,
        'total_equipment': total_equipment,
        'total_users': total_users,
        'week_stats': week_stats,
        'equipment_usage': [dict(r) for r in equipment_usage]
    })


# ==================== 前端路由 ====================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


# ==================== 启动 ====================

if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("  实验室超净台预约系统")
    print("=" * 50)

    # 启动邮件提醒后台线程
    t = threading.Thread(target=reminder_loop, daemon=True)
    t.start()

    # Zeabur 部署支持：使用环境变量 PORT，host=0.0.0.0，生产环境关闭 debug
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    print(f"  访问地址: http://0.0.0.0:{port}")
    print(f"  默认管理员: admin@lab.local / admin123")
    print(f"  Debug 模式: {'开启' if debug else '关闭'}")
    app.run(host='0.0.0.0', port=port, debug=debug)
