import csv

from scripts.cache_performance import (
    DEFAULT_SIZES,
    MEMCACHED_PREFIX,
    REDIS_PREFIX,
    _cache_key,
    _parse_sizes,
    make_payload,
    process_payload,
    run_mode,
    run_suite,
    summarize,
    write_csv,
    write_markdown,
)


class FakeAdapter:
    def __init__(self):
        self.values = {}
        self.deleted = []

    def ping(self):
        return True

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ttl):
        self.values[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)


def test_payload_is_exact_deterministic_and_processing_is_real():
    assert len(make_payload(1025)) == 1025
    assert make_payload(1025) == make_payload(1025)
    assert process_payload(b"example", rounds=1) != process_payload(b"different", rounds=1)


def test_metrics_include_distribution_and_hit_rate():
    metrics = summarize([1.0, 2.0, 3.0, 4.0, 100.0], hits=4, misses=1)
    assert metrics["average_ms"] == 22.0
    assert metrics["p50_ms"] == 3.0
    assert metrics["p95_ms"] == 100.0
    assert metrics["hit_rate_percent"] == 80.0


def test_cache_key_namespaces_are_separate():
    payload = make_payload(100)
    assert _cache_key(REDIS_PREFIX, payload, 2).startswith(REDIS_PREFIX)
    assert _cache_key(MEMCACHED_PREFIX, payload, 2).startswith(MEMCACHED_PREFIX)
    assert _cache_key(REDIS_PREFIX, payload, 2) != _cache_key(MEMCACHED_PREFIX, payload, 2)


def test_run_mode_records_one_cold_miss_then_warm_hits():
    adapter = FakeAdapter()
    result = run_mode("Redis", b"payload", "key", 1, 4, adapter)
    assert result["misses"] == 1
    assert result["hits"] == 3
    assert result["count"] == 4


def test_suite_clears_only_its_own_key_and_exports_reports(tmp_path):
    redis, memcached = FakeAdapter(), FakeAdapter()
    redis.values["unrelated"] = b"keep"
    results = run_suite([1024], 2, 1, redis, memcached, progress=lambda _: None)
    assert set(results["1 KB"]) == {"NO CACHE", "Redis", "Memcached"}
    assert results["1 KB"]["Redis"]["misses"] == 1
    assert results["1 KB"]["Redis"]["hits"] == 1
    assert redis.values["unrelated"] == b"keep"
    assert all(key.startswith(REDIS_PREFIX) for key in redis.deleted)
    assert all(key.startswith(MEMCACHED_PREFIX) for key in memcached.deleted)

    csv_path, md_path = tmp_path / "lab.csv", tmp_path / "lab.md"
    write_csv(csv_path, results)
    write_markdown(md_path, results, runs=2, rounds=1)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert "p95_ms" in rows[0] and "speedup_vs_no_cache" in rows[0]
    assert "HIT lạnh" not in md_path.read_text(encoding="utf-8")
    assert "không dùng sleep" in md_path.read_text(encoding="utf-8")


def test_sizes_parser_and_validation():
    assert _parse_sizes("1KB,100KB,1MB") == [1024, 102400, 1024**2]
    assert DEFAULT_SIZES[-1] == 10 * 1024**2
