# -*- coding: utf-8 -*-
"""
性能监控中间件
"""

import time
import os
from functools import wraps
from flask import request, g

def performance_monitor(f):
    """性能监控装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if os.getenv('VERCEL') == '1':
            start_time = time.time()
            result = f(*args, **kwargs)
            end_time = time.time()
            
            # 记录慢请求（超过1秒）
            if end_time - start_time > 1.0:
                print(f"慢请求警告: {request.path} 耗时 {end_time - start_time:.2f}秒")
            
            return result
        else:
            return f(*args, **kwargs)
    return decorated_function

def add_performance_headers(response):
    """添加性能相关的响应头"""
    if os.getenv('VERCEL') == '1':
        response.headers['X-Vercel-Cache'] = 'HIT'
        response.headers['Cache-Control'] = 'public, max-age=300'
    return response
