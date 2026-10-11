"""Redis cache helpers and a small service layer."""

import json
import os
import time
import redis

DEFAULT_TTL = int(os.getenv("CACHE_TTL_SECONDS", "60"))


def create_redis_client():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        socket_timeout=float(os.getenv("REDIS_TIMEOUT", "2")),
        decode_responses=True,
    )


def cache_key(student_id):
    return f"student:{student_id}"


class StudentService:
    def __init__(self, database, redis_client, ttl=DEFAULT_TTL):
        self.database = database
        self.redis = redis_client
        self.ttl = ttl

    def get_student(self, student_id):
        cached = self.redis.get(cache_key(student_id))
        if cached is not None:
            return json.loads(cached), "HIT"
        student = self.database.get_student(student_id)
        if student is not None:
            self.redis.setex(cache_key(student_id), self.ttl, json.dumps(student, ensure_ascii=False))
        return student, "MISS"

    def invalidate(self, student_id):
        self.redis.delete(cache_key(student_id))

    def add_student(self, student_id, name, email, major):
        self.database.add_student(student_id, name, email, major)
        self.invalidate(student_id)

    def update_student(self, student_id, name, email, major):
        updated = self.database.update_student(student_id, name, email, major)
        self.invalidate(student_id)
        return updated

    def delete_student(self, student_id):
        deleted = self.database.delete_student(student_id)
        self.invalidate(student_id)
        return deleted


def benchmark(database, service, student_id, repetitions=1000):
    """Return average elapsed milliseconds for direct SQLite and Redis lookup paths."""
    start = time.perf_counter()
    for _ in range(repetitions):
        database.get_student(student_id)
    sqlite_ms = (time.perf_counter() - start) * 1000 / repetitions
    service.get_student(student_id)  # prime once so timed cache lookups measure hits
    start = time.perf_counter()
    for _ in range(repetitions):
        service.get_student(student_id)
    redis_ms = (time.perf_counter() - start) * 1000 / repetitions
    return sqlite_ms, redis_ms
