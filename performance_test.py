# -*- coding: utf-8 -*-
"""
性能测试脚本
用于评估Vercel环境下的应用性能
"""

import time
import requests
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

def test_endpoint_performance(url, endpoint, num_requests=10):
    """测试单个端点的性能"""
    times = []
    errors = 0
    
    print(f"测试端点: {endpoint}")
    
    for i in range(num_requests):
        try:
            start_time = time.time()
            response = requests.get(f"{url}{endpoint}", timeout=30)
            end_time = time.time()
            
            if response.status_code == 200:
                times.append(end_time - start_time)
                print(f"  请求 {i+1}: {times[-1]:.3f}秒")
            else:
                errors += 1
                print(f"  请求 {i+1}: 错误状态码 {response.status_code}")
                
        except Exception as e:
            errors += 1
            print(f"  请求 {i+1}: 错误 - {e}")
    
    if times:
        avg_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        print(f"  ✅ 平均响应时间: {avg_time:.3f}秒")
        print(f"  📊 最快: {min_time:.3f}秒, 最慢: {max_time:.3f}秒")
        print(f"  ❌ 错误数: {errors}")
        return {
            'endpoint': endpoint,
            'avg_time': avg_time,
            'min_time': min_time,
            'max_time': max_time,
            'errors': errors,
            'success_rate': (num_requests - errors) / num_requests * 100
        }
    else:
        print(f"  ❌ 所有请求都失败了")
        return None

def test_concurrent_performance(url, endpoint, num_concurrent=5, requests_per_thread=2):
    """测试并发性能"""
    print(f"\n测试并发性能: {endpoint} ({num_concurrent} 并发, 每个线程 {requests_per_thread} 请求)")
    
    def worker():
        return test_endpoint_performance(url, endpoint, requests_per_thread)
    
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        futures = [executor.submit(worker) for _ in range(num_concurrent)]
        results = []
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    if results:
        avg_response_times = [r['avg_time'] for r in results]
        total_avg = statistics.mean(avg_response_times)
        print(f"  📈 并发测试完成: {total_time:.3f}秒")
        print(f"  🎯 平均响应时间: {total_avg:.3f}秒")
        print(f"  📊 吞吐量: {num_concurrent * requests_per_thread / total_time:.2f} 请求/秒")

def main():
    """主测试函数"""
    # 测试URL（请替换为您的实际URL）
    test_urls = [
        "https://interest-based-translation-platform.vercel.app",
        "https://interest-based-translation-pla-git-3679f1-yang-xingyus-projects.vercel.app"
    ]
    
    # 测试端点
    endpoints = [
        "/",
        "/works",
        "/profile",
        "/static/favicon.ico"
    ]
    
    for url in test_urls:
        print(f"\n{'='*60}")
        print(f"测试URL: {url}")
        print(f"{'='*60}")
        
        # 单线程测试
        for endpoint in endpoints:
            test_endpoint_performance(url, endpoint, num_requests=5)
        
        # 并发测试
        test_concurrent_performance(url, "/", num_concurrent=3, requests_per_thread=2)

if __name__ == '__main__':
    main()
