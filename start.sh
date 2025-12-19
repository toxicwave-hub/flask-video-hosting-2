#!/bin/bash
# 启动 Gunicorn WSGI 服务器
# -w 4: 启动 4 个工作进程
# -b 0.0.0.0:$PORT: 绑定到所有接口和 Render 提供的 $PORT 环境变量
# app:app: 模块名:应用实例名
gunicorn --workers 4 --bind 0.0.0.0:$PORT app:app
