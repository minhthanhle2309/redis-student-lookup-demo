# Hướng dẫn Cache Performance Lab

Lab so sánh cùng một phép xử lý trên cùng payload ở ba mode: `NO CACHE`, Redis và Memcached. Nó độc lập với `scripts/benchmark.py`, vốn đo SQLite so với Redis.

## Chuẩn bị

Trong PowerShell tại thư mục repository:

```powershell
python -m pip install -r requirements.txt
docker compose up -d redis memcached
docker compose ps
```

Chờ Redis và Memcached ở trạng thái healthy. Redis giữ nguyên service và cổng cũ; Memcached mặc định nghe loopback `127.0.0.1:11211`. Có thể đổi cổng host bằng `$env:MEMCACHED_PORT` trước khi chạy Compose.

## Chạy so sánh

Chạy cả ba mode với payload 1 KB, 100 KB, 1 MB, 5 MB và 10 MB:

```powershell
python -m scripts.cache_performance --runs 5 --rounds 3
```

Chọn mode, payload, số lượt và khối lượng xử lý:

```powershell
python -m scripts.cache_performance --mode redis --sizes 100KB,1MB --runs 10 --rounds 5
python -m scripts.cache_performance --mode memcached --sizes 1MB,10MB --runs 5 --rounds 3
python -m scripts.cache_performance --mode no-cache --sizes 1KB,10MB --runs 5 --rounds 3
```

`--rounds` là số vòng SHA-256 thật chạy trên payload mỗi khi không có kết quả cache. Tăng số này để làm phần tính toán rõ hơn; hãy giữ cùng một giá trị khi so các mode. Mỗi lần chạy ghi kết quả thực vào `benchmark-results/cache-performance.csv` và `benchmark-results/cache-performance.md`.

Ví dụ dạng dòng trạng thái (số đo sẽ tùy máy):

```text
1 MB | NO CACHE: avg <đo được> ms
1 MB | Redis: avg <đo được> ms, HIT 4, MISS 1
1 MB | Memcached: avg <đo được> ms, HIT 4, MISS 1
Saved CSV: ...
Saved Markdown: ...
```

## Giải thích phép đo

Payload được tạo xác định. Cùng payload được gửi vào cùng phép xử lý ở mọi mode; cache lưu digest 32 byte. Cách này đo tác dụng bỏ qua tính toán khi có HIT, không đại diện cho ứng dụng cache cả object lớn.

Script làm nóng interpreter và kết nối ngoài phép đo, xóa đúng key trong namespace riêng của backend, rồi tính thời gian từ trước GET đến sau SET. Lượt cache đầu tiên dự kiến là MISS; các lượt sau là HIT nếu service hoạt động và TTL còn hiệu lực. Payload, checksum tạo cache key và lượt xử lý khởi động không nằm trong thời gian đo. Từng mode có số lượt bằng nhau.

Báo cáo có avg, p50, p95, min/max, tổng thời gian, throughput, HIT/MISS, hit rate và speedup tương đối với `NO CACHE`. Đây là đo local một tiến trình, không phải tải đồng thời. Kết nối, cấu hình, máy và tác vụ nền ảnh hưởng kết quả; overhead cache có thể khiến cache chậm hơn khi payload nhỏ hoặc công việc tính toán nhẹ.

Script chỉ xóa key cụ thể có prefix `seminar:cache-performance:redis:` hoặc `seminar:cache-performance:memcached:`; không gọi `FLUSHDB`, `FLUSHALL` hoặc xóa key ngoài lab.
