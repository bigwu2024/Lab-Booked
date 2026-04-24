# -*- coding: utf-8 -*-
"""
实验室超净台预约系统 - 后端服务
Flask + MySQL，提供 RESTful API
支持用户注册/登录、邮件提醒
Deploy: mysql+pymysql
"""

import os
import re
import json
import hashlib
import secrets
import threading
import smtplib
import pymysql
from pymysql.cursors import DictCursor
from email.mime.text import MIMEText
from email.utils import formataddr
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)


# 覆盖 Zeabur 默认的严格 CSP 策略，允许前端 JS 正常运行
@app.after_request
def set_csp(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self'; "
        "connect-src 'self'"
    )
    return response


DATABASE_URL = os.environ.get('DATABASE_URL', '')

# Zeabur 数据库环境变量（支持 MySQL / MariaDB）
MYSQL_HOST = os.environ.get('MYSQL_HOST', '') or os.environ.get('MARIADB_HOST', '')
MYSQL_PORT = os.environ.get('MYSQL_PORT', '') or os.environ.get('MARIADB_PORT', '3306')
MYSQL_USERNAME = os.environ.get('MYSQL_USERNAME', '') or os.environ.get('MARIADB_USERNAME', '')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '') or os.environ.get('MARIADB_PASSWORD', '')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', '') or os.environ.get('MARIADB_DATABASE', '')


# ==================== 数据库工具 ====================

def get_db_config():
    """获取数据库连接配置，优先用 Zeabur 注入变量，其次解析 DATABASE_URL"""
    if MYSQL_HOST and MYSQL_USERNAME:
        return {
            'host': MYSQL_HOST,
            'port': int(MYSQL_PORT) if MYSQL_PORT else 3306,
            'user': MYSQL_USERNAME,
            'password': MYSQL_PASSWORD,
            'database': MYSQL_DATABASE or 'zeabur',
            'charset': 'utf8mb4',
        }
    if DATABASE_URL:
        import re as _re
        m = _re.match(r'(?:mysql|postgresql|mariadb)://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)', DATABASE_URL)
        if m:
            return {
                'host': m.group(3),
                'port': int(m.group(4) or 3306),
                'user': m.group(1),
                'password': m.group(2),
                'database': m.group(5),
                'charset': 'utf8mb4',
            }
    raise ValueError('未配置数据库连接信息（需要 DATABASE_URL 或 MYSQL_*/MARIADB_* 环境变量）')


def get_db():
    """获取数据库连接"""
    params = get_db_config()
    conn = pymysql.connect(**params, cursorclass=DictCursor)
    conn.autocommit(False)
    return conn


