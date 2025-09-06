# -*- coding: utf-8 -*-
"""
Vercel专用启动文件
包含错误处理和简化的配置
"""
import os
import sys
os.environ['VERCEL'] = '1'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import app
    from flask import send_from_directory
    import os

    # 添加静态文件路由处理（Vercel专用）
    @app.route('/static/<path:filename>')
    def vercel_static(filename):
        """Vercel环境下的静态文件处理"""
        try:
            return send_from_directory('static', filename)
        except Exception as e:
            print(f"静态文件访问错误: {e}")
            return "File not found", 404

    @app.route('/uploads/<path:filename>')
    def vercel_uploads(filename):
        """Vercel环境下的上传文件处理"""
        try:
            from app import app as main_app
            return send_from_directory(main_app.config['UPLOAD_FOLDER'], filename)
        except Exception as e:
            print(f"上传文件访问错误: {e}")
            return "File not found", 404

    # 确保数据库表存在（仅启动时尝试一次）
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
        # 兜底到简化版应用
        print("🔄 尝试使用简化版应用...")
        from simple_app import app
        print("✅ 简化版应用启动成功")
    except Exception as e2:
        print(f"❌ 简化版应用也失败: {e2}")
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

if __name__ == '__main__':
    app.run(debug=False)
