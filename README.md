# 实验室超净台预约系统

一个轻量级的实验室设备（超净台）在线预约系统，使用 Python Flask + SQLite 构建，无需复杂部署。

## ✨ 功能特性

- **📅 周视图日历** — 一眼看到整周所有预约，按设备颜色区分
- **⚡ 实时冲突检测** — 同一设备/同一用户时间冲突自动拦截
- **📋 预约管理** — 创建、编辑、取消预约，支持筛选过滤
- **🔬 设备管理** — 添加/编辑设备，设置状态（可用/维护中/停用）
- **👥 用户管理** — 添加实验室成员，按课题组分类
- **📊 数据统计** — 活跃预约数、今日预约、近7天趋势图
- **📧 邮件通知** — 预约创建/取消通知，开始前15分钟提醒

## 🚀 快速启动

### 方式一：双击启动（推荐）
双击 `启动系统.bat`，然后浏览器打开 `http://localhost:5000`

### 方式二：命令行启动
```bash
pip install -r requirements.txt
python app.py
```

浏览器访问：**http://localhost:5000**

## 📁 项目结构

```
08.预约系统/
├── app.py              # 后端服务 (Flask + SQLite)
├── booking.db          # 数据库文件（自动创建，已 .gitignore）
├── requirements.txt    # Python 依赖
├── gunicorn.conf.py    # Gunicorn 生产部署配置
├── Procfile            # Zeabur/Heroku 部署入口
├── 启动系统.bat         # 一键启动脚本
└── static/
    └── index.html      # 前端页面（单页应用）
```

## ☁️ Zeabur 部署

### 自动部署（推荐）
1. 将代码推送到 GitHub 仓库
2. 在 [Zeabur](https://zeabur.com) 控制台导入 GitHub 仓库
3. Zeabur 自动检测 Python 项目并部署
4. 默认管理员：`admin@lab.local` / `admin123`

### 数据持久化
- **⚠️ SQLite 数据不持久**：Zeabur 容器重启会丢失数据
- 推荐方案：在 Zeabur 添加 PostgreSQL 服务，或定期备份数据库
- 当前实现使用 SQLite（适合小规模使用）

### 环境变量
| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PORT` | 服务端口（Zeabur 自动设置） | `5000` |
| `FLASK_DEBUG` | 调试模式 | `0` |

## 🔧 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/equipment | 获取设备列表 |
| POST | /api/equipment | 添加设备 |
| PUT | /api/equipment/:id | 更新设备 |
| DELETE | /api/equipment/:id | 删除设备 |
| GET | /api/users | 获取用户列表 |
| PUT | /api/users/:id | 更新用户 |
| DELETE | /api/users/:id | 删除用户 |
| GET | /api/bookings | 获取预约列表（支持过滤） |
| GET | /api/bookings/week?date=YYYY-MM-DD | 获取周视图数据 |
| POST | /api/bookings | 创建预约 |
| PUT | /api/bookings/:id | 更新预约 |
| DELETE | /api/bookings/:id | 取消预约 |
| GET | /api/stats | 获取统计数据 |
| POST | /api/auth/register | 用户注册 |
| POST | /api/auth/login | 用户登录 |
| PUT | /api/auth/profile | 更新个人信息 |
| PUT | /api/auth/password | 修改密码 |
| GET | /api/email-config | 获取邮件配置 |
| POST | /api/email-config | 保存邮件配置 |
| POST | /api/email-test | 测试邮件发送 |

## 📝 使用流程

1. 启动系统 → 打开浏览器访问
2. 先到「用户管理」添加实验室成员
3. 到「预约日历」点击「新建预约」
4. 选择预约人、设备、日期和时间 → 确认预约
5. 所有成员打开同一地址即可查看和预约
