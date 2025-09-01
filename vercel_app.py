# -*- coding: utf-8 -*-
"""
Vercel专用启动文件
包含错误处理和简化的配置
"""

import os
import sys

# 设置环境变量
os.environ['VERCEL'] = '1'

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # 尝试导入主应用
    from app import app
    
    # 确保数据库表存在
    with app.app_context():
        try:
            from app import db
            db.create_all()
            print("✅ 数据库表创建成功")
        except Exception as e:
            print(f"⚠️ 数据库初始化警告: {e}")
    
    print("✅ Vercel应用启动成功")
    
except Exception as e:
    print(f"❌ 主应用启动失败: {e}")
    import traceback
    traceback.print_exc()
    
    try:
        # 尝试使用简化版应用
        print("🔄 尝试使用简化版应用...")
        from simple_app import app
        print("✅ 简化版应用启动成功")
        
    except Exception as e2:
        print(f"❌ 简化版应用也失败: {e2}")
        
        # 创建一个基本的错误应用
        from flask import Flask, jsonify
        
        app = Flask(__name__)
        
        @app.route('/')
        def error_handler():
            return jsonify({
                'error': 'Application failed to start',
                'main_error': str(e),
                'simple_error': str(e2),
                'status': 'error'
            }), 500
        
        @app.route('/<path:path>')
        def catch_all(path):
            return jsonify({
                'error': 'Application failed to start',
                'main_error': str(e),
                'simple_error': str(e2),
                'status': 'error'
            }), 500

# 导出应用实例
if __name__ == '__main__':
    app.run(debug=False)