def query_db(conn, sql, params=(), one=False):
    """执行查询并返回字典列表"""
    with conn.cursor(DictCursor) as cur:
        cur.execute(sql, params)
        if one:
            row = cur.fetchone()
            return dict(row) if row else None
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def execute_db(conn, sql, params=()):
    """执行写操作，返回 cursor"""
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def init_db():
    """初始化数据库表"""
    conn = get_db()

    with conn.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS equipment (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                location VARCHAR(255) DEFAULT '',
                status VARCHAR(50) DEFAULT 'available',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                real_name VARCHAR(255) DEFAULT '',
                email VARCHAR(255) UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                group_name VARCHAR(255) DEFAULT '',
                phone VARCHAR(50) DEFAULT '',
                role VARCHAR(50) DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                equipment_id INT NOT NULL,
                user_id INT NOT NULL,
                date VARCHAR(20) NOT NULL,
                start_time VARCHAR(10) NOT NULL,
                end_time VARCHAR(10) NOT NULL,
                purpose TEXT,
                status VARCHAR(50) DEFAULT 'active',
                reminder_sent TINYINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (equipment_id) REFERENCES equipment(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS email_config (
                id INT AUTO_INCREMENT PRIMARY KEY,
                smtp_host VARCHAR(255) NOT NULL,
                smtp_port INT DEFAULT 465,
                smtp_user VARCHAR(255) NOT NULL,
                smtp_pass TEXT,
                use_ssl TINYINT DEFAULT 1,
                sender_name VARCHAR(255) DEFAULT '超净台预约系统',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        ''')

    conn.commit()

    # 插入默认设备（如果表为空）
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) as cnt FROM equipment')
        if cur.fetchone()['cnt'] == 0:
            for name, loc, desc in [
                ('超净台 1号', '实验室 A101', '左侧标准超净台'),
                ('超净台 2号', '实验室 A101', '右侧标准超净台'),
                ('超净台 3号', '实验室 A102', '生物安全柜'),
            ]:
                cur.execute(
                    'INSERT INTO equipment (name, location, description) VALUES (%s, %s, %s)',
                    (name, loc, desc)
                )
            conn.commit()

    # 插入默认管理员（如果表为空）
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) as cnt FROM users')
        if cur.fetchone()['cnt'] == 0:
            pw_hash = hash_password('admin123')
            cur.execute(
                'INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)',
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
    """从数据库加载邮件配置"""
    try:
        conn = get_db()
        rows = query_db(conn, 'SELECT * FROM email_config ORDER BY id DESC LIMIT 1')
        conn.close()
        if rows:
            return rows[0]
    except Exception:
        pass
    return None


def save_email_config(config):
    """保存邮件配置到数据库"""
    conn = get_db()
    # 清除旧配置，只保留一条
    execute_db(conn, 'DELETE FROM email_config')
    execute_db(conn, '''
        INSERT INTO email_config (smtp_host, smtp_port, smtp_user, smtp_pass, use_ssl, sender_name)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (
        config['smtp_host'], config.get('smtp_port', 465),
        config['smtp_user'], config.get('smtp_pass', ''),
        1 if config.get('use_ssl', True) else 0, config.get('sender_name', '超净台预约系统')
    ))
    conn.commit()
    conn.close()


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
            <p style="color:#9ca3af;font-size:12px;border-top:1px solid #f0f0f0;padding-top:12px;margin-top:12px;">
                贵州医科大学生物工程学院 · 超净台预约系统<br>
                此邮件由系统自动发送，请勿回复。
            </p>
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
        '🎉 预约成功！', '#22c55e,#16a34a',
        f'<strong>{user_name}</strong>，好消息！',
        '你的超净台已经就位，就等你来了：', rows
    )
    send_email(user_email, f'[预约成功] {date} {start_time}-{end_time} {equipment_name}', html)


def send_booking_cancelled(user_name, user_email, equipment_name, date, start_time, end_time):
    """预约取消通知"""
    if not user_email:
        return
    html = make_email_html(
        '👋 预约已取消', '#ef4444,#dc2626',
        f'<strong>{user_name}</strong>，你的预约已取消',
        '以下时间段已释放，其他人可以预约了：',
        [
            ('📅 日期', date),
            ('⏰ 时间', f'{start_time} - {end_time}'),
            ('🔬 设备', equipment_name),
        ]
    )
    send_email(user_email, f'[已取消] {date} {start_time}-{end_time} {equipment_name}', html)


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
        '⏰ 马上就到啦！', '#4f6ef7,#3a54d4',
        f'<strong>{user_name}</strong>，准备出发！',
        '你的超净台预约 15 分钟后开始，别忘了穿好实验服：', rows
    )
    send_email(user_email, f'[即将开始] {date} {start_time} {equipment_name}', html)


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

    bookings = query_db(conn, '''
        SELECT b.id, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, u.email, e.name as equipment_name,
               b.date, b.start_time, b.end_time, b.purpose, b.reminder_sent
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN equipment e ON b.equipment_id = e.id
        WHERE b.date = %s
          AND b.status = 'active'
          AND b.reminder_sent = 0
          AND b.start_time >= %s
          AND b.start_time <= %s
    ''', (today, current_time, (now + timedelta(minutes=15)).strftime('%H:%M')))

    for b in bookings:
        send_booking_reminder(
            b['user_name'], b['email'], b['equipment_name'],
            b['date'], b['start_time'], b['end_time'], b['purpose']
        )
        execute_db(conn, 'UPDATE bookings SET reminder_sent = 1 WHERE id = %s', (b['id'],))

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
    existing = query_db(conn, 'SELECT id FROM users WHERE email = %s', (email,), one=True)
    if existing:
        conn.close()
        return jsonify({'error': '该邮箱已被注册'}), 400

    pw_hash = hash_password(password)
    # 第一个注册的用户自动成为管理员
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) as cnt FROM users')
        count = cur.fetchone()['cnt']
    role = 'admin' if count == 0 else 'user'

    with conn.cursor() as cur:
        cur.execute('''
            INSERT INTO users (name, real_name, email, password_hash, group_name, phone, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (name, real_name, email, pw_hash, group_name, phone, role))
        user_id = cur.lastrowid
    conn.commit()

    user = query_db(conn, 'SELECT id, name, real_name, email, group_name, phone, role FROM users WHERE id = %s', (user_id,), one=True)
    conn.close()

    return jsonify({
        'message': '注册成功',
        'user': user,
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
    user = query_db(conn,
        'SELECT id, name, real_name, email, password_hash, group_name, phone, role FROM users WHERE email = %s',
        (email,), one=True)
    conn.close()

    if not user or user['password_hash'] != hash_password(password):
        return jsonify({'error': '邮箱或密码错误'}), 401

    token = secrets.token_hex(32)
    del user['password_hash']

    return jsonify({
        'message': '登录成功',
        'user': user,
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
            fields.append(f'{field} = %s')
            params.append(data[field].strip())

    if not fields:
        conn.close()
        return jsonify({'error': '没有要更新的内容'}), 400

    params.append(uid)
    execute_db(conn, f'UPDATE users SET {", ".join(fields)} WHERE id = %s', params)
    conn.commit()

    user = query_db(conn, 'SELECT id, name, real_name, email, group_name, phone, role FROM users WHERE id = %s', (uid,), one=True)
    conn.close()

    return jsonify({'message': '信息更新成功', 'user': user})


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
    user = query_db(conn, 'SELECT password_hash FROM users WHERE id = %s', (uid,), one=True)
    if not user or user['password_hash'] != hash_password(old_password):
        conn.close()
        return jsonify({'error': '原密码错误'}), 401

    execute_db(conn, 'UPDATE users SET password_hash = %s WHERE id = %s', (hash_password(new_password), uid))
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
    rows = query_db(conn, 'SELECT * FROM equipment ORDER BY id')
    conn.close()
    return jsonify(rows)


@app.route('/api/equipment', methods=['POST'])
def add_equipment():
    """添加新设备"""
    data = request.json
    conn = get_db()
    cur = execute_db(conn,
        'INSERT INTO equipment (name, location, description) VALUES (%s, %s, %s)',
        (data['name'], data.get('location', ''), data.get('description', ''))
    )
    conn.commit()
    equip_id = cur.lastrowid
    cur.close()
    conn.close()
    return jsonify({'id': equip_id, 'message': '设备添加成功'}), 201


@app.route('/api/equipment/<int:eid>', methods=['PUT'])
def update_equipment(eid):
    """更新设备信息"""
    data = request.json
    conn = get_db()
    execute_db(conn,
        'UPDATE equipment SET name=%s, location=%s, status=%s, description=%s WHERE id=%s',
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
    cur = execute_db(conn,
        "SELECT COUNT(*) as cnt FROM bookings WHERE equipment_id=%s AND status='active'",
        (eid,)
    )
    bookings = cur.fetchone()['cnt']
    cur.close()
    if bookings > 0:
        conn.close()
        return jsonify({'error': '该设备有活跃预约，无法删除'}), 400
    execute_db(conn, 'DELETE FROM equipment WHERE id=%s', (eid,))
    conn.commit()
    conn.close()
    return jsonify({'message': '设备删除成功'})


# ==================== 用户 API ====================

@app.route('/api/users', methods=['GET'])
def get_users():
    """获取所有用户（不返回密码）"""
    conn = get_db()
    rows = query_db(conn, 'SELECT id, name, real_name, email, group_name, phone, role, created_at FROM users ORDER BY id')
    conn.close()
    return jsonify(rows)


@app.route('/api/users/<int:uid>', methods=['PUT'])
def update_user(uid):
    """更新用户信息（管理员）"""
    data = request.json
    conn = get_db()
    execute_db(conn,
        'UPDATE users SET name=%s, real_name=%s, group_name=%s, phone=%s, role=%s WHERE id=%s',
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
    cur = execute_db(conn,
        "SELECT COUNT(*) as cnt FROM bookings WHERE user_id=%s AND status='active'",
        (uid,)
    )
    bookings = cur.fetchone()['cnt']
    cur.close()
    if bookings > 0:
        conn.close()
        return jsonify({'error': '该用户有活跃预约，无法删除'}), 400
    execute_db(conn, "DELETE FROM users WHERE id=%s AND role != 'admin'", (uid,))
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
        query += ' AND b.equipment_id = %s'
        params.append(int(equipment_id))
    if date_from:
        query += ' AND b.date >= %s'
        params.append(date_from)
    if date_to:
        query += ' AND b.date <= %s'
        params.append(date_to)
    if user_id:
        query += ' AND b.user_id = %s'
        params.append(int(user_id))
    if status:
        query += " AND b.status = %s"
        params.append(status)

    query += ' ORDER BY b.date, b.start_time, b.equipment_id'
    rows = query_db(conn, query, params)
    conn.close()
    return jsonify(rows)


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
    rows = query_db(conn, '''
        SELECT b.*, e.name as equipment_name, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, u.group_name
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        JOIN users u ON b.user_id = u.id
        WHERE b.date >= %s AND b.date <= %s AND b.status = 'active'
        ORDER BY b.date, b.start_time, b.equipment_id
    ''', (monday.strftime('%Y-%m-%d'), sunday.strftime('%Y-%m-%d')))
    conn.close()

    return jsonify({
        'week_start': monday.strftime('%Y-%m-%d'),
        'week_end': sunday.strftime('%Y-%m-%d'),
        'bookings': rows
    })


@app.route('/api/bookings', methods=['POST'])
def create_booking():
    """创建预约"""
    data = request.json
    conn = get_db()

    # 冲突检测
    conflict = query_db(conn, '''
        SELECT b.id, e.name as equip_name, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, b.start_time, b.end_time
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        JOIN users u ON b.user_id = u.id
        WHERE b.equipment_id = %s
          AND b.date = %s
          AND b.status = 'active'
          AND b.start_time < %s
          AND b.end_time > %s
    ''', (data['equipment_id'], data['date'], data['end_time'], data['start_time']), one=True)

    if conflict:
        conn.close()
        return jsonify({
            'error': '时间冲突',
            'detail': f"{conflict['equip_name']} 在 {conflict['start_time']}-{conflict['end_time']} 已被 {conflict['user_name']} 预约"
        }), 409

    # 同一用户同一时间段不能预约多台设备
    same_user_conflict = query_db(conn, '''
        SELECT b.id, e.name as equip_name
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        WHERE b.user_id = %s
          AND b.date = %s
          AND b.status = 'active'
          AND b.start_time < %s
          AND b.end_time > %s
    ''', (data['user_id'], data['date'], data['end_time'], data['start_time']), one=True)

    if same_user_conflict:
        conn.close()
        return jsonify({
            'error': '时间冲突',
            'detail': f"你在 {data['start_time']}-{data['end_time']} 已经预约了 {same_user_conflict['equip_name']}"
        }), 409

    cur = execute_db(conn, '''
        INSERT INTO bookings (equipment_id, user_id, date, start_time, end_time, purpose)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (
        data['equipment_id'], data['user_id'], data['date'],
        data['start_time'], data['end_time'], data.get('purpose', '')
    ))
    conn.commit()
    booking_id = cur.lastrowid
    cur.close()

    # 发送预约成功邮件通知
    user = query_db(conn, 'SELECT name, email FROM users WHERE id = %s', (data['user_id'],), one=True)
    equip = query_db(conn, 'SELECT name FROM equipment WHERE id = %s', (data['equipment_id'],), one=True)
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
    conflict = query_db(conn, '''
        SELECT b.id, e.name as equip_name, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, b.start_time, b.end_time
        FROM bookings b
        JOIN equipment e ON b.equipment_id = e.id
        JOIN users u ON b.user_id = u.id
        WHERE b.equipment_id = %s
          AND b.date = %s
          AND b.status = 'active'
          AND b.start_time < %s
          AND b.end_time > %s
          AND b.id != %s
    ''', (data.get('equipment_id'), data.get('date'),
          data['end_time'], data['start_time'], bid), one=True)

    if conflict:
        conn.close()
        return jsonify({
            'error': '时间冲突',
            'detail': f"{conflict['equip_name']} 在 {conflict['start_time']}-{conflict['end_time']} 已被 {conflict['user_name']} 预约"
        }), 409

    execute_db(conn, '''
        UPDATE bookings SET
            equipment_id=%s, date=%s, start_time=%s, end_time=%s,
            purpose=%s, status=%s, updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
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
    booking = query_db(conn, '''
        SELECT b.date, b.start_time, b.end_time, COALESCE(NULLIF(u.real_name, ''), u.name) as user_name, u.email, e.name as equip_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN equipment e ON b.equipment_id = e.id
        WHERE b.id = %s AND b.status = 'active'
    ''', (bid,), one=True)

    execute_db(conn,
        "UPDATE bookings SET status='cancelled', updated_at=CURRENT_TIMESTAMP WHERE id=%s",
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

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM bookings WHERE status='active'")
        total_bookings = cur.fetchone()['cnt']

        today = datetime.now().strftime('%Y-%m-%d')
        cur.execute("SELECT COUNT(*) as cnt FROM bookings WHERE date=%s AND status='active'", (today,))
        today_bookings = cur.fetchone()['cnt']

        cur.execute('SELECT COUNT(*) as cnt FROM equipment')
        total_equipment = cur.fetchone()['cnt']

        cur.execute('SELECT COUNT(*) as cnt FROM users')
        total_users = cur.fetchone()['cnt']

    # 近7天每天预约数
    week_stats = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM bookings WHERE date=%s AND status='active'", (d,))
            count = cur.fetchone()['cnt']
        week_stats.append({'date': d, 'count': count})

    # 各设备使用率（近7天）
    equipment_usage = query_db(conn, '''
        SELECT e.id, e.name, COUNT(b.id) as booking_count
        FROM equipment e
        LEFT JOIN bookings b ON e.id = b.equipment_id
            AND b.date >= %s AND b.date <= %s AND b.status = 'active'
        GROUP BY e.id
        ORDER BY booking_count DESC
    ''', (
        (datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d'),
        today
    ))

    conn.close()

    return jsonify({
        'total_bookings': total_bookings,
        'today_bookings': today_bookings,
        'total_equipment': total_equipment,
        'total_users': total_users,
        'week_stats': week_stats,
        'equipment_usage': equipment_usage
    })


# ==================== 前端路由 ====================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


# ==================== 启动 ====================

_db_initialized = False

def _ensure_db():
    """确保数据库已初始化，在首次 API 请求时触发"""
    global _db_initialized
    if _db_initialized:
        return True
    try:
        init_db()
        _db_initialized = True
        print("[启动] 数据库初始化成功")
        return True
    except Exception as e:
        print(f"[启动] 数据库初始化失败: {e}")
        return False

def _delayed_init():
    """启动时尝试初始化数据库，最多重试10次"""
    import time
    for i in range(10):
        try:
            init_db()
            global _db_initialized
            _db_initialized = True
            print(f"[启动] 数据库初始化成功（第{i+1}次尝试）")
            return True
        except Exception as e:
            print(f"[启动] 数据库初始化失败（第{i+1}次）: {e}")
            time.sleep(5)
    return False

# 启动时尝试初始化（如果配置了数据库）
if DATABASE_URL or (MYSQL_HOST and MYSQL_USERNAME):
    _delayed_init()

# 首次请求时自动初始化数据库（兜底）
@app.before_request
def before_request_hook():
    _ensure_db()

# 启动邮件提醒后台线程
t = threading.Thread(target=reminder_loop, daemon=True)
t.start()

if __name__ == '__main__':
    print("=" * 50)
    print("  实验室超净台预约系统")
    print("=" * 50)

    # Zeabur 部署支持：使用环境变量 PORT，host=0.0.0.0，生产环境关闭 debug
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    print(f"  访问地址: http://0.0.0.0:{port}")
    print(f"  默认管理员: admin@lab.local / admin123")
    print(f"  Debug 模式: {'开启' if debug else '关闭'}")
    app.run(host='0.0.0.0', port=port, debug=debug)
