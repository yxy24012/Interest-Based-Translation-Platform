# Gunicorn配置文件
import os

# 绑定地址和端口
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# 工作进程数
workers = 2

# 工作进程类型
worker_class = "sync"

# 超时设置
timeout = 120
keepalive = 2

# 日志设置
accesslog = "-"
errorlog = "-"
loglevel = "info"

# 预加载应用
preload_app = True

# 最大请求数
max_requests = 1000
max_requests_jitter = 50

# 重启工作进程
graceful_timeout = 30
