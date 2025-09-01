# -*- coding: utf-8 -*-
"""
Vercel性能优化配置
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

# Vercel环境检测
IS_VERCEL = os.getenv('VERCEL') == '1'

# 数据库连接池配置（针对Vercel优化）
VERCEL_DB_CONFIG = {
    'pool_size': 5,  # 连接池大小
    'max_overflow': 10,  # 最大溢出连接数
    'pool_timeout': 20,  # 连接超时时间
    'pool_recycle': 3600,  # 连接回收时间（1小时）
    'pool_pre_ping': True,  # 连接前ping测试
    'echo': False  # 关闭SQL日志
}

# 缓存配置
CACHE_CONFIG = {
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300,  # 5分钟
    'CACHE_KEY_PREFIX': 'vercel_'
}

# 静态文件缓存配置
STATIC_CACHE_CONFIG = {
    'static_folder': 'static',
    'static_url_path': '/static',
    'send_file_max_age_default': 31536000  # 1年缓存
}

def get_optimized_db_url():
    """获取优化的数据库URL"""
    db_url = os.getenv('DATABASE_URL', 'sqlite:///forum.db')
    
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql+psycopg2://', 1)
    
    if 'postgresql+psycopg2://' in db_url and 'sslmode=' not in db_url:
        sep = '&' if '?' in db_url else '?'
        db_url = f'{db_url}{sep}sslmode=require'
    
    return db_url

def create_optimized_engine():
    """创建优化的数据库引擎"""
    if not IS_VERCEL:
        return None
    
    db_url = get_optimized_db_url()
    if 'sqlite' in db_url:
        return None
    
    return create_engine(
        db_url,
        **VERCEL_DB_CONFIG
    )
