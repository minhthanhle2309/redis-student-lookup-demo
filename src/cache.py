"""Redis cache helpers and a small service layer."""

import json
import os
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


def cache_key(student_id, prefix="student:"):
    return f"{prefix}{student_id}"


class StudentService:
    def __init__(self, database, redis_client, ttl=DEFAULT_TTL, key_prefix="student:"):
        self.database = database
        self.redis = redis_client
        self.ttl = ttl
        self.key_prefix = key_prefix
        self.last_lookup = {"student_id": None, "key": None, "status": None, "ttl": None,
                            "ttl_status": "not_checked", "source": None, "events": [], "redis_state": "unknown",
                            "cache_write": "not_attempted"}
        self.last_invalidation_ok = True
        self.last_invalidation_deleted = 0

    @staticmethod
    def _event(events, stage, state, message):
        events.append({"stage": stage, "state": state, "message": message})

    def _read_ttl(self, key, events):
        try:
            remaining = self.redis.ttl(key)
        except redis.RedisError:
            self.last_lookup["ttl_status"] = "unavailable"
            self.last_lookup["redis_state"] = "degraded"
            self._event(events, "ttl_read", "error", "Không đọc được TTL từ Redis.")
            return None
        self.last_lookup["ttl"] = remaining if remaining >= 0 else None
        if remaining >= 0:
            self.last_lookup["ttl_status"] = "available"
            self._event(events, "ttl_read", "success", f"Redis trả TTL còn {remaining} giây.")
        elif remaining == -1:
            self.last_lookup["ttl_status"] = "no_expiry"
            self._event(events, "ttl_read", "warning", "Key có trong Redis nhưng không đặt thời hạn.")
        else:
            self.last_lookup["ttl_status"] = "key_missing"
            self._event(events, "ttl_read", "warning", "Key không còn tồn tại khi kiểm tra TTL.")
        return remaining

    def _read_database(self, student_id, events):
        try:
            student = self.database.get_student(student_id)
        except Exception:
            self.last_lookup.update({"status": "ERROR", "source": None})
            self._event(events, "database_error", "error", "Không thể đọc dữ liệu SQLite.")
            raise
        self.last_lookup["source"] = "SQLite"
        self._event(events, "sqlite_read", "success", "SQLite đã trả lời truy vấn theo MSSV.")
        if student is None:
            self._event(events, "sqlite_not_found", "warning", "SQLite không tìm thấy MSSV này.")
        else:
            self._event(events, "sqlite_found", "success", "Đã đọc hồ sơ từ SQLite.")
        return student

    def get_student(self, student_id):
        key = cache_key(student_id, self.key_prefix)
        events = []
        self.last_lookup = {"student_id": student_id, "key": key, "status": None, "ttl": None,
                            "ttl_status": "not_checked", "source": None, "events": events,
                            "redis_state": "checking", "cache_write": "not_attempted"}
        self._event(events, "lookup_started", "success", f"Bắt đầu tra cứu MSSV {student_id}.")
        self._event(events, "redis_check", "active", "Đang kiểm tra Redis cache.")
        try:
            cached = self.redis.get(key)
        except redis.RedisError:
            self.last_lookup["redis_state"] = "unavailable"
            self.last_lookup["ttl_status"] = "unavailable"
            events[1].update({"state": "error", "message": "Kiểm tra Redis thất bại."})
            self._event(events, "redis_error", "error", "Redis không khả dụng; chuyển sang SQLite.")
            student = self._read_database(student_id, events)
            self.last_lookup.update({"status": "BYPASS", "source": "SQLite"})
            self._event(events, "result_return", "success" if student is not None else "warning",
                        "Đã trả hồ sơ từ SQLite." if student is not None else "SQLite không có hồ sơ để trả.")
            return student, "BYPASS"
        self.last_lookup["redis_state"] = "connected"
        events[1].update({"state": "success", "message": "Redis đã phản hồi lệnh kiểm tra cache."})
        if cached is not None:
            try:
                student = json.loads(cached)
                if not isinstance(student, dict) or student.get("student_id") != student_id:
                    raise ValueError("cached student record is invalid")
                self._event(events, "redis_hit", "success", "Redis cache HIT: đã đọc dữ liệu từ cache.")
                self.last_lookup.update({"status": "HIT", "source": "Redis"})
                self._read_ttl(key, events)
                self._event(events, "result_return", "success", "Đã trả hồ sơ lấy từ Redis.")
                return student, "HIT"
            except (ValueError, TypeError):
                # A corrupt cache entry is treated as a miss; remove only this student's key.
                self._event(events, "cache_invalid", "warning", "Dữ liệu cache không hợp lệ; sẽ đọc SQLite.")
                try:
                    deleted = self.redis.delete(key)
                    self._event(events, "cache_delete", "success", "Đã xóa key cache không hợp lệ.") if deleted else None
                except redis.RedisError:
                    self._event(events, "cache_delete", "error", "Không xóa được key cache không hợp lệ.")
        else:
            self.last_lookup["ttl_status"] = "key_missing"
            self._event(events, "redis_miss", "success", "Redis đã phản hồi: key chưa có dữ liệu cache hợp lệ.")
        student = self._read_database(student_id, events)
        if student is not None:
            try:
                self.redis.setex(key, self.ttl, json.dumps(student, ensure_ascii=False))
            except redis.RedisError:
                self.last_lookup.update({"status": "BYPASS", "source": "SQLite", "redis_state": "unavailable", "cache_write": "failed"})
                self.last_lookup.update({"ttl": None, "ttl_status": "unavailable"})
                self._event(events, "cache_write", "error", "Redis không ghi được cache; kết quả hiện tại vẫn lấy từ SQLite.")
                self._event(events, "result_return", "success", "Đã trả hồ sơ lấy từ SQLite.")
                return student, "BYPASS"
            self.last_lookup["cache_write"] = "success"
            self._event(events, "cache_write", "success", "Đã ghi hồ sơ vào Redis với TTL cấu hình.")
            self._read_ttl(key, events)
        self.last_lookup["status"] = "MISS"
        self._event(events, "result_return", "success" if student is not None else "warning",
                    "Đã trả hồ sơ lấy từ SQLite." if student is not None else "Không có hồ sơ để trả.")
        return student, "MISS"

    def invalidate(self, student_id):
        try:
            self.last_invalidation_deleted = self.redis.delete(cache_key(student_id, self.key_prefix))
            self.last_invalidation_ok = True
            return True
        except redis.RedisError:
            self.last_invalidation_ok = False
            self.last_invalidation_deleted = 0
            return False

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
