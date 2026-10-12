import io
import json

import redis

from src.cache_dashboard import CacheDashboard


class FakeDatabase:
    def __init__(self, fail=False):
        self.students = {"SV001": {"student_id": "SV001", "name": "An", "email": "an@example.edu", "major": "CS"}}
        self.fail = fail

    def get_student(self, sid):
        if self.fail:
            raise RuntimeError("secret sqlite connection string")
        return self.students.get(sid)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.offline = False

    def _check(self):
        if self.offline:
            raise redis.ConnectionError("private redis host details")

    def ping(self):
        self._check()
        return True

    def get(self, key):
        self._check()
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self._check()
        self.values[key] = value
        self.ttls[key] = ttl

    def ttl(self, key):
        self._check()
        return self.ttls.get(key, -2)

    def delete(self, key):
        self._check()
        self.ttls.pop(key, None)
        return int(self.values.pop(key, None) is not None)


def request(app, method="GET", path="/", payload=None, query="", host="127.0.0.1:5001"):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(body)),
               "HTTP_HOST": host, "wsgi.input": io.BytesIO(body)}
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = headers

    raw = b"".join(app(environ, start_response)).decode("utf-8")
    response["body"] = json.loads(raw) if "application/json" in dict(response["headers"]).get("Content-Type", "") else raw
    return response


def test_first_lookup_miss_then_hit_reports_real_source_and_ttl():
    db, client = FakeDatabase(), FakeRedis()
    app = CacheDashboard(db, client)
    miss = request(app, "POST", "/api/lookup", {"student_id": "SV001"})["body"]
    assert miss["status"] == "MISS" and miss["source"] == "SQLite"
    assert miss["redis_key"] == "student:SV001" and miss["ttl"]["status"] == "available"
    assert miss["ttl"]["ttl_seconds"] == 60
    assert "cache_write" in [event["stage"] for event in miss["events"]]

    hit = request(app, "POST", "/api/lookup", {"student_id": "SV001"})["body"]
    assert hit["status"] == "HIT" and hit["source"] == "Redis"
    assert hit["student"] == db.students["SV001"]
    assert hit["ttl"]["ttl_seconds"] == client.ttls["student:SV001"]

    missing = request(app, "POST", "/api/lookup", {"student_id": "SV999"})["body"]
    assert missing["status"] == "MISS" and missing["source"] == "SQLite"
    assert missing["ttl"]["status"] == "key_missing"


def test_ttl_endpoint_distinguishes_real_ttl_missing_key_and_no_expiry():
    client = FakeRedis()
    app = CacheDashboard(FakeDatabase(), client)
    client.values["student:SV001"] = "{}"
    client.ttls["student:SV001"] = 17
    ttl = request(app, "GET", "/api/ttl", query="student_id=SV001")["body"]
    assert ttl["status"] == "available" and ttl["ttl_seconds"] == 17
    assert request(app, "GET", "/api/ttl", query="student_id=UNKNOWN")["body"]["status"] == "key_missing"
    client.ttls["student:SV001"] = -1
    assert request(app, "GET", "/api/ttl", query="student_id=SV001")["body"]["status"] == "no_expiry"


def test_delete_removes_only_the_student_key():
    client = FakeRedis()
    client.values.update({"student:SV001": "{}", "unrelated:key": "keep"})
    app = CacheDashboard(FakeDatabase(), client)
    result = request(app, "POST", "/api/cache/delete", {"student_id": "SV001"})["body"]
    assert result["deleted"] is True
    assert "student:SV001" not in client.values
    assert client.values["unrelated:key"] == "keep"


def test_redis_failure_is_bypass_and_reports_sqlite_source():
    client = FakeRedis()
    client.offline = True
    app = CacheDashboard(FakeDatabase(), client)
    result = request(app, "POST", "/api/lookup", {"student_id": "SV001"})["body"]
    assert result["status"] == "BYPASS" and result["source"] == "SQLite"
    assert result["student"]["student_id"] == "SV001"
    assert any(event["stage"] == "redis_error" for event in result["events"])
    assert request(app, "GET", "/api/status")["body"]["connected"] is False


def test_not_found_invalid_input_and_internal_error_are_safe():
    app = CacheDashboard(FakeDatabase(), FakeRedis())
    missing = request(app, "POST", "/api/lookup", {"student_id": "SV999"})["body"]
    assert missing["status"] == "MISS" and missing["source"] == "SQLite" and missing["student"] is None
    invalid = request(app, "POST", "/api/lookup", {"student_id": "../../private"})
    assert invalid["status"] == "400 Bad Request"
    broken = CacheDashboard(FakeDatabase(fail=True), FakeRedis())
    error = request(broken, "POST", "/api/lookup", {"student_id": "SV001"})["body"]
    assert error["status"] == "ERROR" and error["source"] is None
    assert "secret sqlite" not in json.dumps(error)


def test_dashboard_rejects_non_loopback_host():
    result = request(CacheDashboard(FakeDatabase(), FakeRedis()), host="example.com")
    assert result["status"] == "403 Forbidden"
