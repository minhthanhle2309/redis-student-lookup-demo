# Redis Student Lookup Demo

Demo CLI cho seminar SOA: SQLite giữ dữ liệu sinh viên chính; Redis cache kết quả tra cứu có TTL. Có thêm demo session Redis độc lập và benchmark riêng. CLI ban đầu vẫn chạy bằng `src.main`.

## Yêu cầu và cài đặt (PowerShell, Windows)

Cần Python 3.10 trở lên, Git và Docker Desktop. Docker chỉ cần cho Redis. Từ thư mục repository:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Nếu PowerShell chặn kích hoạt môi trường ảo:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Khởi động Redis bằng Docker

Mở Docker Desktop trước, sau đó chạy:

```powershell
docker compose up -d
docker compose ps
docker compose exec redis redis-cli ping
```

Lệnh cuối phải hiện `PONG`. Compose ánh xạ Redis lên `127.0.0.1:6379`; ứng dụng dùng mặc định `REDIS_HOST=localhost`, `REDIS_PORT=6379`, `REDIS_DB=0`, `REDIS_TIMEOUT=2`. Có thể đổi cấu hình trong PowerShell trước khi chạy ứng dụng:

```powershell
$env:REDIS_HOST = "localhost"
$env:REDIS_PORT = "6379"
$env:REDIS_DB = "0"
$env:REDIS_TIMEOUT = "2"
$env:CACHE_TTL_SECONDS = "60"
```

Các biến môi trường này chỉ có hiệu lực trong cửa sổ PowerShell hiện tại. Không cần cài Docker nếu Redis đã chạy sẵn ở địa chỉ cấu hình.

## Chạy CLI gốc

```powershell
python -m src.main
```

Menu giữ nguyên các thao tác xem, tra cứu, thêm, cập nhật, xóa sinh viên. Dữ liệu SQLite mặc định ở `data/students.db`; ứng dụng chỉ tạo bảng và dữ liệu mẫu nếu database chưa có bảng/sinh viên. Có thể trỏ sang database khác để chạy thử riêng:

```powershell
$env:STUDENT_DB_PATH = ".\data\seminar-test.db"
python -m src.main
```

Tra cứu hiển thị MSSV, trạng thái `HIT`, `MISS` hoặc `BYPASS`, Redis key và TTL còn lại nếu đọc được. `BYPASS` nghĩa là Redis gặp lỗi và kết quả được đọc trực tiếp từ SQLite; không được tính là cache HIT. Sau khi sửa/xóa, khóa của sinh viên đó được xóa. Thêm mới cũng xóa khóa cùng MSSV nếu có.

### Kịch bản cache HIT, MISS, TTL, invalidation

Chạy CLI và làm lần lượt:

1. Chọn `6`, nhập `SV001`: chương trình xóa đúng khóa `student:SV001`; lần đầu là `MISS`, lần hai là `HIT`.
2. Chọn `2`, nhập `SV001` để xem TTL còn lại. Đợi hơn 60 giây (hoặc đặt `$env:CACHE_TTL_SECONDS = "5"` trước khi khởi chạy CLI) rồi tra cứu lại: trạng thái là `MISS`.
3. Chọn `7`, nhập `SV001`: demo TTL ngắn 3 giây, chờ 4 giây rồi tra lại và thấy `MISS`.
4. Tạo cache bằng lựa chọn `2`, rồi chọn `4` để đổi thông tin `SV001`; lần đọc tiếp theo là `MISS` và có dữ liệu mới. Chọn `5` để xóa sinh viên và khóa cache.

## Demo session lưu trên Redis

Chạy trong cửa sổ PowerShell khác, vẫn ở thư mục repository và đã kích hoạt `.venv`:

```powershell
$env:SESSION_TTL_SECONDS = "45"
python -m src.session_demo
```

Mở `http://127.0.0.1:5000`. Tài khoản trình diễn: tên `demo`, mật khẩu `redis123`. Đăng nhập, làm mới trang để xem trạng thái và TTL, thử truy cập nội dung được bảo vệ, rồi đăng xuất và thử lại. Chờ quá 45 giây để trình bày session tự hết hạn. Có thể đổi TTL bằng `SESSION_TTL_SECONDS`.

Session ID ngẫu nhiên nằm trong cookie `HttpOnly; SameSite=Lax`; dữ liệu xác thực nằm phía server trong Redis. Form POST kiểm tra CSRF token. Mật khẩu demo được kiểm tra bằng PBKDF2-HMAC-SHA256; mã nguồn chỉ chứa hash, không ghi mật khẩu vào log. Redis không sẵn sàng thì ứng dụng trả lỗi dịch vụ và không đăng nhập offline. Demo chạy HTTP local nên **không mã hóa dữ liệu trên đường truyền**; chỉ dùng trên máy cá nhân trong lớp, không dùng cho thông tin thật. Cookie tự thêm `Secure` khi ứng dụng được phục vụ qua HTTPS.

Dừng web demo bằng `Ctrl+C` trong cửa sổ đang chạy.

## Web Dashboard trình diễn Redis Cache

Dashboard chạy riêng tại `http://127.0.0.1:5001`, không chiếm cổng Session Demo `5000`. Không cần thêm package Python. Hướng dẫn PowerShell, kịch bản MISS → HIT, TTL, xóa đúng key và BYPASS nằm ở [docs/cache-dashboard-guide.md](docs/cache-dashboard-guide.md).

