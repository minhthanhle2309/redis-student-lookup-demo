# Cache Performance Lab

Thời điểm đo: 2026-10-18T03:29:27.776163+00:00
Số lượt/mode: 20; số vòng SHA-256 trên payload: 1000

| Payload | Mode | Avg (ms) | p50 (ms) | p95 (ms) | Min–max (ms) | Ops/s | HIT | MISS | Hit rate | Speedup |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 KB | NO CACHE | 1.256 | 1.269 | 1.347 | 1.147–1.393 | 796.17 | 0 | 0 | 0.0% | 1.00x |
| 1 KB | Redis | 0.688 | 0.556 | 0.734 | 0.431–3.202 | 1453.88 | 19 | 1 | 95.0% | 1.83x |
| 1 KB | Memcached | 0.627 | 0.526 | 0.772 | 0.396–2.269 | 1595.23 | 19 | 1 | 95.0% | 2.00x |
| 100 KB | NO CACHE | 72.068 | 66.760 | 98.621 | 59.610–103.133 | 13.88 | 0 | 0 | 0.0% | 1.00x |
| 100 KB | Redis | 4.826 | 0.722 | 1.167 | 0.569–82.330 | 207.21 | 19 | 1 | 95.0% | 14.93x |
| 100 KB | Memcached | 4.251 | 0.594 | 0.907 | 0.409–73.564 | 235.26 | 19 | 1 | 95.0% | 16.95x |
| 1 MB | NO CACHE | 976.603 | 984.899 | 1066.214 | 877.981–1092.389 | 1.02 | 0 | 0 | 0.0% | 1.00x |
| 1 MB | Redis | 46.859 | 0.632 | 0.993 | 0.432–925.064 | 21.34 | 19 | 1 | 95.0% | 20.84x |
| 1 MB | Memcached | 47.204 | 0.677 | 1.168 | 0.492–931.046 | 21.18 | 19 | 1 | 95.0% | 20.69x |
| 5 MB | NO CACHE | 4600.123 | 4618.140 | 4738.119 | 4321.342–4753.529 | 0.22 | 0 | 0 | 0.0% | 1.00x |
| 5 MB | Redis | 231.344 | 0.578 | 1.070 | 0.429–4615.467 | 4.32 | 19 | 1 | 95.0% | 19.88x |
| 5 MB | Memcached | 231.413 | 0.484 | 1.053 | 0.415–4617.384 | 4.32 | 19 | 1 | 95.0% | 19.88x |
| 10 MB | NO CACHE | 9189.367 | 9209.445 | 9551.469 | 8858.398–9702.796 | 0.11 | 0 | 0 | 0.0% | 1.00x |
| 10 MB | Redis | 457.637 | 0.499 | 0.841 | 0.381–9142.300 | 2.19 | 19 | 1 | 95.0% | 20.08x |
| 10 MB | Memcached | 448.086 | 0.666 | 1.213 | 0.418–8948.895 | 2.23 | 19 | 1 | 95.0% | 20.51x |

## Cách đọc và giới hạn

Payload được tạo xác định và xử lý bằng nhiều vòng SHA-256 thật; không dùng sleep để tạo độ trễ. Cache lưu digest 32 byte của kết quả, còn payload đầu vào giống nhau ở cả ba mode. Mỗi mode có cùng số lượt đo; cache được làm nóng kết nối ngoài vùng đo, xóa đúng key riêng trước khi chạy, rồi đo một MISS lạnh và các HIT tiếp theo. Payload và checksum tạo key nằm ngoài khoảng bấm giờ; lệnh cache, xử lý payload khi MISS và ghi cache nằm trong khoảng đo.

Đây là workload CPU-bound trên một tiến trình và kết nối local. Nó minh họa chi phí xử lý được tránh khi có HIT, không đại diện cho mọi ứng dụng hay cho cache các object lớn. Redis/Memcached có overhead mạng, serialization và tải nền; kết quả thay đổi theo máy, cấu hình và số vòng. Không dùng kết quả này làm cam kết hiệu năng.
