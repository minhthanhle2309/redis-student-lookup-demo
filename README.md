# Redis Student Lookup Demo

Project minh họa Redis trong seminar môn **Kiến trúc Hướng Dịch Vụ (SOA)**. Project giữ hồ sơ sinh viên trong SQLite, dùng Redis làm cache tra cứu và lưu session phía server; đồng thời có dashboard để quan sát luồng cache, demo session và hai loại benchmark độc lập.

Mục tiêu học tập:

- Nhìn thấy cache-aside qua các trạng thái `MISS`, `HIT` và `BYPASS`.
- Quan sát TTL, cache invalidation và dữ liệu nguồn SQLite.
- Phân biệt session ID trong cookie với session data lưu ở Redis.
- So sánh một workload xử lý có/không có cache trên Redis và Memcached.
- Đọc benchmark có giới hạn đo rõ ràng, không suy luận rằng một cache luôn nhanh hơn cache khác.

## Nội dung

- [Kiến trúc](#kiến-trúc)
- [Technology stack và dependencies](#technology-stack-và-dependencies)
- [Setup từ đầu trên Windows](#setup-từ-đầu-trên-windows)
- [Docker và Docker Compose](#docker-và-docker-compose)
- [Redis Student Lookup CLI](#redis-student-lookup-cli)
- [Cache Dashboard](#cache-dashboard)
- [Session Storage Demo](#session-storage-demo)
- [Memcached Demo](#memcached-demo)
- [Cache Performance Lab](#cache-performance-lab)
- [Benchmark SQLite và Redis](#benchmark-sqlite-và-redis)
- [Benchmark Results](#benchmark-results)
- [Troubleshooting](#troubleshooting)
- [Seminar Demo Flow](#seminar-demo-flow)
- [Commands Cheat Sheet](#commands-cheat-sheet)

## Kiến trúc

```text
Người dùng
  ├─ Python CLI ───────────────┐
  ├─ Cache Dashboard :5001 ─────┼──> StudentService ──> Redis :6379
  │                              │       │                cache student:<MSSV>, TTL
  │                              └───────┴──> SQLite data/students.db
  │
  ├─ Session Demo :5000 ───────────────────> Redis :6379
  │                                           seminar:session:<session-id>
  │
  └─ Cache Performance Lab ──> NO CACHE / Redis / Memcached :11211
       tạo payload + SHA-256       lưu digest vào cache

Docker Compose khởi chạy các service Redis và Memcached trên loopback của máy.
```

| Thành phần | Vai trò trong project |
|---|---|
| Application | CLI gốc và các ứng dụng WSGI nhỏ viết bằng Python standard library. |
| SQLite | Nguồn dữ liệu chính cho hồ sơ sinh viên; file mặc định là `data/students.db`. |
| Redis | Cache-aside cho tra cứu sinh viên và kho session phía server. TTL/invalidation được minh họa trực tiếp. |
| Cache Dashboard | UI local trên cổng `5001`, gọi cùng `StudentService` và key Redis như CLI. |
| Session Storage Demo | UI local trên cổng `5000`; cookie chứa session reference, Redis giữ session data. |
| Memcached | Backend thứ hai chỉ dùng trong Cache Performance Lab để đối chiếu với Redis. |
| Cache Performance Lab | So sánh phép xử lý payload `NO CACHE`, Redis và Memcached. Không thay đổi nghiệp vụ tra cứu sinh viên. |
| SQLite/Redis Benchmark | Script độc lập so sánh SQLite trực tiếp với Redis cold-cache/warm-cache, dùng database benchmark riêng. |
| Docker Compose | Chạy Redis và Memcached cục bộ; hai service chỉ publish lên địa chỉ loopback. |

Các luồng độc lập: Dashboard/CLI dùng SQLite làm nguồn hồ sơ và Redis làm cache; Session Demo không dùng SQLite; Memcached không tham gia Student Lookup hoặc Session Demo. Performance Lab chỉ cache kết quả xử lý của workload tổng hợp.

## Technology stack và dependencies

- **Python**: ứng dụng, script benchmark và unit tests.
- **WSGI trong Python standard library** (`wsgiref.simple_server`): hai web demo. Project không dùng Flask.
- **SQLite**: đi kèm Python, lưu dữ liệu sinh viên và dữ liệu tổng hợp riêng của benchmark SQLite/Redis.
- **Redis**: image `redis:7-alpine`; Python package `redis>=5.0,<7.0`.
- **Memcached**: image `memcached:alpine`; Python package `pymemcache>=4.0,<5.0`.
- **pytest**: `pytest>=8.0,<9.0`, chạy unit tests.
- **Docker Desktop và Docker Compose**: chạy Redis/Memcached. `docker compose` là lệnh plugin của Docker CLI.

Danh sách package Python nằm trong `requirements.txt`. Không có Flask hoặc package web framework bên ngoài.

## Setup từ đầu trên Windows

### 1. Lấy source và mở PowerShell

Clone repository đã cấu hình trong Git hoặc tải ZIP và giải nén. Từ PowerShell:

```powershell
git clone https://github.com/minhthanhle2309/redis-student-lookup-demo.git
Set-Location .\redis-student-lookup-demo
```

Nếu đã giải nén ZIP, mở PowerShell tại thư mục gốc (nơi có `README.md`, `docker-compose.yml` và thư mục `src`).

### 2. Tạo môi trường Python và cài dependencies

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Dấu nhắc PowerShell thường hiển thị `(.venv)` sau khi activate. Nếu máy không có launcher `py`, cài Python và dùng lệnh `python -m venv .venv`.

### 3. Khởi động Docker services và kiểm tra

Mở Docker Desktop, đợi engine sẵn sàng rồi chạy:

```powershell
docker compose up -d redis memcached
docker compose ps
docker compose exec redis redis-cli ping
```

Redis phải trả `PONG`; chờ cả Redis và Memcached hiện `healthy` trong `docker compose ps`. Mục [Docker](#docker-và-docker-compose) có cách xem logs, kiểm tra ports và dừng services.

### 4. Chuẩn bị SQLite trước khi dùng Dashboard

Khi chạy `python -m src.main`, CLI gọi `initialize_database()`: tạo bảng `students` nếu chưa có và thêm ba sinh viên mẫu nếu bảng rỗng. Dashboard **không** khởi tạo schema hay dữ liệu. Trên database mới, chạy CLI một lần, xem danh sách nếu cần, rồi chọn `0` để thoát trước khi khởi chạy Dashboard. Database mặc định là `data/students.db`.

Có thể dùng một đường dẫn DB khác bằng cách đặt biến trước khi chạy ứng dụng:

```powershell
$env:STUDENT_DB_PATH = ".\data\seminar-test.db"
python -m src.main
```

Đặt biến này riêng trong mỗi terminal dùng database đó. Dùng CLI để khởi tạo DB mới; Dashboard vẫn chỉ đọc/tra cứu và không tự thêm schema hay mẫu.

## Docker và Docker Compose

Compose khai báo hai service:

| Service | Container | Cổng host mặc định | Health check |
|---|---|---:|---|
| `redis` | `redis-student-demo` | `127.0.0.1:6379` | `redis-cli ping` |
| `memcached` | `redis-student-demo-memcached` | `127.0.0.1:11211` | Lệnh `version` qua `nc` |

Redis chạy với persistence tắt trong cấu hình demo. Dữ liệu trong Redis container có thể mất khi container bị tạo lại. Cổng host Redis có thể đổi bằng `REDIS_PORT` khi chạy Compose; nếu đổi, đặt cùng giá trị `REDIS_PORT` trong PowerShell của ứng dụng. Memcached adapter hiện kết nối `localhost:11211`; giữ cổng mặc định để chạy Performance Lab.

```powershell
# Khởi động hai service
docker compose up -d redis memcached

# Xem trạng thái/health
docker compose ps

# Redis ping và mở redis-cli tương tác
docker compose exec redis redis-cli ping
docker compose exec redis redis-cli

# Kiểm tra TCP port mặc định từ PowerShell
Test-NetConnection 127.0.0.1 -Port 6379
Test-NetConnection 127.0.0.1 -Port 11211

# Xem logs
docker compose logs --tail 100 redis
docker compose logs --tail 100 memcached

# Dừng và gỡ containers/networks do Compose tạo
docker compose down
```

`docker compose down` không xóa file SQLite hoặc các report. Không dùng `docker compose down -v`, `FLUSHDB` hoặc `FLUSHALL` cho seminar này.

## Redis Student Lookup CLI

Chạy CLI gốc:

```powershell
python -m src.main
```

Menu hiện có: xem danh sách, tra cứu, thêm, cập nhật, xóa sinh viên, demo HIT/MISS, demo TTL ngắn và hướng dẫn benchmark. Chọn `0` để thoát. Khi khởi chạy, CLI khởi tạo SQLite như phần setup. Nếu Redis không sẵn sàng, CLI cảnh báo; tra cứu có thể tiếp tục qua SQLite và hiện `BYPASS` thay vì báo HIT.

### Luồng tra cứu

1. SQLite là source of truth. Redis chỉ giữ bản cache JSON theo key `student:<MSSV>`.
2. **MISS**: Redis chưa có key hợp lệ; `StudentService` đọc SQLite. Nếu có hồ sơ, ghi JSON vào Redis với TTL. Hồ sơ không tồn tại không được cache.
3. **HIT**: Redis có JSON hợp lệ cho đúng MSSV; kết quả trả từ Redis và TTL được đọc.
4. **BYPASS**: Redis đọc/ghi gặp lỗi; kết quả tra cứu được lấy trực tiếp từ SQLite. Đây không phải HIT.
5. Khi cập nhật/xóa sinh viên, service xóa key cùng MSSV. Thêm mới cũng gọi invalidation cùng MSSV.

### Kịch bản MISS, HIT, kiểm tra key và invalidation

Trong CLI chọn `6` và nhập một MSSV có trong danh sách (ví dụ `SV001` nếu còn tồn tại). Tùy chọn này xóa đúng key sinh viên đó trước; lần đầu thường `MISS`, lần sau thường `HIT`. Hoặc chọn `2` hai lần để tra cứu bình thường.

Trong một terminal khác, xem key đúng MSSV:

```powershell
docker compose exec redis redis-cli GET student:SV001
docker compose exec redis redis-cli TTL student:SV001
```

Đổi `SV001` thành MSSV đang tra cứu. `GET` trả JSON nếu key tồn tại; `TTL` trả số giây còn lại, `-2` nếu key không tồn tại, `-1` nếu không đặt expiry.

Để chứng minh invalidation, tạo cache bằng lựa chọn `2`, chọn `4` cập nhật đúng sinh viên, sau đó tra lại bằng `2`. Service xóa cache cũ; lần đọc sau sẽ nạp thông tin mới từ SQLite (thường là `MISS`). Lựa chọn `5` xóa hồ sơ và key tương ứng. Không thử CRUD trên dữ liệu thật nếu không muốn thay đổi DB.

Lựa chọn `7` minh họa TTL cố định 3 giây: xóa key, đọc để tạo lại, chờ 4 giây, đọc lại. Nó không dùng giá trị `CACHE_TTL_SECONDS` vì lựa chọn này truyền TTL 3 giây trực tiếp.

## Cache Dashboard

- **Lệnh:** `python -m src.cache_dashboard`
- **URL:** [http://127.0.0.1:5001](http://127.0.0.1:5001)
- **Bind:** `127.0.0.1`, chỉ phục vụ local.
- **Database:** dùng `STUDENT_DB_PATH` hoặc `data/students.db`; không khởi tạo schema/sample.

Dashboard dùng `StudentService` hiện tại, hiển thị trạng thái lookup, source (SQLite/Redis), key, TTL, trace sự kiện và sơ đồ luồng. Nút **Làm mới trạng thái** ping Redis; **Kiểm tra TTL** đọc TTL của MSSV; **Xóa cache của MSSV này** chỉ xóa key đúng MSSV đang nhập. MSSV giới hạn 1–32 ký tự ASCII gồm chữ, số, `_` hoặc `-`.

Khởi chạy sau khi Redis healthy và database có bảng `students`:

```powershell
python -m src.cache_dashboard
```

Mở URL trong browser, nhập MSSV có thật rồi bấm tra cứu. Lần đầu key chưa có thường hiện `MISS`, source `SQLite`; tra cứu lại sẽ `HIT`, source `Redis`. Bấm **Kiểm tra TTL** để xem số giây Redis trả về. Bấm xóa cache rồi tra lại để thấy MISS. Kiểm chứng trực tiếp trong PowerShell:

```powershell
docker compose exec redis redis-cli GET student:SV001
docker compose exec redis redis-cli TTL student:SV001
```

Thay MSSV trong key bằng giá trị thực tế trên Dashboard. Có thể kiểm thử BYPASS bằng cách dừng Redis trong lúc Dashboard đang chạy, tra cứu, rồi bật lại:

```powershell
docker compose stop redis
docker compose start redis
```

### TTL của StudentService

`CACHE_TTL_SECONDS` mặc định là **60 giây**. Giá trị được đọc khi Python import `src.cache`; đặt/đổi biến trong PowerShell **trước khi chạy** CLI hoặc Dashboard. Ứng dụng đang chạy không tự đọc lại biến, nên cần dừng và khởi động lại tiến trình Python. Không cần restart Redis chỉ để đổi TTL application.

```powershell
$env:CACHE_TTL_SECONDS = "5"
python -m src.cache_dashboard
```

Sau đó xóa cache, lookup để tạo lại key, rồi dùng **Kiểm tra TTL**. CLI lựa chọn `7` vẫn dùng TTL cố định 3 giây như đã nêu.

## Session Storage Demo

Session Demo là WSGI app độc lập, không dùng SQLite. Chạy trong terminal riêng khi Redis đang hoạt động:

```powershell
python -m src.session_demo
```

- **Port:** `5000`
- **URL:** [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **Credential mặc định trong code:** username `demo`, password `redis123`.
- **TTL mặc định:** 45 giây (`SESSION_TTL_SECONDS`).

Mở URL, đăng nhập, tải lại hoặc mở `/status` để xem user và TTL còn lại; gửi form **Truy cập trang được bảo vệ**, sau đó **Đăng xuất**. Route bảo vệ trả unauthorized khi chưa đăng nhập, session hết hạn hoặc bị xóa. Logout xóa server-side key và xóa cookie session. Form POST kiểm tra CSRF token.

Cookie `seminar_session` chỉ mang session ID ngẫu nhiên, có `HttpOnly` và `SameSite=Lax`; session data (username) nằm trong Redis dưới prefix `seminar:session:` với TTL. Cookie không đặt `Max-Age`; thời hạn hiệu lực server-side do TTL Redis quyết định. CSRF token dùng cookie riêng. Không đưa session ID, cookie, raw session key/value hoặc bất kỳ secret nào vào README, ảnh chụp seminar hay log chia sẻ. Nếu kiểm tra Redis, chỉ kiểm tra số lượng key/TTL trên máy local và không công bố giá trị.

Ví dụ đặt TTL ngắn trước khi start, trong cùng PowerShell:

```powershell
$env:SESSION_TTL_SECONDS = "10"
python -m src.session_demo
```

Đăng nhập, chờ quá 10 giây, tải lại `/status` hoặc thử route được bảo vệ để thấy session hết hạn. Biến chỉ được đọc lúc app khởi tạo; restart app để áp dụng giá trị mới. Có thể kiểm tra key prefix mà không in giá trị session:

```powershell
$sessionKey = docker compose exec redis redis-cli --raw --scan --pattern 'seminar:session:*' | Select-Object -First 1
if ($sessionKey) { docker compose exec redis redis-cli TTL $sessionKey }
```

Nếu nhiều session đang tồn tại, câu lệnh lấy một key đầu tiên bất kỳ. Không chạy lệnh `GET` để in session data khi trình chiếu. Mật khẩu demo được xác minh bằng PBKDF2-HMAC-SHA256; password hash không cần đưa vào README. Có thể đổi username bằng `SESSION_DEMO_USERNAME` và password bằng cách cấu hình `SESSION_PASSWORD_HASH` đúng định dạng mà code xác minh; các giá trị mặc định dành cho lớp học.

Demo dùng HTTP local; HTTP không mã hóa đường truyền. Chỉ dùng dữ liệu và credential demo trên máy cá nhân trong lớp, không đưa ứng dụng lên mạng công cộng hay dùng thông tin thật. Khi chạy phía sau HTTPS, cookie được thêm cờ `Secure` theo scheme WSGI.

## Memcached Demo

Memcached là backend đối chiếu cho Cache Performance Lab; nó **không** được dùng để cache Student Lookup hoặc lưu session. Docker Compose khởi chạy image `memcached:alpine` với 64 MB memory, bind cổng host `127.0.0.1:11211` và healthcheck `version`.

Khởi động và kiểm tra:

```powershell
docker compose up -d memcached
docker compose ps
Test-NetConnection 127.0.0.1 -Port 11211
```

Trạng thái Compose cần là `healthy`; `TcpTestSucceeded: True` xác nhận TCP port có listener. Cache Performance Lab còn gọi kiểm tra version qua adapter trước khi đo, vì vậy kết nối lỗi sẽ làm benchmark dừng. Cài `pymemcache` bằng `python -m pip install -r requirements.txt` nếu Python báo thiếu module.

Chạy riêng backend Memcached (so với baseline NO CACHE):

```powershell
python -m scripts.cache_performance --mode memcached --sizes 1MB,10MB --runs 5 --rounds 3
```

## Cache Performance Lab

Script `scripts/cache_performance.py` chạy phép xử lý payload xác định với ba mode:

- **NO CACHE:** mỗi lượt thực hiện các vòng SHA-256 trên payload.
- **Redis / Memcached:** GET digest; khi cache miss thì xử lý payload rồi SET kết quả. Cache chỉ lưu digest 32 byte, không lưu payload đầu vào.

Payload mặc định: 1 KB, 100 KB, 1 MB, 5 MB, 10 MB. Payload lớn làm tăng chi phí SHA-256 ở MISS/NO CACHE; HIT bỏ qua phép tính đó. Đây là workload CPU-bound local một tiến trình, không đại diện cho mọi ứng dụng hay benchmark cache object lớn.

### Các tham số và metrics

- `--sizes`: danh sách kích thước, phân cách bằng dấu phẩy. Parser nhận KB, MB hoặc số byte, ví dụ `1KB,100KB,1MB`.
- `--runs`: số request được bấm giờ trên mỗi mode/cỡ payload. Mặc định `5`.
- `--rounds`: số vòng SHA-256 trên payload mỗi lần cần tính kết quả. Mặc định `3`.
- `--mode`: `all` (mặc định), `no-cache`, `redis` hoặc `memcached`. Chế độ một cache vẫn đo thêm NO CACHE làm baseline.
- `--csv`, `--markdown`: đổi đường dẫn output; mặc định là `benchmark-results/cache-performance.csv` và `benchmark-results/cache-performance.md`.
- **HIT/MISS:** lần cache đầu tiên sau khi xóa đúng key là MISS; các lần kế tiếp thường là HIT. NO CACHE không gọi cache nên số đếm HIT/MISS bằng 0.
- **Hit rate:** `HIT / số request * 100`; không có ý nghĩa như tỷ lệ thành công của NO CACHE.
- **Average:** trung bình latency mỗi request.
- **P50:** median/percentile 50; một nửa mẫu ở hoặc dưới mức này.
- **P95:** percentile 95; phần lớn mẫu ở hoặc dưới mức này, nhạy với độ trễ đuôi.
- **Min/Max:** latency nhỏ nhất/lớn nhất quan sát được.
- **Throughput:** số request chia cho tổng thời gian đo, đơn vị ops/s.
- **Speedup:** average NO CACHE chia cho average mode đang xét; >1x nghĩa là nhanh hơn ở workload/máy đo này, <1x nghĩa là chậm hơn. Không phải cam kết chung.

Kết nối và interpreter được làm nóng ngoài phép đo; script xóa chính xác key thuộc prefix lab, không flush cache. Thời gian cache tính từ trước GET tới sau SET; phần SHA-256 khi MISS được tính. Payload, checksum tạo key và một lần tính khởi động không tính giờ. Cùng payload, số lượt và rounds được dùng trên mọi mode trong một lần chạy. Độ trễ có thể lệch do scheduler/tải nền; benchmark một tiến trình không mô phỏng concurrent load.

### Lệnh thực tế

Xem đúng trợ giúp từ argparse:

```powershell
python -m scripts.cache_performance --help
```

Workload nhỏ, nhanh, chỉ NO CACHE (không cần Redis/Memcached):

```powershell
python -m scripts.cache_performance --mode no-cache --sizes 1KB,100KB --runs 2 --rounds 1
```

Chạy tất cả kích thước mặc định, so sánh đủ Redis/Memcached/NO CACHE (cần cả hai service):

```powershell
python -m scripts.cache_performance --runs 5 --rounds 3
```

Chỉ các kích thước đã chọn nhưng vẫn so cả ba mode:

```powershell
python -m scripts.cache_performance --sizes 1KB,100KB,1MB,5MB,10MB --runs 5 --rounds 3
```

Chỉ Redis hoặc Memcached so với NO CACHE:

```powershell
python -m scripts.cache_performance --mode redis --sizes 100KB,1MB --runs 10 --rounds 5
python -m scripts.cache_performance --mode memcached --sizes 100KB,1MB --runs 10 --rounds 5
```

### Output của Performance Lab

- `benchmark-results/cache-performance.csv`
- `benchmark-results/cache-performance.md`

CSV có các cột `payload`, `mode`, `count`, `average_ms`, `p50_ms`, `p95_ms`, `min_ms`, `max_ms`, `total_elapsed_ms`, `throughput_ops_s`, `hits`, `misses`, `hit_rate_percent`, `speedup_vs_no_cache`. Markdown trình bày cùng kết quả dưới dạng bảng và ghi cấu hình/scope. Mỗi lần chạy ghi đè hai report cùng tên; dùng `--csv` và `--markdown` nếu cần giữ nhiều lần chạy.

## Benchmark SQLite và Redis

Đây là script khác: `scripts/benchmark.py`. Nó tạo dữ liệu tổng hợp trong `data/benchmark_students.db` và so sánh SQLite trực tiếp, Redis cold-cache và Redis warm-cache. Nó không dùng `data/students.db`. Cần Redis đang chạy.

Lệnh mặc định seminar:

```powershell
python -m scripts.benchmark --dataset-size 1000 --queries 500 --repetitions 3
```

Các options thực tế từ argparse:

```powershell
python -m scripts.benchmark --help
python -m scripts.benchmark --dataset-size 5000 --queries 1000 --repetitions 5 --seed 2026
```

`--dataset-size`, `--queries`, `--repetitions`, `--seed` điều chỉnh workload; `--csv`, `--markdown` đổi vị trí report. Script dùng prefix `seminar:benchmark:student:` và xóa key trong namespace đó trước khi đo. Không chạy benchmark trỏ vào DB sinh viên mặc định; code từ chối đường dẫn database gốc.

## Benchmark Results

Các report hiện có trong `benchmark-results/` là snapshot của những lần chạy trước, không phải số liệu đảm bảo sẽ lặp lại. Lệnh chạy tương ứng sẽ tạo mới/ghi đè report cùng tên.

| Benchmark | CSV | Markdown | Ý nghĩa |
|---|---|---|---|
| SQLite/Redis | `benchmark-results/results.csv` | `benchmark-results/summary.md` | SQLite direct, Redis cold-cache, Redis warm-cache. |
| Cache Performance Lab | `benchmark-results/cache-performance.csv` | `benchmark-results/cache-performance.md` | Các mode NO CACHE, Redis, Memcached theo payload. |

Ở SQLite/Redis report, `method` là phương pháp; `count` là số truy vấn; `average_ms`, `median_ms`/p50, `p95_ms` là phân phối latency; `total_elapsed_ms` là tổng các khoảng đo; `throughput_ops_s` là throughput; `hits`, `misses`, `hit_rate_percent` là thống kê cache. SQLite direct không có cache nên hit rate để trống trong CSV. Cold-cache được làm sạch đúng namespace trước truy vấn; warm-cache được khởi tạo trước lượt đo.

Ở Performance Lab, `payload` là cỡ đầu vào và `mode` là cách xử lý. `count` là số lượt, các cột latency/throughput tương tự; `min_ms`/`max_ms` là khoảng quan sát; HIT/MISS và hit rate mô tả cache mode; `speedup_vs_no_cache` là tỷ số average NO CACHE / average mode theo cùng payload. NO CACHE có đếm HIT/MISS bằng 0, không phải do cache miss.

P50 là mốc giữa; P95 giúp thấy tail latency nhưng với số mẫu nhỏ có thể biến động mạnh. Đọc HIT/MISS cùng với mode: nhiều HIT nghĩa là truy vấn cache được phục vụ, không chứng minh toàn hệ thống nhanh hơn trong mọi tải. Speedup lớn hơn 1 chỉ cho biết mode đó có average thấp hơn NO CACHE trong workload cụ thể. Redis không được đảm bảo nhanh hơn Memcached (hoặc SQLite); payload, rounds, serialization, kết nối, máy và tải nền đều ảnh hưởng kết quả. Không dùng report snapshot làm số liệu tổng quát.

## Troubleshooting

| Vấn đề | Nguyên nhân/kiểm tra | Cách xử lý |
|---|---|---|
| Docker Desktop chưa chạy | `docker compose ps` báo không kết nối được Docker engine. | Mở Docker Desktop, đợi engine sẵn sàng, chạy `docker compose up -d redis memcached`. |
| Redis không connect được | Kiểm tra `docker compose ps`, `docker compose logs --tail 100 redis`, `Test-NetConnection 127.0.0.1 -Port 6379`. | Chạy `docker compose up -d redis`; kiểm tra `docker compose exec redis redis-cli ping`. Nếu đổi host port, đồng bộ `$env:REDIS_PORT` trước khi start Compose và app. |
| Memcached không connect được | Kiểm tra service health và `Test-NetConnection 127.0.0.1 -Port 11211`. | `docker compose up -d memcached`; xem `docker compose logs --tail 100 memcached`. Adapter lab đang dùng port 11211 mặc định. |
| Cổng 6379 đã được dùng | Compose không publish được Redis host port. | Dừng process/service đang dùng cổng, hoặc đặt `$env:REDIS_PORT = "6380"`, chạy Compose lại và đặt cùng `$env:REDIS_PORT` trong terminal app. |
| Cổng 11211 đã được dùng | Memcached host port bận; Compose không thể bind. | Dừng listener hiện tại. Performance Lab kết nối cố định tới `localhost:11211`, nên cần giải phóng cổng mặc định để chạy adapter hiện tại. |
| Cổng Dashboard `5001` hoặc Session `5000` bị chiếm | WSGI server báo lỗi bind/address already in use. | Dừng process cũ bằng `Ctrl+C` trong terminal tương ứng; source hiện bind cố định vào `127.0.0.1:5001` và `127.0.0.1:5000`. |
| Thiếu `pymemcache` | Import error khi chạy mode Memcached/all. | Activate `.venv`, chạy `python -m pip install -r requirements.txt`. |
| `.venv` chưa activate / pip cài sai Python | `python` không phải interpreter trong project. | Chạy `.\.venv\Scripts\Activate.ps1` từ project root rồi `python -m pip install -r requirements.txt`; kiểm tra `python -c "import sys; print(sys.executable)"`. |
| PowerShell chặn `Activate.ps1` | Execution policy của process không cho script chạy. | Chạy `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, rồi `.\.venv\Scripts\Activate.ps1`. Chỉ áp dụng cho cửa sổ hiện tại. |
| Redis CLI không thấy key | Có thể tra sai MSSV/DB/port, key đã hết TTL, invalidation đã xóa hoặc lookup chưa chạy. | Chọn đúng MSSV từ CLI/Dashboard, lookup lại, rồi `docker compose exec redis redis-cli --scan --pattern 'student:*'`. Kiểm tra đúng Redis DB/port của app. |
| Dashboard báo MISS/HIT nhưng CLI không thấy key | CLI có thể nối Redis khác do biến môi trường; key có thể vừa hết hạn/xóa. | Với ví dụ MSSV `SV001`, chạy `docker compose exec redis redis-cli GET student:SV001` và `docker compose exec redis redis-cli TTL student:SV001`; thay `SV001` bằng MSSV thật. Xác nhận `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`. |
| TTL khác mong đợi | Key được tạo trước khi đổi biến, TTL giảm theo thời gian, hoặc đang chạy TTL demo 3 giây. | Đặt `$env:CACHE_TTL_SECONDS` trước khi chạy app; restart tiến trình Python, xóa key, lookup lại. Không cần restart Redis. Lựa chọn CLI `7` luôn dùng 3 giây. |
| Login Session Demo thất bại | Redis chưa hoạt động, CSRF cookie/form token không khớp, hoặc credential đã override. | Ping Redis; reload `http://127.0.0.1:5000` để lấy form/token mới; dùng credential mặc định `demo` / `redis123` nếu chưa đặt override. Session demo không login offline. |
| Session tưởng đã logout nhưng còn hoạt động | Cookie cũ/Redis key khác phiên; hoặc đang xem tab/cookie khác. | Logout qua form cùng browser; trạng thái server-side mới là nguồn xác nhận. Không chia sẻ session ID/cookie. TTL mặc định 45 giây. |
| Benchmark chạy quá lâu | Dataset, queries, repetitions, payload hoặc rounds lớn; 10 MB và rounds cao làm SHA-256 lặp lâu. | Giảm `--dataset-size`, `--queries`, `--repetitions`; Performance Lab dùng `--sizes 1KB,100KB --runs 2 --rounds 1`. |
| Cache Performance Lab không kết nối Redis/Memcached | Service chưa healthy hoặc host port sai. | Chạy `docker compose ps`, ping Redis, kiểm tra TCP 6379/11211. Mode `all` cần cả hai; `--mode redis` chỉ cần Redis, `--mode memcached` chỉ cần Memcached, `--mode no-cache` không cần cache service. |
| Dashboard không tra cứu được | Dashboard không tự tạo bảng/sample, hoặc SQLite path không đúng. | Khởi tạo DB bằng `python -m src.main` (chọn `0` sau khi hoàn tất), kiểm tra `STUDENT_DB_PATH` trong cùng terminal khi start Dashboard. |

## Seminar Demo Flow

1. **A — Giới thiệu project:** SQLite là nguồn dữ liệu; Redis minh họa cache và session; Memcached là đối tượng benchmark riêng.
2. **B — Student Lookup:** chạy `python -m src.main`, xem danh sách để chọn MSSV tồn tại.
3. **C — MISS:** lựa chọn `6` xóa đúng key rồi tra lần đầu; giải thích đọc SQLite và ghi Redis.
4. **D — HIT:** lần hai cùng MSSV; giải thích kết quả lấy từ Redis.
5. **E — Kiểm chứng key:** ví dụ `docker compose exec redis redis-cli GET student:SV001` và `docker compose exec redis redis-cli TTL student:SV001`; dùng MSSV thật đang trình bày.
6. **F — TTL:** chạy lựa chọn `7` để xem TTL 3 giây, hoặc cấu hình `CACHE_TTL_SECONDS` trước khi khởi chạy Dashboard/CLI rồi quan sát Redis TTL.
7. **G — Session Storage:** chạy `python -m src.session_demo`, login bằng credential mặc định, xem `/status`, kiểm tra TTL, logout; nhấn mạnh cookie là reference, Redis giữ data.
8. **H — Redis vs Memcached:** đảm bảo hai service healthy; giải thích Memcached chỉ được dùng ở Performance Lab.
9. **I — Performance Benchmark:** chạy `python -m scripts.cache_performance --sizes 1KB,100KB --runs 3 --rounds 2`; đối chiếu CSV/Markdown. Hoặc chạy SQLite/Redis benchmark riêng bằng `python -m scripts.benchmark --dataset-size 1000 --queries 500 --repetitions 3`.
10. **J — Kết luận:** Redis phù hợp mục tiêu minh họa của project vì cùng một service hỗ trợ cache có TTL, key/invalidation và server-side session. Benchmark là workload local cụ thể, không đủ căn cứ để kết luận Redis luôn nhanh nhất.

Xem thêm kịch bản tại [docs/demo-guide.md](docs/demo-guide.md), hướng dẫn Dashboard tại [docs/cache-dashboard-guide.md](docs/cache-dashboard-guide.md), và hướng dẫn Performance Lab tại [docs/cache-performance-lab.md](docs/cache-performance-lab.md).

## Commands Cheat Sheet

Các lệnh dưới đây giả định PowerShell đang ở project root.

```powershell
# Môi trường và dependencies
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# Docker: Redis + Memcached
docker compose up -d redis memcached
docker compose ps
docker compose exec redis redis-cli ping
Test-NetConnection 127.0.0.1 -Port 6379
Test-NetConnection 127.0.0.1 -Port 11211

# Student Lookup CLI và Dashboard
python -m src.main
python -m src.cache_dashboard
# Mở http://127.0.0.1:5001

# Redis key/TTL mẫu; thay SV001 bằng MSSV đang dùng
docker compose exec redis redis-cli GET student:SV001
docker compose exec redis redis-cli TTL student:SV001
docker compose exec redis redis-cli --scan --pattern 'student:*'

# Session Storage; mở http://127.0.0.1:5000
python -m src.session_demo
# Kiểm tra TTL của một server-side session mà không in value
$sessionKey = docker compose exec redis redis-cli --raw --scan --pattern 'seminar:session:*' | Select-Object -First 1
if ($sessionKey) { docker compose exec redis redis-cli TTL $sessionKey }

# Cache Performance Lab: NO CACHE + Redis + Memcached
python -m scripts.cache_performance --help
python -m scripts.cache_performance --sizes 1KB,100KB --runs 3 --rounds 2

# Benchmark SQLite vs Redis
python -m scripts.benchmark --help
python -m scripts.benchmark --dataset-size 1000 --queries 500 --repetitions 3

# Tests và dừng services
python -m pytest -q
docker compose logs --tail 100 redis
docker compose logs --tail 100 memcached
docker compose down
deactivate
```
