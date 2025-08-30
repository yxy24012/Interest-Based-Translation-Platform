#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from seed_data import seed_database, create_default_admin

def init_render_database():
    """初始化Render数据库"""
    with app.app_context():
        try:
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
            
            print("Render数据库初始化完成！")
        except Exception as e:
            print(f"数据库初始化失败: {e}")
            sys.exit(1)

if __name__ == '__main__':
    init_render_database()
