import csv

from scripts.benchmark import BenchmarkDatabase, PREFIX, run_benchmark, summarize, write_csv, write_markdown
import pytest


def test_metric_calculation_and_export(tmp_path):
    metrics = summarize([1.0, 2.0, 3.0, 4.0, 100.0])
    assert metrics["count"] == 5
    assert metrics["average_ms"] == 22.0
    assert metrics["median_ms"] == 3.0
    assert metrics["p95_ms"] == 100.0
    assert round(metrics["throughput_ops_s"], 4) == round(5 / 0.11, 4)

    results = {"SQLite direct": {**metrics, "hits": 0, "misses": 0, "hit_rate": None}}
    csv_path, md_path = tmp_path / "results.csv", tmp_path / "summary.md"
    write_csv(csv_path, results)
    write_markdown(md_path, results, {"dataset_size": 2}, "benchmark.db")
    with csv_path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["median_ms"] == "3.0" and row["hit_rate_percent"] == ""
    assert "100.0000" in md_path.read_text(encoding="utf-8")


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expiries = {}

    def scan_iter(self, match):
        return iter(list(self.values))

    def delete(self, key):
        self.values.pop(key, None)
        self.expiries.pop(key, None)

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.expiries[key] = ttl

    def get(self, key):
        return self.values.get(key)

    def ttl(self, key):
        return self.expiries.get(key, -2)


def test_same_workload_cold_misses_warm_hits_and_separate_database(tmp_path):
    path = tmp_path / "benchmark.sqlite"
    db = BenchmarkDatabase(path)
    client = FakeRedis()
    try:
        results, config = run_benchmark(db, client, dataset_size=5, query_count=8, repetitions=2, seed=10)
        assert config["total_queries_per_method"] == 16
        assert results["SQLite direct"]["count"] == 16
        assert results["Redis cold cache"]["misses"] == 16
        assert results["Redis warm cache"]["hits"] == 16
        assert all(key.startswith(PREFIX) for key in client.values)
        assert db.connection.execute("select count(*) from students").fetchone()[0] == 5
    finally:
        db.close()


def test_benchmark_refuses_original_demo_database():
    from scripts.benchmark import ROOT

    with pytest.raises(ValueError, match="separate"):
        BenchmarkDatabase(ROOT / "data" / "students.db")
