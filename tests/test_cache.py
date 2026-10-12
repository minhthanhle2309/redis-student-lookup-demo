import json
import time

from src.cache import StudentService, cache_key


class FakeDatabase:
    def __init__(self):
        self.students = {"SV001": {"student_id": "SV001", "name": "An", "email": "an@example.edu", "major": "CS"}}

    def get_student(self, student_id):
        return self.students.get(student_id)

    def add_student(self, sid, name, email, major):
        if sid in self.students:
            raise ValueError("duplicate")
        self.students[sid] = {"student_id": sid, "name": name, "email": email, "major": major}

    def update_student(self, sid, name, email, major):
        if sid not in self.students:
            return False
        self.students[sid] = {"student_id": sid, "name": name, "email": email, "major": major}
        return True

    def delete_student(self, sid):
        return self.students.pop(sid, None) is not None


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.expiry = {}
        self.now = time.monotonic()

    def get(self, key):
        if key in self.expiry and self.expiry[key] <= self.now:
            self.delete(key)
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.ttls[key] = ttl
        self.values[key] = value
        self.expiry[key] = self.now + ttl

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)

    def ttl(self, key):
        if self.get(key) is None:
            return -2
        return int(self.expiry[key] - self.now)


def make_service():
    db, client = FakeDatabase(), FakeRedis()
    return db, client, StudentService(db, client, ttl=42)


def test_cache_miss_then_hit_and_ttl():
    db, client, service = make_service()
    student, status = service.get_student("SV001")
    assert status == "MISS" and student["name"] == "An"
    assert client.ttls[cache_key("SV001")] == 42
    assert service.get_student("SV001")[1] == "HIT"
    client.now += 43
    assert service.get_student("SV001")[1] == "MISS"


def test_missing_student_is_not_cached():
    _, client, service = make_service()
    assert service.get_student("UNKNOWN") == (None, "MISS")
    assert cache_key("UNKNOWN") not in client.values


def test_update_and_delete_invalidate_old_cache():
    _, client, service = make_service()
    service.get_student("SV001")
    assert service.update_student("SV001", "Updated", "new@example.edu", "Math")
    assert cache_key("SV001") not in client.values
    assert service.get_student("SV001")[0]["name"] == "Updated"
    assert service.delete_student("SV001")
    assert cache_key("SV001") not in client.values
    assert service.get_student("SV001")[0] is None


def test_add_invalidates_cache_key():
    _, client, service = make_service()
    client.values[cache_key("SV002")] = json.dumps({"stale": True})
    service.add_student("SV002", "Binh", "b@example.edu", "IS")
    assert cache_key("SV002") not in client.values


def test_lookup_exposes_key_and_remaining_ttl():
    _, client, service = make_service()
    service.get_student("SV001")
    student, status = service.get_student("SV001")
    assert student["student_id"] == "SV001"
    assert status == "HIT"
    assert {key: service.last_lookup[key] for key in ("student_id", "key", "status", "ttl")} == {
        "student_id": "SV001", "key": "student:SV001", "status": "HIT", "ttl": 42}


def test_redis_read_failure_falls_back_without_claiming_hit():
    import redis

    db, client, service = make_service()
    client.get = lambda _key: (_ for _ in ()).throw(redis.ConnectionError("offline"))
    student, status = service.get_student("SV001")
    assert student == db.students["SV001"]
    assert status == "BYPASS"
    assert service.last_lookup["status"] == "BYPASS"


def test_ttl_read_failure_does_not_turn_a_real_cache_hit_into_miss():
    import redis

    _, client, service = make_service()
    service.get_student("SV001")
    client.ttl = lambda _key: (_ for _ in ()).throw(redis.ConnectionError("offline"))
    student, status = service.get_student("SV001")
    assert status == "HIT" and student["student_id"] == "SV001"
    assert service.last_lookup["source"] == "Redis"
    assert service.last_lookup["ttl_status"] == "unavailable"


def test_malformed_cached_value_is_not_reported_as_hit():
    _, client, service = make_service()
    client.values[cache_key("SV001")] = json.dumps({"student_id": "SV999"})
    student, status = service.get_student("SV001")
    assert status == "MISS" and student["student_id"] == "SV001"
    assert any(event["stage"] == "cache_invalid" for event in service.last_lookup["events"])
