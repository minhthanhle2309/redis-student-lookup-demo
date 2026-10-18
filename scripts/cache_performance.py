"""Compare uncached work with Redis and Memcached result caching."""

import argparse
import csv
import hashlib
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIZES = (1024, 100 * 1024, 1024**2, 5 * 1024**2, 10 * 1024**2)
SIZE_LABELS = {1024: "1 KB", 100 * 1024: "100 KB", 1024**2: "1 MB",
               5 * 1024**2: "5 MB", 10 * 1024**2: "10 MB"}
REDIS_PREFIX = "seminar:cache-performance:redis:"
MEMCACHED_PREFIX = "seminar:cache-performance:memcached:"


def make_payload(size_bytes):
    """Return a deterministic byte string of exactly size_bytes."""
    if size_bytes < 1:
        raise ValueError("Kích thước payload phải lớn hơn 0")
    pattern = bytes(range(256))
    repeats, remainder = divmod(size_bytes, len(pattern))
    return pattern * repeats + pattern[:remainder]


def process_payload(payload, rounds=3):
    """Perform real deterministic CPU work; no sleeps or fabricated timings."""
    if rounds < 1:
        raise ValueError("rounds phải lớn hơn 0")
    digest = b""
    for _ in range(rounds):
        digest = hashlib.sha256(digest + payload).digest()
    return digest


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def summarize(latencies, hits=0, misses=0):
    elapsed = sum(latencies)
    return {
        "count": len(latencies),
        "average_ms": statistics.fmean(latencies),
        "p50_ms": statistics.median(latencies),
        "p95_ms": percentile(latencies, 0.95),
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "total_elapsed_ms": elapsed,
        "throughput_ops_s": len(latencies) / (elapsed / 1000) if elapsed else 0.0,
        "hits": hits,
        "misses": misses,
        "hit_rate_percent": hits / len(latencies) * 100 if latencies else 0.0,
    }


class RedisAdapter:
    def __init__(self, client=None, host="localhost", port=6379, db=0, timeout=2):
        if client is None:
            import redis
            client = redis.Redis(host=host, port=port, db=db, socket_timeout=timeout)
        self.client = client

    def get(self, key):
        return self.client.get(key)

    def set(self, key, value, ttl):
        self.client.setex(key, ttl, value)

    def delete(self, key):
        self.client.delete(key)

    def ping(self):
        return self.client.ping()


class MemcachedAdapter:
    def __init__(self, client=None, host="127.0.0.1", port=11211, timeout=2):
        if client is None:
            from pymemcache.client.base import Client
            client = Client((host, port), connect_timeout=timeout, timeout=timeout)
        self.client = client

    def get(self, key):
        return self.client.get(key)

    def set(self, key, value, ttl):
        self.client.set(key, value, expire=ttl)

    def delete(self, key):
        self.client.delete(key)

    def ping(self):
        return self.client.version() is not None


def run_mode(mode, payload, key, rounds, runs, adapter=None):
    """Run equal measured request counts; first cache access is cold, then warm."""
    latencies, hits, misses = [], 0, 0
    for _ in range(runs):
        started = time.perf_counter()
        if adapter is None:
            process_payload(payload, rounds)
        else:
            result = adapter.get(key)
            if result is not None:
                hits += 1
            else:
                misses += 1
                adapter.set(key, process_payload(payload, rounds), 3600)
        latencies.append((time.perf_counter() - started) * 1000)
    return summarize(latencies, hits, misses)


def _cache_key(prefix, payload, rounds):
    # Compute identity outside timed sections, equally for both cache services.
    fingerprint = hashlib.sha256(payload).hexdigest()
    return f"{prefix}v1:{rounds}:{fingerprint}"


def run_suite(sizes=DEFAULT_SIZES, runs=5, rounds=3, redis_adapter=None,
              memcached_adapter=None, progress=print):
    if runs < 1 or rounds < 1 or not sizes or any(size < 1 for size in sizes):
        raise ValueError("sizes, runs và rounds phải là số dương")
    adapters = [("Redis", redis_adapter, REDIS_PREFIX),
                ("Memcached", memcached_adapter, MEMCACHED_PREFIX)]
    for name, adapter, _ in adapters:
        if adapter is None:
            raise ValueError(f"Thiếu adapter {name}")
        adapter.ping()

    output = {}
    for size in sizes:
        payload = make_payload(size)
        # One unmeasured computation warms the interpreter and CPU path.
        process_payload(payload, rounds)
        label = SIZE_LABELS.get(size, f"{size} bytes")
        output[label] = {}
        output[label]["NO CACHE"] = run_mode("NO CACHE", payload, "", rounds, runs)
        progress(f"{label} | NO CACHE: avg {output[label]['NO CACHE']['average_ms']:.3f} ms")
        for name, adapter, prefix in adapters:
            key = _cache_key(prefix, payload, rounds)
            # Remove only this exact lab key. First timed call is a genuine MISS.
            adapter.delete(key)
            # Untimed round trip warms the client connection, then clears its key.
            adapter.set(key, b"warmup", 3600)
            adapter.get(key)
            adapter.delete(key)
            result = run_mode(name, payload, key, rounds, runs, adapter)
            output[label][name] = result
            progress(f"{label} | {name}: avg {result['average_ms']:.3f} ms, "
                     f"HIT {result['hits']}, MISS {result['misses']}")
    return output


