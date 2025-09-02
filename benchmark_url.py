#!/usr/bin/env python3
"""
benchmark_url.py
----------------
快速测试一个 URL 多次请求的性能，输出：
- Server-Timing (ms) 从响应头解析 (X-Server-Timing 或 Server-Timing)
- TTFB (s) 近似首字节时间
- Total (s) 请求完整耗时
并统计 avg/median/p95。

用法示例：
    python benchmark_url.py -u https://interest-based-translation-platform.vercel.app/works -n 10 --delay-ms 250
"""

import argparse
import re
import statistics
import time
from typing import List, Optional

import requests


def parse_server_timing(headers: requests.structures.CaseInsensitiveDict) -> Optional[float]:
    """
    从响应头解析 Server-Timing: total;dur=xxx
    返回毫秒 (float)，找不到则返回 None
    """
    val = headers.get("Server-Timing") or headers.get("X-Server-Timing")
    if not val:
        return None
    m = re.search(r"total\s*;\s*dur\s*=\s*([0-9]+(?:\.[0-9]+)?)", val, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def p95(values: List[float]) -> float:
    if not values:
        return float("nan")
    vs = sorted(values)
    idx = max(0, min(len(vs)-1, int(round(0.95 * (len(vs)-1)))))
    return vs[idx]


def run_once(session: requests.Session, url: str, method: str = "GET", timeout: float = 30.0) -> dict:
    """
    执行一次请求，返回字典：server_timing_ms, ttfb_s, total_s, status, bytes
    """
    start = time.perf_counter()
    resp = session.request(method.upper(), url, timeout=timeout, stream=True)
    ttfb_s = resp.elapsed.total_seconds()

    total_bytes = 0
    for chunk in resp.iter_content(chunk_size=65536):
        if chunk:
            total_bytes += len(chunk)
    total_s = time.perf_counter() - start

    server_timing_ms = parse_server_timing(resp.headers)

    return {
        "server_timing_ms": server_timing_ms,
        "ttfb_s": ttfb_s,
        "total_s": total_s,
        "status": resp.status_code,
        "bytes": total_bytes,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-u", "--url", required=True, help="目标 URL (例如 https://site/works)")
    ap.add_argument("-n", "--times", type=int, default=10, help="循环次数 (默认: 10)")
    ap.add_argument("--delay-ms", type=int, default=250, help="两次请求之间延迟毫秒 (默认: 250)")
    ap.add_argument("--method", default="GET", help="HTTP 方法 (默认: GET)")
    ap.add_argument("--timeout", type=float, default=30.0, help="请求超时 (默认: 30 秒)")
    args = ap.parse_args()

    st_list, ttfb_list, total_list = [], [], []

    with requests.Session() as sess:
        for i in range(1, args.times + 1):
            try:
                r = run_once(sess, args.url, method=args.method, timeout=args.timeout)
                st = r["server_timing_ms"]
                ttfb = r["ttfb_s"]
                total = r["total_s"]
                st_list.append(st if st is not None else float("nan"))
                ttfb_list.append(ttfb)
                total_list.append(total)
                print(f"[{i:02d}] status={r['status']}  bytes={r['bytes']}  "
                      f"ServerTiming(ms)={st if st is not None else 'NA'}  "
                      f"TTFB(s)={ttfb:.3f}  Total(s)={total:.3f}")
            except Exception as e:
                print(f"[{i:02d}] ERROR: {e}")
            time.sleep(args.delay_ms / 1000.0)

    def safe_avg(vals: List[float]) -> float:
        vals2 = [v for v in vals if v == v]
        return statistics.fmean(vals2) if vals2 else float("nan")

    def safe_median(vals: List[float]) -> float:
        vals2 = [v for v in vals if v == v]
        return statistics.median(vals2) if vals2 else float("nan")

    print("\n--- SUMMARY ---")
    print(f"ServerTiming(ms)  avg={safe_avg(st_list):.1f}  median={safe_median(st_list):.1f}  p95={p95([v for v in st_list if v == v]):.1f}")
    print(f"TTFB(s)          avg={safe_avg(ttfb_list):.3f}  median={safe_median(ttfb_list):.3f}  p95={p95(ttfb_list):.3f}")
    print(f"Total(s)         avg={safe_avg(total_list):.3f}  median={safe_median(total_list):.3f}  p95={p95(total_list):.3f}")


if __name__ == "__main__":
    main()
