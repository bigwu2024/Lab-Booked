"""Gunicorn 配置文件 - Zeabur 生产部署"""
import os

# 绑定端口（Zeabur 通过 PORT 环境变量指定）
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Worker 配置
workers = 2
threads = 4
timeout = 120

# 入口
wsgi_app = "app:app"