Khởi động Redis bằng Docker Compose như các bước phía trên, rồi mở một PowerShell khác trong repository:

```powershell
python -m src.cache_dashboard
```

Dashboard tái sử dụng `StudentService` và key `student:<MSSV>` hiện có. Nó không khởi tạo schema hoặc dữ liệu mẫu; nếu database chưa có bảng `students`, dashboard báo lỗi an toàn và không sửa database.

## Benchmark SQLite và Redis

Lệnh này chạy trên máy cục bộ, cần Redis đang chạy nhưng không cần thêm Docker service:

```powershell
python -m scripts.benchmark --dataset-size 1000 --queries 500 --repetitions 3
```

Benchmark dùng `data/benchmark_students.db` riêng, tạo dữ liệu tổng hợp theo seed mặc định `2026`, chạy cùng chuỗi truy vấn cho SQLite trực tiếp, Redis cold-cache và Redis warm-cache. Dữ liệu demo `data/students.db` không được dùng. Kết quả đo thật được ghi vào `benchmark-results/results.csv` và `benchmark-results/summary.md`.

Có thể chỉnh cỡ dữ liệu, số truy vấn mỗi lượt và số lượt:

```powershell
python -m scripts.benchmark --dataset-size 5000 --queries 1000 --repetitions 5 --seed 2026
```

Báo cáo gồm trung bình, median/p50, p95, tổng thời gian, throughput và bộ đếm HIT/MISS. Tổng thời gian là tổng các khoảng tra cứu được bấm giờ; chuẩn bị database, xóa khóa để tạo cold cache, làm nóng cache và overhead vòng lặp không tính vào đó. Đây là phép đo local một tiến trình; hiệu năng tùy dữ liệu, tải nền, cache hệ điều hành, serialization và vị trí Redis. Redis không phải lúc nào cũng nhanh hơn SQLite. Benchmark chỉ xóa khóa có prefix `seminar:benchmark:student:`; không dùng `FLUSHDB` hay `FLUSHALL`.

## Cache Performance Lab: NO CACHE, Redis và Memcached

Hướng dẫn đầy đủ ở [docs/cache-performance-lab.md](docs/cache-performance-lab.md).

Lab riêng này so sánh xử lý trực tiếp với cache kết quả ở Redis và Memcached. Payload xác định có cỡ mặc định 1 KB, 100 KB, 1 MB, 5 MB và 10 MB. Mỗi lượt thực hiện nhiều vòng SHA-256 thật trên payload; cache chỉ giữ digest 32 byte. Đây là workload CPU-bound để thấy lợi ích khi HIT bỏ qua xử lý, không phải khẳng định cache luôn nhanh hơn hay mô phỏng mọi ứng dụng.

Thêm service Memcached vào Compose rồi cài dependencies:

```powershell
docker compose up -d redis memcached
docker compose ps
python -m pip install -r requirements.txt
```

Chạy so sánh đủ ba mode trên toàn bộ cỡ payload:

```powershell
python -m scripts.cache_performance --runs 5 --rounds 3
```

Có thể chọn một backend/cỡ payload, số lượt và lượng công việc CPU:

```powershell
python -m scripts.cache_performance --mode redis --sizes 100KB,1MB --runs 10 --rounds 5
python -m scripts.cache_performance --mode memcached --sizes 1MB,10MB --runs 5 --rounds 3
python -m scripts.cache_performance --mode no-cache --sizes 1KB,10MB --runs 5 --rounds 3
```

Mỗi cỡ chạy cùng payload và cùng số lượt. Kết nối được làm nóng ngoài phép đo; từng cache xóa đúng key thuộc namespace riêng trước khi chạy, vì vậy lượt cache đầu tiên là MISS và các lượt kế tiếp có thể là HIT. Không xóa toàn bộ Redis/Memcached. Báo cáo số đo thực được ghi riêng vào `benchmark-results/cache-performance.csv` và `benchmark-results/cache-performance.md`, gồm avg, p50, p95, min/max, throughput, HIT/MISS, hit rate và speedup so với NO CACHE. Payload, tạo key và một lượt xử lý làm nóng không tính giờ; GET, xử lý khi MISS và SET được tính. Kết quả là phép đo local một tiến trình, chịu ảnh hưởng của máy, tải nền, kết nối và cấu hình backend.

`--mode` nhận `all`, `no-cache`, `redis` hoặc `memcached`. Chế độ cache đơn lẻ vẫn xuất NO CACHE cùng với backend đã chọn để speedup có mốc so sánh. Mặc định yêu cầu cả hai service có thể kết nối được.
## Kiểm tra và kết thúc

Chạy unit tests không cần Redis:

```powershell
python -m pytest -q
```

Sau khi dừng CLI/session demo bằng `Ctrl+C` hoặc lựa chọn `0`, dừng Redis do Compose quản lý:

```powershell
docker compose down
deactivate
```

`docker compose down` dừng và gỡ container demo; Redis của cấu hình này không bật lưu bền dữ liệu. Không dùng `docker compose down -v`.

## Hướng dẫn trình bày

Kịch bản và câu hỏi seminar ở [docs/demo-guide.md](docs/demo-guide.md). Toàn bộ workflow có thể trình bày trong khoảng 10–15 phút: khởi động Redis, HIT/MISS và invalidation (4 phút), session/TTL (3 phút), benchmark và giới hạn đo (4 phút), câu hỏi (tùy thời gian).