def _rows(results):
    baseline = {size: row["NO CACHE"]["average_ms"] for size, row in results.items()}
    for size, methods in results.items():
        for mode, metrics in methods.items():
            yield {"payload": size, "mode": mode, **metrics,
                   "speedup_vs_no_cache": baseline[size] / metrics["average_ms"]
                   if metrics["average_ms"] else 0.0}


def write_csv(path, results):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["payload", "mode", "count", "average_ms", "p50_ms", "p95_ms", "min_ms",
              "max_ms", "total_elapsed_ms", "throughput_ops_s", "hits", "misses",
              "hit_rate_percent", "speedup_vs_no_cache"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(_rows(results))


def write_markdown(path, results, runs, rounds):
    lines = ["# Cache Performance Lab", "", f"Thời điểm đo: {datetime.now(timezone.utc).isoformat()}",
             f"Số lượt/mode: {runs}; số vòng SHA-256 trên payload: {rounds}", "",
             "| Payload | Mode | Avg (ms) | p50 (ms) | p95 (ms) | Min–max (ms) | Ops/s | HIT | MISS | Hit rate | Speedup |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in _rows(results):
        lines.append(f"| {row['payload']} | {row['mode']} | {row['average_ms']:.3f} | "
                     f"{row['p50_ms']:.3f} | {row['p95_ms']:.3f} | "
                     f"{row['min_ms']:.3f}–{row['max_ms']:.3f} | {row['throughput_ops_s']:.2f} | "
                     f"{row['hits']} | {row['misses']} | {row['hit_rate_percent']:.1f}% | "
                     f"{row['speedup_vs_no_cache']:.2f}x |")
    lines += ["", "## Cách đọc và giới hạn", "",
              "Payload được tạo xác định và xử lý bằng nhiều vòng SHA-256 thật; không dùng sleep để tạo độ trễ. Cache lưu digest 32 byte của kết quả, còn payload đầu vào giống nhau ở cả ba mode. Mỗi mode có cùng số lượt đo; cache được làm nóng kết nối ngoài vùng đo, xóa đúng key riêng trước khi chạy, rồi đo một MISS lạnh và các HIT tiếp theo. Payload và checksum tạo key nằm ngoài khoảng bấm giờ; lệnh cache, xử lý payload khi MISS và ghi cache nằm trong khoảng đo.", "",
              "Đây là workload CPU-bound trên một tiến trình và kết nối local. Nó minh họa chi phí xử lý được tránh khi có HIT, không đại diện cho mọi ứng dụng hay cho cache các object lớn. Redis/Memcached có overhead mạng, serialization và tải nền; kết quả thay đổi theo máy, cấu hình và số vòng. Không dùng kết quả này làm cam kết hiệu năng.", ""]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _parse_sizes(value):
    units = {"KB": 1024, "MB": 1024**2}
    sizes = []
    try:
        for item in value.split(","):
            item = item.strip().upper().replace(" ", "")
            unit = next((unit for unit in units if item.endswith(unit)), None)
            sizes.append(int(item[:-len(unit)]) * units[unit] if unit else int(item))
    except (ValueError, StopIteration) as exc:
        raise argparse.ArgumentTypeError("Dùng định dạng như 1KB,100KB,1MB") from exc
    return sizes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=_parse_sizes, default=list(DEFAULT_SIZES),
                        help="Comma-separated payload sizes, e.g. 1KB,100KB,1MB,5MB,10MB")
    parser.add_argument("--runs", type=int, default=5, help="Measured requests per mode")
    parser.add_argument("--rounds", type=int, default=3, help="SHA-256 rounds per payload")
    parser.add_argument("--mode", choices=("all", "no-cache", "redis", "memcached"), default="all")
    parser.add_argument("--csv", type=Path, default=ROOT / "benchmark-results" / "cache-performance.csv")
    parser.add_argument("--markdown", type=Path, default=ROOT / "benchmark-results" / "cache-performance.md")
    args = parser.parse_args(argv)
    redis_adapter = RedisAdapter() if args.mode in ("all", "redis") else None
    memcached_adapter = MemcachedAdapter() if args.mode in ("all", "memcached") else None
    if args.mode == "no-cache":
        results = {}
        for size in args.sizes:
            payload = make_payload(size)
            process_payload(payload, args.rounds)
            label = SIZE_LABELS.get(size, f"{size} bytes")
            results[label] = {"NO CACHE": run_mode("NO CACHE", payload, "", args.rounds, args.runs)}
    else:
        # Run selected backends; preserve the default three-way comparison.
        if args.mode == "redis":
            memcached_adapter = _NoopAdapter()
        elif args.mode == "memcached":
            redis_adapter = _NoopAdapter()
        results = run_suite(args.sizes, args.runs, args.rounds, redis_adapter,
                            memcached_adapter, progress=print)
        if args.mode != "all":
            selected = "Redis" if args.mode == "redis" else "Memcached"
            results = {size: {"NO CACHE": modes["NO CACHE"], selected: modes[selected]}
                       for size, modes in results.items()}
    write_csv(args.csv, results)
    write_markdown(args.markdown, results, args.runs, args.rounds)
    print(f"Saved CSV: {args.csv}\nSaved Markdown: {args.markdown}")


class _NoopAdapter:
    """Allows a single-backend CLI selection without probing the other service."""
    def ping(self):
        return True

    def get(self, key):
        return None

    def set(self, key, value, ttl):
        pass

    def delete(self, key):
        pass


if __name__ == "__main__":
    main()
