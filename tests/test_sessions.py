import io
import json
import re
import time

from src.session_demo import CSRF_COOKIE, SESSION_COOKIE, SessionDemo
from src.sessions import SessionStore


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expiry = {}

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.expiry[key] = time.time() + ttl

    def get(self, key):
        if key in self.expiry and self.expiry[key] <= time.time():
            self.delete(key)
        return self.values.get(key)

    def ttl(self, key):
        if self.get(key) is None:
            return -2
        return max(0, int(self.expiry[key] - time.time()))

    def delete(self, key):
        existed = key in self.values
        self.values.pop(key, None)
        self.expiry.pop(key, None)
        return int(existed)


def request(app, method="GET", path="/", data=None, cookie="", scheme="http"):
    body = (data or "").encode()
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "CONTENT_LENGTH": str(len(body)),
               "CONTENT_TYPE": "application/x-www-form-urlencoded", "HTTP_COOKIE": cookie,
               "wsgi.input": io.BytesIO(body), "wsgi.url_scheme": scheme}
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    response = b"".join(app(environ, start_response)).decode()
    return captured["status"], captured["headers"], response


def cookie_value(headers, name):
    value = next(h[1] for h in headers if h[0].lower() == "set-cookie" and h[1].startswith(name + "="))
    return value.split(";", 1)[0].split("=", 1)[1]


def csrf_from_page(body):
    return re.search(r"name='csrf' value='([^']+)'", body).group(1)


def test_session_login_status_protected_expiration_and_logout():
    client = FakeRedis()
    app = SessionDemo(client, ttl=1)
    status, headers, body = request(app)
    assert status == "200 OK" and "Chưa đăng nhập" in body
    csrf = cookie_value(headers, CSRF_COOKIE)
    status, headers, body = request(app, "POST", "/login", f"csrf={csrf}&username=demo&password=redis123", f"{CSRF_COOKIE}={csrf}")
    assert status == "200 OK" and "Đăng nhập thành công" in body
    sid = cookie_value(headers, SESSION_COOKIE)
    session_cookie = next(h[1] for h in headers if h[0].lower() == "set-cookie" and h[1].startswith(SESSION_COOKIE + "="))
    assert "HttpOnly" in session_cookie and "SameSite=Lax" in session_cookie
    assert SessionStore(client, 1).get(sid) == {"username": "demo"}
    cookie = f"{CSRF_COOKIE}={csrf}; {SESSION_COOKIE}={sid}"
    assert request(app, "POST", "/protected", f"csrf={csrf}", cookie)[0] == "200 OK"
    time.sleep(1.05)
    assert request(app, "POST", "/protected", f"csrf={csrf}", cookie)[0] == "401 Unauthorized"
    assert "hết hạn" in request(app, "GET", "/status", cookie=cookie)[2]

    # Login again and explicitly revoke the server-side record on logout.
    _, headers, _ = request(app, "POST", "/login", f"csrf={csrf}&username=demo&password=redis123", f"{CSRF_COOKIE}={csrf}")
    sid = cookie_value(headers, SESSION_COOKIE)
    cookie = f"{CSRF_COOKIE}={csrf}; {SESSION_COOKIE}={sid}"
    status, headers, body = request(app, "POST", "/logout", f"csrf={csrf}", cookie)
    assert status == "200 OK" and "không còn hợp lệ" in body
    assert SessionStore(client, 1).get(sid) is None
    assert request(app, "POST", "/protected", f"csrf={csrf}", cookie)[0] == "401 Unauthorized"


def test_session_cookie_is_secure_when_wsgi_uses_https():
    app = SessionDemo(FakeRedis(), ttl=30)
    _, headers, _ = request(app, scheme="https")
    csrf = cookie_value(headers, CSRF_COOKIE)
    _, headers, _ = request(app, "POST", "/login", f"csrf={csrf}&username=demo&password=redis123",
                            f"{CSRF_COOKIE}={csrf}", scheme="https")
    session_cookie = next(h[1] for h in headers if h[0].lower() == "set-cookie" and h[1].startswith(SESSION_COOKIE + "="))
    assert "Secure" in session_cookie and "HttpOnly" in session_cookie and "SameSite=Lax" in session_cookie


def test_session_rejects_bad_credentials_and_csrf():
    app = SessionDemo(FakeRedis(), ttl=30)
    _, headers, body = request(app)
    csrf = cookie_value(headers, CSRF_COOKIE)
    assert request(app, "POST", "/login", "csrf=no&username=demo&password=bad", f"{CSRF_COOKIE}={csrf}")[0] == "403 Forbidden"
    assert "không đúng" in request(app, "POST", "/login", f"csrf={csrf}&username=demo&password=bad", f"{CSRF_COOKIE}={csrf}")[2]
