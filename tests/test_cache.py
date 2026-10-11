import json

from src.cache import StudentService, benchmark, cache_key


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

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.ttls[key] = ttl
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


def make_service():
    db, client = FakeDatabase(), FakeRedis()
    return db, client, StudentService(db, client, ttl=42)


def test_cache_miss_then_hit_and_ttl():
    db, client, service = make_service()
    student, status = service.get_student("SV001")
    assert status == "MISS" and student["name"] == "An"
    assert client.ttls[cache_key("SV001")] == 42
    assert service.get_student("SV001")[1] == "HIT"


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


def test_benchmark_returns_non_negative_milliseconds():
    db, _, service = make_service()
    direct, cached = benchmark(db, service, "SV001", repetitions=3)
    assert direct >= 0 and cached >= 0
