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
        if "Đã đăng xuất" in content:
            initial_state, state_class = "Logged Out", "logged-out"
        elif any(message in content for message in (
                "Đăng nhập thành công", "Đang đăng nhập:", "Truy cập được bảo vệ thành công")):
            initial_state, state_class = "Session Active", "active"
        else:
            initial_state, state_class = "Not Authenticated", "inactive"

        return ("<!doctype html><html lang='vi'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<meta name='color-scheme' content='light'>"
                "<title>Redis Session Storage Demo</title><style>"
                ":root{font-family:Inter,'Segoe UI',Arial,sans-serif;color:#14233b;background:#edf2f8;"
                "--navy:#112744;--blue:#2463eb;--muted:#64748b;--line:#d8e1ed;--white:#fff;"
                "--green:#16804a;--red:#b42335;--amber:#9a5b08}*{box-sizing:border-box}"
                "body{margin:0;min-width:320px}.page{max-width:1180px;margin:0 auto;padding:42px 28px 56px}"
                ".hero{background:linear-gradient(120deg,#10294a,#1b4a76);color:white;border-radius:22px;"
                "padding:32px 38px;margin-bottom:22px;box-shadow:0 14px 36px #15365a22}"
                ".eyebrow{font-size:13px;font-weight:750;letter-spacing:.13em;text-transform:uppercase;color:#a9cdfd}"
                "h1{font-size:clamp(32px,4vw,48px);line-height:1.08;margin:9px 0 8px;letter-spacing:-.03em}"
                ".subtitle{font-size:19px;color:#d6e5f7;margin:0}.layout{display:grid;grid-template-columns:1fr 1fr;"
                "gap:18px}.card{background:var(--white);border:1px solid var(--line);border-radius:18px;"
                "padding:25px;box-shadow:0 8px 24px #1936570b}.card h2{font-size:22px;margin:0 0 18px;color:var(--navy)}"
                ".login{grid-row:span 1}.field{margin:0 0 16px}label{display:block;font-size:16px;"
                "font-weight:700;margin-bottom:7px}input{width:100%;height:52px;border:1px solid #b8c6d8;"
                "border-radius:10px;padding:0 14px;font:inherit;font-size:17px;color:var(--navy);background:#fff}"
                "input:focus{outline:3px solid #2463eb30;border-color:var(--blue)}.actions{display:flex;"
                "gap:10px;flex-wrap:wrap;margin-top:18px}button,.button{min-height:48px;border:0;border-radius:10px;"
                "padding:12px 18px;font:inherit;font-size:16px;font-weight:750;text-decoration:none;cursor:pointer;"
                "display:inline-flex;align-items:center;justify-content:center}.primary{background:var(--blue);color:#fff}"
                ".secondary{background:#eaf0f8;color:#1d3555}.danger{background:#fff0f0;color:#a42632}"
                "button:hover,.button:hover{filter:brightness(.96)}.status-card{display:flex;align-items:center;"
                "gap:13px;border:1px solid var(--line);background:#f7f9fc;border-radius:14px;padding:17px;margin:0 0 14px}"
                ".status-icon{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;flex:none;"
                "background:#e8edf4;color:#506079;font-size:23px;font-weight:800}.badge{display:inline-flex;"
                "border-radius:999px;padding:7px 12px;font-size:15px;font-weight:800;background:#e8edf4;color:#46566c}"
                ".badge.active{background:#dcfce8;color:#11613a}.badge.expired,.badge.logged-out{background:#ffeded;color:#a22635}"
                ".badge.inactive{background:#fff3d8;color:#87530b}.server-message{font-size:17px;line-height:1.5;"
                "color:#33445e;min-height:28px}.server-message p{margin:8px 0}.session-info{display:grid;"
                "grid-template-columns:1fr 1fr;gap:12px;margin:16px 0}.info-item{border:1px solid var(--line);"
                "border-radius:12px;padding:14px;background:#fbfcfe}.info-label{display:block;color:var(--muted);"
                "font-size:13px;font-weight:700;margin-bottom:5px}.info-value{font-size:19px;font-weight:800;"
                "overflow-wrap:anywhere;color:var(--navy)}.session-info[hidden]{display:none}"
                ".hint{font-size:14px;color:var(--muted);line-height:1.5;margin:12px 0 0}"
                ".full{grid-column:1/-1}.section-lead{margin:-8px 0 18px;color:var(--muted);font-size:16px}"
                ".storage-flow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));align-items:stretch;gap:10px}"
                ".flow-node{min-height:82px;display:flex;flex-direction:column;justify-content:center;align-items:center;"
                "text-align:center;gap:7px;border:1px solid #cbd8e8;background:#f7faff;border-radius:13px;"
                "padding:12px;font-size:16px;font-weight:800;color:#1a365d}.flow-node .symbol{font-size:23px;color:var(--blue)}"
                ".flow-arrow{display:none}.explanation{text-align:center;font-size:18px;font-weight:700;color:#31445f;margin:18px 0 0}"
                ".demo-flow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;align-items:center}"
                ".demo-step{border-radius:12px;background:#f0f5fc;border:1px solid #d7e2f0;padding:14px 10px;"
                "text-align:center;font-weight:750;color:#28415f;font-size:15px}.demo-step.active-step{"
                "background:#e5f8ec;border-color:#9bd7b2;color:#12623b}.arrow{text-align:center;color:#7b91ad;font-size:22px}"
                ".logout-flow{margin-top:14px;padding:13px 16px;border-left:4px solid #cc5260;background:#fff5f5;"
                "border-radius:0 10px 10px 0;color:#79323b;font-weight:700}.footer-note{margin:18px 2px 0;color:var(--muted);"
                "font-size:13px;line-height:1.5}form{margin:0}@media(max-width:760px){.page{padding:22px 14px 36px}"
                ".hero{padding:26px 22px}.layout{grid-template-columns:1fr}.full{grid-column:auto}.storage-flow{grid-template-columns:1fr}"
                ".flow-node{min-height:64px}.demo-flow{grid-template-columns:1fr}.arrow{transform:rotate(90deg);height:18px}"
                ".session-info{grid-template-columns:1fr}.card{padding:21px}}"
                "</style></head><body><main class='page'>"
                "<header class='hero'><div class='eyebrow'>SOA seminar · Redis</div>"
                "<h1>Redis Session Storage Demo</h1>"
                "<p class='subtitle'>Server-side session storage with Redis</p></header>"
                "<div class='layout'><section class='card login'><h2>Sign in</h2>"
                f"<form method='post' action='/login'><input type='hidden' name='csrf' value='{escape(token)}'>"
                "<div class='field'><label for='username'>Username</label>"
                "<input id='username' name='username' autocomplete='username' required></div>"
                "<div class='field'><label for='password'>Password</label>"
                "<input id='password' type='password' name='password' autocomplete='current-password' required></div>"
                "<button class='primary' type='submit'>Login</button></form>"
                "<p class='hint'>Your session is stored on the server after successful authentication.</p></section>"
                "<section class='card' aria-live='polite'><h2>Session status</h2>"
                f"<div class='status-card'><div class='status-icon' id='statusIcon'>●</div>"
                f"<span class='badge {state_class}' id='statusBadge'>{initial_state}</span></div>"
                f"<div class='server-message' id='serverMessage'>{content}</div>"
                "<div class='session-info' id='sessionInfo' hidden>"
                "<div class='info-item'><span class='info-label'>Username</span><span class='info-value' id='sessionUser'></span></div>"
                "<div class='info-item'><span class='info-label'>Estimated Redis TTL</span><span class='info-value' id='sessionTtl'></span></div></div>"
                "<p class='hint' id='stateHint' hidden></p>"
                "<div class='actions'><a class='button secondary' href='/status'>Check Session</a>"
                f"<form method='post' action='/logout'><input type='hidden' name='csrf' value='{escape(token)}'>"
                "<button class='danger' type='submit'>Logout</button></form></div></section>"
                "<section class='card full'><h2>How Redis stores a session</h2>"
                "<div class='storage-flow' aria-label='Browser to Redis session storage flow'>"
                "<div class='flow-node'><span class='symbol'>▣</span>Browser</div>"
                "<div class='flow-node'><span class='symbol'>↓</span>Session Cookie</div>"
                "<div class='flow-node'><span class='symbol'>▤</span>Application</div>"
                "<div class='flow-node'><span class='symbol'>↓</span>Redis</div>"
                "<div class='flow-node'><span class='symbol'>◷</span>Session Data + TTL</div></div>"
                "<p class='explanation'>Browser keeps a session reference, while Redis stores the server-side session state.</p></section>"
                "<section class='card full'><h2>Demo flow</h2>"
                "<div class='demo-flow'><div class='demo-step'>Login</div><div class='arrow' aria-hidden='true'>→</div>"
                "<div class='demo-step'>Session Active<br>Redis stores session</div><div class='arrow' aria-hidden='true'>→</div>"
                "<div class='demo-step'>TTL countdown<br>Session Expired</div></div>"
                "<div class='logout-flow'>Logout → Session invalidated</div></section></div>"
                "<p class='footer-note'>The session cookie is an HttpOnly reference. The session ID and password are never displayed in this page.</p>"
                "</main><script>"
                "(()=>{const message=document.getElementById('serverMessage').innerText.trim();"
                "const badge=document.getElementById('statusBadge'),icon=document.getElementById('statusIcon');"
                "const info=document.getElementById('sessionInfo'),user=document.getElementById('sessionUser'),ttl=document.getElementById('sessionTtl');"
                "const hint=document.getElementById('stateHint');"
                "const key='redis-session-demo-active';let label='Not Authenticated',state='inactive';"
                "const active=/Đăng nhập thành công|Đang đăng nhập:|Truy cập được bảo vệ thành công/.test(message);"
                "const loggedOut=/Đã đăng xuất/.test(message);"
                "const inactiveResponse=/Chưa đăng nhập hoặc|Cần đăng nhập;/.test(message);"
                "if(active){label='Session Active';state='active';sessionStorage.setItem(key,'1')}"
                "else if(loggedOut){label='Logged Out';state='logged-out';sessionStorage.removeItem(key)}"
                "else if(inactiveResponse&&sessionStorage.getItem(key)){label='Session Expired';state='expired';sessionStorage.removeItem(key)}"
                "badge.textContent=label;badge.className='badge '+state;"
                "if(state==='active'){hint.textContent='TTL counts down from the last Redis check. Use Check Session to confirm the current server-side state.';hint.hidden=false}"
                "else if(state==='expired'){hint.textContent='This tab previously observed an active session; the server now reports no valid session. Check Session again to confirm.';hint.hidden=false}"
                "else if(state==='inactive'){hint.textContent='The server reports no authenticated session. Its current response cannot distinguish a first visit from a session that expired in another tab.';hint.hidden=false}"
                "icon.textContent=state==='active'?'✓':state==='expired'||state==='logged-out'?'!':'○';"
                "const match=message.match(/Đang đăng nhập:\\s*(.*); TTL còn (\\d+) giây\\./);"
                "if(match){user.textContent=match[1];ttl.textContent=match[2]+' seconds';info.hidden=false;"
                "let remaining=Number(match[2]);const timer=setInterval(()=>{remaining=Math.max(0,remaining-1);"
                "ttl.textContent=remaining+' seconds';if(remaining===0)clearInterval(timer)},1000)}"
                "})();</script></body></html>")

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
