"""Reproducible SQLite versus Redis cache benchmark for classroom use."""

import argparse
import csv
import math
import random
import sqlite3
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from src.cache import StudentService, create_redis_client

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "benchmark_students.db"
PREFIX = "seminar:benchmark:student:"


def percentile(values, percent):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percent * len(ordered)) - 1)]


def summarize(latencies_ms, elapsed_ms=None):
    total = sum(latencies_ms)
    elapsed = total if elapsed_ms is None else elapsed_ms
    elapsed_seconds = elapsed / 1000
    return {
        "count": len(latencies_ms),
        "average_ms": statistics.fmean(latencies_ms) if latencies_ms else 0.0,
        "median_ms": statistics.median(latencies_ms) if latencies_ms else 0.0,
        "p95_ms": percentile(latencies_ms, 0.95) if latencies_ms else 0.0,
        "total_elapsed_ms": elapsed,
        "throughput_ops_s": len(latencies_ms) / elapsed_seconds if elapsed_seconds else 0.0,
    }


class BenchmarkDatabase:
    def __init__(self, path):
        self.path = Path(path)
        original_db = ROOT / "data" / "students.db"
        if self.path.resolve() == original_db.resolve():
            raise ValueError("Benchmark database must be separate from the demo database")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)

    def prepare(self, size):
        self.connection.execute("CREATE TABLE IF NOT EXISTS students (student_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, major TEXT NOT NULL)")
        # This is the dedicated benchmark database; replace only its synthetic benchmark rows.
        self.connection.execute("DELETE FROM students")
        self.connection.executemany("INSERT INTO students VALUES (?, ?, ?, ?)", (
            (f"BENCH{i:08d}", f"Student {i:08d}", f"student{i}@example.edu", f"Major {i % 12:02d}")
            for i in range(size)
        ))
        self.connection.commit()

    def get_student(self, student_id):
        row = self.connection.execute("SELECT student_id, name, email, major FROM students WHERE student_id=?", (student_id,)).fetchone()
        return dict(zip(("student_id", "name", "email", "major"), row)) if row else None

    def close(self):
        self.connection.close()


def run_benchmark(database, client, dataset_size=1000, query_count=500, repetitions=3, seed=2026):
    if min(dataset_size, query_count, repetitions) < 1:
        raise ValueError("dataset_size, query_count, and repetitions must be positive")
    database.prepare(dataset_size)
    rng = random.Random(seed)
    workload = [f"BENCH{rng.randrange(dataset_size):08d}" for _ in range(query_count)]
    queries = workload * repetitions
    service = StudentService(database, client, ttl=300, key_prefix=PREFIX)
    # Only remove this benchmark's own namespace, in bounded SCAN batches.
    for key in client.scan_iter(match=f"{PREFIX}*"):
        client.delete(key)

    measurements = {}
    direct = []
    for sid in queries:
        start = time.perf_counter()
        database.get_student(sid)
        direct.append((time.perf_counter() - start) * 1000)
    measurements["SQLite direct"] = {**summarize(direct), "hits": 0, "misses": 0, "hit_rate": None}

    # Time a Redis cache-aside miss per query. Namespace deletion happens outside each timed interval.
    cold = []
    cold_hits = cold_misses = 0
    for sid in queries:
        client.delete(f"{PREFIX}{sid}")
        start = time.perf_counter()
        _, status = service.get_student(sid)
        cold.append((time.perf_counter() - start) * 1000)
        cold_hits += status == "HIT"
        cold_misses += status == "MISS"
    measurements["Redis cold cache"] = {**summarize(cold), "hits": cold_hits, "misses": cold_misses,
                                          "hit_rate": cold_hits / len(cold) * 100}

    # Warm exactly the same sequence before starting the timed warm-cache pass.
    for sid in queries:
        service.get_student(sid)
    warm = []
    warm_hits = warm_misses = 0
    for sid in queries:
        start = time.perf_counter()
        _, status = service.get_student(sid)
        warm.append((time.perf_counter() - start) * 1000)
        warm_hits += status == "HIT"
        warm_misses += status == "MISS"
    measurements["Redis warm cache"] = {**summarize(warm), "hits": warm_hits, "misses": warm_misses,
                                          "hit_rate": warm_hits / len(warm) * 100}
    return measurements, {"dataset_size": dataset_size, "query_count_per_repetition": query_count,
                          "repetitions": repetitions, "total_queries_per_method": len(queries), "seed": seed}


def write_csv(path, measurements):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["method", "count", "average_ms", "median_ms", "p95_ms", "total_elapsed_ms", "throughput_ops_s", "hits", "misses", "hit_rate_percent"]
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for method, row in measurements.items():
            writer.writerow({"method": method, **{k: row.get(k) for k in fields[1:-1]}, "hit_rate_percent": row.get("hit_rate")})


def write_markdown(path, measurements, config, db_path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kết quả benchmark SQLite và Redis", "", f"Thời điểm đo: {datetime.now(timezone.utc).isoformat()}",
             f"Database riêng: `{db_path}`", f"Cấu hình: {config}", "",
             "| Phương thức | Trung bình (ms) | Median/p50 (ms) | p95 (ms) | Tổng thời gian (ms) | Throughput (ops/s) | HIT | MISS | Tỷ lệ HIT |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for method, row in measurements.items():
        rate = "—" if row["hit_rate"] is None else f"{row['hit_rate']:.1f}%"
        lines.append(f"| {method} | {row['average_ms']:.4f} | {row['median_ms']:.4f} | {row['p95_ms']:.4f} | {row['total_elapsed_ms']:.2f} | {row['throughput_ops_s']:.1f} | {row['hits']} | {row['misses']} | {rate} |")
    lines += ["", "## Giới hạn đo", "", "Đây là phép đo một tiến trình trên máy hiện tại; kết quả chịu ảnh hưởng của kích thước dataset, SQLite cache của hệ điều hành, Redis local, serialization, kết nối và tải nền. Tổng elapsed là tổng các khoảng tra cứu được bấm giờ; chuẩn bị dataset, xóa khóa để tạo cold cache, làm nóng cache, và overhead vòng lặp không nằm trong tổng đo. Redis không được đảm bảo nhanh hơn SQLite trong mọi cấu hình.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-size", type=int, default=1000)
    parser.add_argument("--queries", type=int, default=500)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--csv", type=Path, default=ROOT / "benchmark-results" / "results.csv")
    parser.add_argument("--markdown", type=Path, default=ROOT / "benchmark-results" / "summary.md")
    args = parser.parse_args()
    client = create_redis_client()
    client.ping()
    database = BenchmarkDatabase(DEFAULT_DB)
    try:
        results, config = run_benchmark(database, client, args.dataset_size, args.queries, args.repetitions, args.seed)
    finally:
        database.close()
    write_csv(args.csv, results)
    write_markdown(args.markdown, results, config, DEFAULT_DB)
    print(f"Đã lưu CSV: {args.csv}\nĐã lưu Markdown: {args.markdown}")
    for method, result in results.items():
        print(f"{method}: avg={result['average_ms']:.4f}ms p50={result['median_ms']:.4f}ms p95={result['p95_ms']:.4f}ms")


if __name__ == "__main__":
    main()
