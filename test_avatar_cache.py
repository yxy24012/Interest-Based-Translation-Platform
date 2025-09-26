#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试头像缓存修复的脚本
"""
import requests
import time

def test_avatar_cache():
    """测试头像缓存是否被正确禁用"""
    
    # 测试URL（需要替换为实际的Vercel部署URL）
    base_url = "https://your-app.vercel.app"  # 请替换为实际的URL
    
    test_urls = [
        f"{base_url}/avatar/1",  # 用户头像
        f"{base_url}/default-avatar",  # 默认头像
        f"{base_url}/uploads/avatar_1.jpg",  # 上传的头像文件
    ]
    
    print("🔍 测试头像缓存设置...")
    
    for url in test_urls:
        try:
            print(f"\n📡 测试URL: {url}")
            
            # 发送请求
            response = requests.get(url, timeout=10)
            
            # 检查响应状态
            if response.status_code == 200:
                print(f"✅ 状态码: {response.status_code}")
                
                # 检查缓存相关的头部
                cache_headers = {
                    'Cache-Control': response.headers.get('Cache-Control', '未设置'),
                    'Pragma': response.headers.get('Pragma', '未设置'),
                    'Expires': response.headers.get('Expires', '未设置'),
                    'Last-Modified': response.headers.get('Last-Modified', '未设置'),
                    'ETag': response.headers.get('ETag', '未设置')
                }
                
                print("📋 缓存头部:")
                for header, value in cache_headers.items():
                    print(f"   {header}: {value}")
                
                # 验证缓存是否被禁用
                cache_control = response.headers.get('Cache-Control', '')
                if 'no-store' in cache_control and 'no-cache' in cache_control:
                    print("✅ 缓存已正确禁用")
                else:
                    print("❌ 缓存可能未被正确禁用")
                    
            else:
                print(f"❌ 请求失败，状态码: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 请求错误: {e}")
        except Exception as e:
            print(f"❌ 其他错误: {e}")
    
    print("\n🎯 测试完成！")
    print("\n💡 如果看到'缓存已正确禁用'，说明修复成功。")
    print("💡 如果仍然有问题，请检查Vercel部署是否已更新。")

if __name__ == "__main__":
    test_avatar_cache()
