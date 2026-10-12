"""Loopback-only visual dashboard for the existing Redis student cache service."""

import json
import re
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

import redis

from src import database
from src.cache import StudentService, cache_key, create_redis_client

STUDENT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
MAX_BODY_BYTES = 1024
ALLOWED_HOSTS = {"127.0.0.1:5001", "127.0.0.1"}
ALLOWED_ORIGIN = "http://127.0.0.1:5001"

PAGE = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Redis Cache Dashboard</title><style>
:root{font-family:Inter,"Segoe UI",Arial,sans-serif;color:#17243b;background:#f3f6fb;--blue:#1d4ed8;--muted:#61718a;--line:#dbe3ef}
*{box-sizing:border-box}body{margin:0}.shell{max-width:1200px;margin:auto;padding:32px 24px 48px}.top{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:24px}.eyebrow{color:#1d4ed8;font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:12px}h1{font-size:clamp(30px,4vw,44px);margin:5px 0}.sub{color:var(--muted);margin:0}.card{background:white;border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 8px 26px #20365d0a}.grid{display:grid;grid-template-columns:1.05fr .95fr;gap:18px}.lookup{grid-column:1/-1}.row{display:flex;gap:12px;align-items:end}.field{flex:1}label{display:block;font-weight:700;margin:0 0 8px}input{width:100%;height:48px;border:1px solid #bdc9da;border-radius:10px;padding:0 14px;font-size:17px}button{border:0;border-radius:10px;padding:13px 18px;background:var(--blue);color:white;font-weight:700;font-size:15px;cursor:pointer}button.secondary{background:#e8eef8;color:#193354}button:disabled{opacity:.55;cursor:wait}.statusline{display:flex;justify-content:space-between;align-items:center;margin:22px 0 0;gap:10px;flex-wrap:wrap}.badge{display:inline-flex;border-radius:999px;padding:8px 14px;font-weight:800;font-size:14px;background:#e8edf4;color:#506079}.badge.HIT{background:#dcfce7;color:#166534}.badge.MISS{background:#ffedd5;color:#9a3412}.badge.BYPASS,.badge.ERROR{background:#fee2e2;color:#991b1b}.muted{color:var(--muted)}.result{margin-top:16px;min-height:56px}.student{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:0}.student div{background:#f7f9fc;padding:12px;border-radius:10px}.student dt{font-size:12px;color:var(--muted);margin-bottom:4px}.student dd{margin:0;font-weight:650;overflow-wrap:anywhere}.meta{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:16px}.meta div{border-top:1px solid var(--line);padding-top:10px}.meta strong{display:block;font-size:12px;color:var(--muted);margin-bottom:5px}.key{font-family:Consolas,monospace;overflow-wrap:anywhere}.flow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:16px}.node{border:2px solid var(--line);border-radius:12px;padding:12px 10px;text-align:center;background:#fff;min-height:74px;display:grid;place-items:center;font-weight:700;font-size:13px}.node.done{border-color:#22a35a;background:#effdf4}.node.warn{border-color:#e69a24;background:#fff8e9}.node.fail{border-color:#dc4545;background:#fff1f1}.flow-note{font-size:12px;color:var(--muted);margin-top:10px}.events{list-style:none;padding:0;margin:12px 0 0;max-height:330px;overflow:auto}.events li{display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #edf1f6;font-size:14px}.dot{width:9px;height:9px;border-radius:50%;background:#7b8ba3;margin-top:5px;flex:none}.dot.success{background:#20a05a}.dot.warning{background:#e39b21}.dot.error{background:#d83c3c}.actions{display:flex;gap:8px;flex-wrap:wrap}.toast{color:#991b1b;margin-top:12px;min-height:20px}.loading{color:var(--muted);font-weight:600}.sr{position:absolute;left:-10000px}@media(max-width:760px){.shell{padding:22px 14px}.grid{grid-template-columns:1fr}.lookup{grid-column:auto}.row{align-items:stretch;flex-direction:column}.meta{grid-template-columns:1fr}.flow{grid-template-columns:repeat(2,1fr)}.top{align-items:flex-start;flex-direction:column}}
</style></head><body><main class="shell">
<header class="top"><div><div class="eyebrow">Seminar · Service Oriented Architecture</div><h1>Redis Cache Dashboard</h1><p class="sub">Quan sát trực tiếp đường đi của một lần tra cứu sinh viên.</p></div>
<button class="secondary" id="refresh">Làm mới trạng thái</button></header>
<div class="grid"><section class="card lookup"><h2>Tra cứu sinh viên</h2><form id="lookupForm"><div class="row"><div class="field"><label for="studentId">Mã số sinh viên (MSSV)</label><input id="studentId" name="student_id" maxlength="32" pattern="[A-Za-z0-9_-]{1,32}" placeholder="Ví dụ: SV001" autocomplete="off" required></div><button id="lookupButton" type="submit">Tra cứu</button></div></form>
<div class="statusline"><div><span class="muted">Trạng thái lần tra cứu</span> <span class="badge" id="lookupStatus">Chưa tra cứu</span></div><span class="muted" id="loading" aria-live="polite"></span></div><div id="result" class="result" aria-live="polite"><p class="muted">Nhập MSSV để xem kết quả thật từ SQLite hoặc Redis.</p></div><div class="meta"><div><strong>Nguồn dữ liệu lần này</strong><span id="source">—</span></div><div><strong>Redis key thực tế</strong><span id="key" class="key">—</span></div><div><strong>TTL còn lại</strong><span id="ttl">Chưa đọc</span></div></div><p class="toast" id="error" role="alert"></p></section>
<section class="card"><h2>Luồng xử lý</h2><p class="muted">MSSV → Redis → HIT: trả cache · MISS: SQLite → ghi cache → trả kết quả · Redis lỗi: BYPASS → SQLite.</p><div class="flow" id="flow"><div class="node" data-node="input">1 · Nhập MSSV</div><div class="node" data-node="redis">2 · Kiểm tra Redis</div><div class="node" data-node="hit">HIT · Trả từ Redis</div><div class="node" data-node="miss">MISS · Chưa có cache</div><div class="node" data-node="bypass">BYPASS · Redis lỗi</div><div class="node" data-node="sqlite">3 · Đọc SQLite</div><div class="node" data-node="write">4 · Ghi cache có TTL</div><div class="node" data-node="output">5 · Trả kết quả</div></div><p class="flow-note">Màu xanh: bước đã xác nhận thành công · cam: nhánh không có dữ liệu/TTL · đỏ: bước thất bại. Các bước chưa chạy giữ màu trung tính.</p></section>
<section class="card"><h2>Redis và thao tác cache</h2><p>Trạng thái kết nối: <span class="badge" id="redisStatus">Chưa kiểm tra</span></p><div class="actions"><button class="secondary" id="ttlButton">Kiểm tra TTL</button><button class="secondary" id="deleteButton">Xóa cache của MSSV này</button></div><p class="muted">Chỉ thao tác trên key đúng bằng MSSV đang nhập; không xóa key khác.</p></section>
<section class="card"><h2>Nhật ký sự kiện</h2><p class="muted">Chỉ hiện bước mà ứng dụng xác nhận đã thực hiện.</p><ul class="events" id="events"><li class="muted">Chưa có sự kiện.</li></ul></section></div></main>
<script>
const $=id=>document.getElementById(id), form=$('lookupForm');let busy=false;
function setBusy(v){busy=v;$('lookupButton').disabled=v;$('loading').textContent=v?'Đang tra cứu…':''}
function clearFlow(){document.querySelectorAll('.node').forEach(n=>n.className='node')}
function mark(id,state){const n=document.querySelector(`[data-node="${id}"]`);if(n)n.classList.add(state==='error'?'fail':state==='warning'?'warn':'done')}
function showEvents(events){const ul=$('events');ul.replaceChildren();if(!events.length){ul.textContent='Chưa có sự kiện.';return}for(const e of events){const li=document.createElement('li'),dot=document.createElement('i'),span=document.createElement('span');dot.className='dot '+e.state;span.textContent=e.message;li.append(dot,span);ul.append(li);const route={lookup_started:'input',redis_check:'redis',redis_hit:'hit',redis_miss:'miss',cache_invalid:'miss',redis_error:'bypass',sqlite_read:'sqlite',sqlite_found:'sqlite',sqlite_not_found:'sqlite',cache_write:'write',ttl_read:'write',result_return:'output',database_error:'output'};if(route[e.stage])mark(route[e.stage],e.state);if(e.stage==='database_error')mark('sqlite','error')}}
function showStudent(s,status){const box=$('result');box.replaceChildren();if(!s){const p=document.createElement('p');p.className='muted';p.textContent=status==='ERROR'?'Không thể lấy kết quả hợp lệ.':status==='MISS'||status==='BYPASS'?'Không tìm thấy sinh viên trong SQLite.':'Không có hồ sơ để hiển thị.';box.append(p);return}const dl=document.createElement('dl');dl.className='student';for(const [label,value] of [['MSSV',s.student_id],['Họ tên',s.name],['Email',s.email],['Ngành',s.major]]){const wrap=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;wrap.append(dt,dd);dl.append(wrap)}box.append(dl)}
function showTtl(data){$('ttl').textContent=data.status==='available'?`${data.ttl_seconds} giây`:data.status==='no_expiry'?'Key không có thời hạn':data.status==='key_missing'?'Key không tồn tại':data.status==='unavailable'?'Không đọc được (Redis lỗi)':'Chưa kiểm tra TTL'}
async function api(url,options={}){const response=await fetch(url,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});const data=await response.json();if(!response.ok)throw new Error(data.error||'Yêu cầu thất bại.');return data}
function id(){return $('studentId').value.trim()}
form.addEventListener('submit',async e=>{e.preventDefault();if(busy||!validId())return;clearFlow();$('error').textContent='';$('source').textContent='—';$('key').textContent='—';$('ttl').textContent='Đang xử lý';setBusy(true);try{const d=await api('/api/lookup',{method:'POST',body:JSON.stringify({student_id:id()})});$('lookupStatus').textContent=d.status;$('lookupStatus').className='badge '+d.status;$('source').textContent=d.source||'Không có kết quả';$('key').textContent=d.redis_key;showTtl(d.ttl);showStudent(d.student,d.status);showEvents(d.events);if(d.redis_state==='connected')$('redisStatus').textContent='Đang hoạt động';else if(d.redis_state==='unavailable')$('redisStatus').textContent='Không khả dụng';}catch(err){$('lookupStatus').textContent='ERROR';$('lookupStatus').className='badge ERROR';$('source').textContent='Không có kết quả';$('ttl').textContent='Không khả dụng';$('result').textContent='Không thể hoàn tất tra cứu.';$('error').textContent=err.message;mark('output','error');showEvents([{stage:'database_error',state:'error',message:'Không thể hoàn tất tra cứu.'}])}finally{setBusy(false)}});
$('refresh').addEventListener('click',async()=>{try{const d=await api('/api/status');$('redisStatus').textContent=d.connected?'Đang hoạt động':'Không khả dụng';$('redisStatus').className='badge '+(d.connected?'HIT':'ERROR');addEvent({state:d.connected?'success':'error',message:d.connected?'Redis phản hồi PING.':'Redis không phản hồi PING.'});$('error').textContent=''}catch(e){$('redisStatus').textContent='Không thể kiểm tra';$('redisStatus').className='badge ERROR';$('error').textContent=e.message}});
$('ttlButton').addEventListener('click',async()=>{if(!validId())return;try{const d=await api('/api/ttl?student_id='+encodeURIComponent(id()));showTtl(d);addEvent(d.event);$('redisStatus').textContent=d.redis_connected?'Đang hoạt động':'Không khả dụng';$('redisStatus').className='badge '+(d.redis_connected?'HIT':'ERROR')}catch(e){$('error').textContent=e.message}});
$('deleteButton').addEventListener('click',async()=>{if(!validId())return;try{const d=await api('/api/cache/delete',{method:'POST',body:JSON.stringify({student_id:id()})});addEvent(d.event);$('error').textContent=d.message;$('error').style.color=d.deleted===null?'#991b1b':'#166534';if(d.deleted!==null){$('ttl').textContent='Key không tồn tại';$('redisStatus').textContent='Đang hoạt động';$('redisStatus').className='badge HIT'}else{$('redisStatus').textContent='Không khả dụng';$('redisStatus').className='badge ERROR'}}catch(e){$('error').textContent=e.message}});
function validId(){if(!/^[A-Za-z0-9_-]{1,32}$/.test(id())){$('error').textContent='MSSV chỉ được gồm chữ cái, số, dấu gạch ngang hoặc gạch dưới (1–32 ký tự).';$('studentId').focus();return false}$('error').textContent='';return true}
function addEvent(e){const ul=$('events');if(ul.firstElementChild?.classList.contains('muted'))ul.replaceChildren();const li=document.createElement('li'),dot=document.createElement('i'),span=document.createElement('span');dot.className='dot '+e.state;span.textContent=e.message;li.append(dot,span);ul.prepend(li)}
$('studentId').addEventListener('input',()=>{if($('studentId').value.trim())validId()});
</script></body></html>"""


def valid_student_id(value):
    return isinstance(value, str) and STUDENT_ID_RE.fullmatch(value) is not None


class CacheDashboard:
    def __init__(self, database_module=None, redis_client=None, service=None):
        self.database = database_module if database_module is not None else database
        self.redis = redis_client if redis_client is not None else create_redis_client()
        self.service = service if service is not None else StudentService(self.database, self.redis)

    @staticmethod
    def _response(start_response, status, payload, content_type="application/json; charset=utf-8"):
        body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY")])
        return [body]

    @staticmethod
    def _json_body(environ):
        if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ValueError("Content-Type must be application/json")
        length = int(environ.get("CONTENT_LENGTH") or 0)
        if length < 1 or length > MAX_BODY_BYTES:
            raise ValueError("Request body size is invalid")
        return json.loads(environ["wsgi.input"].read(length).decode("utf-8"))

    @staticmethod
    def _ttl_result(client, key):
        try:
            ttl = client.ttl(key)
        except redis.RedisError:
            return {"redis_connected": False, "status": "unavailable", "ttl_seconds": None,
                    "event": {"stage": "ttl_read", "state": "error", "message": "Không đọc được TTL vì Redis không khả dụng."}}
        if ttl == -2:
            status, message = "key_missing", "Redis xác nhận key không tồn tại (TTL = -2)."
        elif ttl == -1:
            status, message = "no_expiry", "Redis xác nhận key tồn tại nhưng không có thời hạn (TTL = -1)."
        else:
            status, message = "available", f"Redis xác nhận TTL còn {ttl} giây."
        return {"redis_connected": True, "status": status, "ttl_seconds": ttl if ttl >= 0 else None,
                "event": {"stage": "ttl_read", "state": "success" if ttl >= 0 else "warning", "message": message}}

    def __call__(self, environ, start_response):
        host = environ.get("HTTP_HOST")
        origin = environ.get("HTTP_ORIGIN")
        if (host and host.lower() not in ALLOWED_HOSTS) or (origin and origin != ALLOWED_ORIGIN):
            return self._response(start_response, "403 Forbidden", {"error": "Yêu cầu từ host không được phép."})
        method, path = environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/")
        if method == "GET" and path == "/":
            return self._response(start_response, "200 OK", PAGE, "text/html; charset=utf-8")
        if method == "GET" and path == "/api/status":
            try:
                self.redis.ping()
                return self._response(start_response, "200 OK", {"connected": True})
            except redis.RedisError:
                return self._response(start_response, "200 OK", {"connected": False})
        if method == "GET" and path == "/api/ttl":
            sid = parse_qs(environ.get("QUERY_STRING", "")).get("student_id", [""])[0]
            if not valid_student_id(sid):
                return self._response(start_response, "400 Bad Request", {"error": "MSSV không hợp lệ (1–32 ký tự chữ, số, _ hoặc -)."})
            return self._response(start_response, "200 OK", self._ttl_result(self.redis, cache_key(sid, self.service.key_prefix)))
        if method == "POST" and path in ("/api/lookup", "/api/cache/delete"):
            try:
                data = self._json_body(environ)
                sid = data.get("student_id") if isinstance(data, dict) else None
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                return self._response(start_response, "400 Bad Request", {"error": "Yêu cầu không hợp lệ."})
            if not valid_student_id(sid):
                return self._response(start_response, "400 Bad Request", {"error": "MSSV không hợp lệ (1–32 ký tự chữ, số, _ hoặc -)."})
            if path == "/api/cache/delete":
                success = self.service.invalidate(sid)
                if not success:
                    message = "Redis không khả dụng; không xóa được cache."
                    return self._response(start_response, "200 OK", {"deleted": None, "message": message,
                        "event": {"stage": "redis_error", "state": "error", "message": message}})
                deleted = bool(self.service.last_invalidation_deleted)
                message = "Đã xóa key cache đúng MSSV." if deleted else "Redis xác nhận key không tồn tại; không có key nào bị xóa."
                return self._response(start_response, "200 OK", {"deleted": deleted, "message": message,
                    "redis_key": cache_key(sid, self.service.key_prefix), "event": {"stage": "cache_delete", "state": "success" if deleted else "warning", "message": message}})
            try:
                student, status = self.service.get_student(sid)
            except Exception:
                trace = self.service.last_lookup
                return self._response(start_response, "200 OK", {"student": None, "status": "ERROR", "source": None,
                    "redis_key": trace.get("key", cache_key(sid, self.service.key_prefix)),
                    "ttl": {"status": "unavailable", "ttl_seconds": None}, "redis_state": trace.get("redis_state"),
                    "events": trace.get("events", [])})
            trace = self.service.last_lookup
            return self._response(start_response, "200 OK", {"student": student, "status": status,
                "source": trace.get("source"), "redis_key": trace.get("key"),
                "ttl": {"status": trace.get("ttl_status", "not_checked"), "ttl_seconds": trace.get("ttl")},
                "redis_state": trace.get("redis_state"), "cache_write": trace.get("cache_write"),
                "events": trace.get("events", [])})
        return self._response(start_response, "404 Not Found", {"error": "Không tìm thấy endpoint."})


def main():
    client = create_redis_client()
    print("Redis Cache Dashboard: http://127.0.0.1:5001 (chỉ truy cập từ máy này)")
    with make_server("127.0.0.1", 5001, CacheDashboard(redis_client=client)) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
