# -*- coding: utf-8 -*-
"""
数据库连接池配置
优化远程数据库连接性能
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

def create_optimized_engine(db_url):
    """创建优化的数据库引擎"""
    
    # 检测数据库类型
    is_postgresql = 'postgresql' in db_url
    
    if is_postgresql:
        # PostgreSQL 连接池配置
        engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=10,  # 连接池大小
            max_overflow=20,  # 最大溢出连接数
            pool_pre_ping=True,  # 连接前ping检查
            pool_recycle=3600,  # 连接回收时间（秒）
            pool_timeout=30,  # 连接超时时间
            echo=False,  # 关闭SQL日志
            # PostgreSQL 特定优化
            connect_args={
                'connect_timeout': 10,  # 连接超时
                'application_name': 'translation_platform',  # 应用名称
                'options': '-c statement_timeout=30000'  # 查询超时30秒
            }
        )
    else:
        # SQLite 配置（本地开发）
        engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False
        )
    
    return engine

def get_database_url():
    """获取数据库URL并进行优化"""
    db_url = os.getenv('DATABASE_URL', 'sqlite:///forum.db')
    
    # 处理PostgreSQL URL格式
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql+psycopg2://', 1)
    
    # 添加SSL配置
    if 'postgresql+psycopg2://' in db_url and 'sslmode=' not in db_url:
        sep = '&' if '?' in db_url else '?'
        db_url = f'{db_url}{sep}sslmode=require'
    
    return db_url

# 数据库连接监控
class DatabaseMonitor:
    def __init__(self):
        self.query_count = 0
        self.slow_queries = []
    
    def log_query(self, query, execution_time):
        """记录查询性能"""
        self.query_count += 1
        if execution_time > 1.0:  # 超过1秒的查询
            self.slow_queries.append({
                'query': str(query),
                'time': execution_time
            })
    
    def get_stats(self):
        """获取数据库统计信息"""
        return {
            'total_queries': self.query_count,
            'slow_queries': len(self.slow_queries),
            'slowest_query': max(self.slow_queries, key=lambda x: x['time']) if self.slow_queries else None
        }

# 全局数据库监控器
db_monitor = DatabaseMonitor()
