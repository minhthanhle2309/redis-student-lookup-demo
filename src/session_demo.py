"""Small standard-library web demonstration of Redis-backed sessions."""

from http import cookies
from html import escape
import secrets
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

import redis

from src.cache import create_redis_client
from src.sessions import SessionStore, verify_demo_credentials

SESSION_COOKIE = "seminar_session"
CSRF_COOKIE = "seminar_csrf"


class SessionDemo:
    def __init__(self, redis_client, ttl=None):
        self.redis = redis_client
        self.store = SessionStore(redis_client, ttl)

    @staticmethod
    def _cookie(environ, name):
        jar = cookies.SimpleCookie()
        try:
            jar.load(environ.get("HTTP_COOKIE", ""))
            return jar[name].value if name in jar else ""
        except cookies.CookieError:
            return ""

    @staticmethod
    def _set_cookie(name, value, secure=False, max_age=None, http_only=True):
        parts = [f"{name}={value}", "Path=/", "SameSite=Lax"]
        if http_only:
            parts.append("HttpOnly")
        if secure:
            parts.append("Secure")
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        return "; ".join(parts)

    @staticmethod
    def _page(content, token):
        return ("<!doctype html><html lang='vi'><meta charset='utf-8'><title>Redis Session Demo</title>"
                "<h1>Redis Session Demo</h1>" + content +
                f"<form method='post' action='/login'><input type='hidden' name='csrf' value='{escape(token)}'>"
                "<label>Tên đăng nhập <input name='username' autocomplete='username'></label>"
                "<label>Mật khẩu <input type='password' name='password' autocomplete='current-password'></label>"
                "<button>Đăng nhập</button></form>"
                f"<form method='post' action='/protected'><input type='hidden' name='csrf' value='{escape(token)}'>"
                "<button>Truy cập trang được bảo vệ</button></form>"
                f"<form method='post' action='/logout'><input type='hidden' name='csrf' value='{escape(token)}'>"
                "<button>Đăng xuất</button></form></html>")

    def __call__(self, environ, start_response):
        method, path = environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/")
        secure = environ.get("wsgi.url_scheme") == "https"
        session_id = self._cookie(environ, SESSION_COOKIE)
        csrf_cookie = self._cookie(environ, CSRF_COOKIE)
        headers = [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store")]
        if not csrf_cookie:
            csrf_cookie = secrets.token_urlsafe(24)
            headers.append(("Set-Cookie", self._set_cookie(CSRF_COOKIE, csrf_cookie, secure, http_only=False)))

        try:
            raw_length = int(environ.get("CONTENT_LENGTH") or 0)
            form = parse_qs(environ["wsgi.input"].read(raw_length).decode("utf-8")) if method == "POST" else {}
            token = form.get("csrf", [""])[0]
            if method == "POST" and (not csrf_cookie or not secrets.compare_digest(token, csrf_cookie)):
                status, content = "403 Forbidden", "<p>CSRF token không hợp lệ.</p>"
            elif method == "POST" and path == "/login":
                username = form.get("username", [""])[0]
                password = form.get("password", [""])[0]
                if verify_demo_credentials(username, password):
                    session_id = self.store.create(username)
                    headers.append(("Set-Cookie", self._set_cookie(SESSION_COOKIE, session_id, secure)))
                    status, content = "200 OK", "<p>Đăng nhập thành công. Phiên được lưu trong Redis.</p>"
                else:
                    status, content = "401 Unauthorized", "<p>Thông tin đăng nhập không đúng.</p>"
            elif method == "POST" and path == "/logout":
                self.store.delete(session_id)
                session_id = ""
                headers.append(("Set-Cookie", self._set_cookie(SESSION_COOKIE, "", secure, max_age=0)))
                status, content = "200 OK", "<p>Đã đăng xuất; phiên không còn hợp lệ.</p>"
            elif method == "POST" and path == "/protected":
                state = self.store.get(session_id)
                status, content = (("200 OK", "<p>Truy cập được bảo vệ thành công.</p>") if state else
                                   ("401 Unauthorized", "<p>Cần đăng nhập; phiên không tồn tại hoặc đã hết hạn.</p>"))
            elif method == "GET" and path in ("/", "/status"):
                state = self.store.get(session_id)
                if state:
                    remaining = self.store.ttl_remaining(session_id)
                    status_text = f"Đang đăng nhập: {escape(state['username'])}; TTL còn {remaining} giây."
                else:
                    status_text = "Chưa đăng nhập hoặc phiên đã hết hạn; Redis không còn phiên hợp lệ."
                status, content = "200 OK", f"<p>{status_text}</p>"
            else:
                status, content = "404 Not Found", "<p>Không tìm thấy trang.</p>"
            body = self._page(content, csrf_cookie).encode("utf-8")
        except redis.RedisError:
            status, body = "503 Service Unavailable", b"Redis khong kha dung; demo khong chap nhan dang nhap offline."
        except (ValueError, UnicodeDecodeError):
            status, body = "400 Bad Request", b"Yeu cau khong hop le."
        start_response(status, headers + [("Content-Length", str(len(body)))])
        return [body]
def main():
    client = create_redis_client()
    client.ping()
    store = SessionStore(client)
    print(f"Session demo: http://127.0.0.1:5000 (TTL {store.ttl}s). HTTP local không mã hóa dữ liệu truyền tải; chỉ dùng trong lớp.")
    with make_server("127.0.0.1", 5000, SessionDemo(client, store.ttl)) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
