# -*- coding: utf-8 -*-
"""
性能测试脚本
测试数据库优化前后的响应速度
"""

import time
import requests
from app import app, db
from sqlalchemy import text

def test_database_connection():
    """测试数据库连接速度"""
    print("🔍 测试数据库连接速度...")
    
    with app.app_context():
        try:
            start_time = time.time()
            with db.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            connection_time = time.time() - start_time
            
            print(f"✅ 数据库连接时间: {connection_time:.4f}秒")
            return connection_time
            
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return None

def test_simple_query():
    """测试简单查询速度"""
    print("🔍 测试简单查询速度...")
    
    with app.app_context():
        try:
            start_time = time.time()
            with db.engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM work"))
                count = result.fetchone()[0]
            query_time = time.time() - start_time
            
            print(f"✅ 作品数量查询时间: {query_time:.4f}秒 (结果: {count}个作品)")
            return query_time
            
        except Exception as e:
            print(f"❌ 查询失败: {e}")
            return None

def test_complex_query():
    """测试复杂查询速度（模拟首页热门作品查询）"""
    print("🔍 测试复杂查询速度（热门作品）...")
    
    with app.app_context():
        try:
            start_time = time.time()
            with db.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT w.id, w.title, COUNT(l.id) as like_count
                    FROM work w
                    LEFT JOIN "like" l ON w.id = l.target_id AND l.target_type = 'work'
                    GROUP BY w.id, w.title
                    ORDER BY like_count DESC
                    LIMIT 6
                """))
                works = result.fetchall()
            query_time = time.time() - start_time
            
            print(f"✅ 热门作品查询时间: {query_time:.4f}秒 (结果: {len(works)}个作品)")
            return query_time
            
        except Exception as e:
            print(f"❌ 复杂查询失败: {e}")
            return None

def test_website_response():
    """测试网站响应速度"""
    print("🔍 测试网站响应速度...")
    
    urls = [
        "https://interest-based-translation-platform.vercel.app/",
        "https://interest-based-translation-platform.vercel.app/works",
        "https://interest-based-translation-platform.vercel.app/messages"
    ]
    
    results = {}
    
    for url in urls:
        try:
            start_time = time.time()
            response = requests.get(url, timeout=30)
            response_time = time.time() - start_time
            
            page_name = url.split('/')[-1] if url.split('/')[-1] else 'home'
            results[page_name] = {
                'time': response_time,
                'status': response.status_code,
                'size': len(response.content)
            }
            
            print(f"✅ {page_name}: {response_time:.4f}秒 (状态: {response.status_code})")
            
        except Exception as e:
            print(f"❌ {url}: 请求失败 - {e}")
            results[url] = {'error': str(e)}
    
    return results

def run_performance_test():
    """运行完整的性能测试"""
    print("🚀 开始性能测试...")
    print("=" * 60)
    
    # 数据库测试
    print("\n📊 数据库性能测试:")
    print("-" * 40)
    
    connection_time = test_database_connection()
    simple_query_time = test_simple_query()
    complex_query_time = test_complex_query()
    
    # 网站响应测试
    print("\n🌐 网站响应测试:")
    print("-" * 40)
    
    website_results = test_website_response()
    
    # 结果汇总
    print("\n📈 性能测试结果汇总:")
    print("=" * 60)
    
    if connection_time:
        print(f"数据库连接: {connection_time:.4f}秒")
    
    if simple_query_time:
        print(f"简单查询: {simple_query_time:.4f}秒")
    
    if complex_query_time:
        print(f"复杂查询: {complex_query_time:.4f}秒")
    
    print("\n网站页面响应时间:")
    for page, result in website_results.items():
        if 'time' in result:
            print(f"  {page}: {result['time']:.4f}秒")
        else:
            print(f"  {page}: 测试失败")
    
    # 性能评估
    print("\n🎯 性能评估:")
    print("-" * 40)
    
    if connection_time and connection_time < 0.1:
        print("✅ 数据库连接: 优秀")
    elif connection_time and connection_time < 0.5:
        print("⚠️ 数据库连接: 良好")
    else:
        print("❌ 数据库连接: 需要优化")
    
    if complex_query_time and complex_query_time < 0.5:
        print("✅ 复杂查询: 优秀")
    elif complex_query_time and complex_query_time < 2.0:
        print("⚠️ 复杂查询: 良好")
    else:
        print("❌ 复杂查询: 需要优化")
    
    # 网站响应评估
    slow_pages = []
    for page, result in website_results.items():
        if 'time' in result and result['time'] > 2.0:
            slow_pages.append(page)
    
    if not slow_pages:
        print("✅ 网站响应: 优秀")
    elif len(slow_pages) <= 1:
        print("⚠️ 网站响应: 良好")
    else:
        print(f"❌ 网站响应: 需要优化 (慢页面: {', '.join(slow_pages)})")

if __name__ == '__main__':
    run_performance_test()
