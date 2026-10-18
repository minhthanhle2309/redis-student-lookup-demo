# Kết quả benchmark SQLite và Redis

Thời điểm đo: 2026-10-12T15:12:03.120465+00:00
Database riêng: `D:\redis-seminar-demo\redis-student-lookup-demo\data\benchmark_students.db`
Cấu hình: {'dataset_size': 1000, 'query_count_per_repetition': 500, 'repetitions': 3, 'total_queries_per_method': 1500, 'seed': 2026}

| Phương thức | Trung bình (ms) | Median/p50 (ms) | p95 (ms) | Tổng thời gian (ms) | Throughput (ops/s) | HIT | MISS | Tỷ lệ HIT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SQLite direct | 0.0175 | 0.0168 | 0.0222 | 26.32 | 57001.3 | 0 | 0 | — |
| Redis cold cache | 2.6010 | 2.4938 | 3.5593 | 3901.53 | 384.5 | 0 | 1500 | 0.0% |
| Redis warm cache | 1.4979 | 1.4523 | 1.9972 | 2246.92 | 667.6 | 1500 | 0 | 100.0% |

## Giới hạn đo

Đây là phép đo một tiến trình trên máy hiện tại; kết quả chịu ảnh hưởng của kích thước dataset, SQLite cache của hệ điều hành, Redis local, serialization, kết nối và tải nền. Tổng elapsed là tổng các khoảng tra cứu được bấm giờ; chuẩn bị dataset, xóa khóa để tạo cold cache, làm nóng cache, và overhead vòng lặp không nằm trong tổng đo. Redis không được đảm bảo nhanh hơn SQLite trong mọi cấu hình.
