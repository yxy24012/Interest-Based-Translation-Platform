#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from seed_data import seed_database, create_default_admin

def init_database():
    """初始化数据库"""
    with app.app_context():
        # 创建所有表
        db.create_all()
        print("数据库表创建完成")
        
        # 创建默认管理员
        create_default_admin()
        print("默认管理员创建完成")
        
        # 插入示例种子数据
        try:
            seed_database()
            print("示例数据已插入")
        except Exception as e:
            print(f"插入示例数据失败: {e}")
        
        print("数据库初始化完成！")

if __name__ == '__main__':
    init_database() 