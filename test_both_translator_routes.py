#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from app import app, db, User
from werkzeug.security import generate_password_hash

def test_both_translator_routes():
    with app.test_client() as client:
        with app.app_context():
            try:
                print("=== 测试两个翻译者申请路由 ===")
                
                # 创建测试用户
                test_user = User.query.filter_by(username='both_test_user').first()
                if not test_user:
                    test_user = User(
                        username='both_test_user',
                        email='both_test@example.com',
                        password_hash=generate_password_hash('password123'),
                        role='user',
                        is_translator=False,
                        is_reviewer=False,
                        is_creator=False,
                        preferred_language='zh',
                        experience=0,
                        email_notifications_enabled=True
                    )
                    db.session.add(test_user)
                    db.session.commit()
                    print("✓ 创建测试用户成功")
                else:
                    # 重置用户状态
                    test_user.is_translator = False
                    db.session.commit()
                    print("✓ 重置测试用户状态")
                
                print(f"用户ID: {test_user.id}")
                print(f"用户名: {test_user.username}")
                print(f"当前翻译者状态: {test_user.is_translator}")
                
                # 设置登录状态
                with client.session_transaction() as sess:
                    sess['user_id'] = test_user.id
                    sess['username'] = test_user.username
                    sess['role'] = test_user.role
                
                # 测试1: /apply/translator 路由
                print("\n--- 测试1: /apply/translator 路由 ---")
                response = client.get('/apply/translator')
                print(f"状态码: {response.status_code}")
                if response.status_code == 200:
                    content = response.get_data(as_text=True)
                    if '翻译者测试' in content:
                        print("✓ /apply/translator 路由正常")
                    else:
                        print("⚠ /apply/translator 页面内容不正确")
                else:
                    print(f"✗ /apply/translator 路由失败，状态码: {response.status_code}")
                
                # 测试2: /test/translator 路由
                print("\n--- 测试2: /test/translator 路由 ---")
                response = client.get('/test/translator')
                print(f"状态码: {response.status_code}")
                if response.status_code == 200:
                    content = response.get_data(as_text=True)
                    if '翻译者测试' in content:
                        print("✓ /test/translator 路由正常")
                    else:
                        print("⚠ /test/translator 页面内容不正确")
                else:
                    print(f"✗ /test/translator 路由失败，状态码: {response.status_code}")
                
                # 测试3: 提交申请到 /apply/translator
                print("\n--- 测试3: 提交申请到 /apply/translator ---")
                response = client.post('/apply/translator')
                print(f"状态码: {response.status_code}")
                if response.status_code == 302:
                    print(f"重定向到: {response.location}")
                    if 'profile' in response.location:
                        print("✓ /apply/translator 提交成功")
                    else:
                        print("⚠ 重定向到其他页面")
                else:
                    print("⚠ 未重定向")
                
                # 验证用户状态
                updated_user = User.query.get(test_user.id)
                print(f"更新后翻译者状态: {updated_user.is_translator}")
                
                # 重置用户状态
                test_user.is_translator = False
                db.session.commit()
                
                # 测试4: 提交申请到 /test/translator
                print("\n--- 测试4: 提交申请到 /test/translator ---")
                response = client.post('/test/translator')
                print(f"状态码: {response.status_code}")
                if response.status_code == 302:
                    print(f"重定向到: {response.location}")
                    if 'profile' in response.location:
                        print("✓ /test/translator 提交成功")
                    else:
                        print("⚠ 重定向到其他页面")
                else:
                    print("⚠ 未重定向")
                
                # 验证用户状态
                updated_user = User.query.get(test_user.id)
                print(f"更新后翻译者状态: {updated_user.is_translator}")
                
                print("\n=== 测试完成 ===")
                
            except Exception as e:
                print(f"测试过程中发生错误: {e}")
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    test_both_translator_routes()
