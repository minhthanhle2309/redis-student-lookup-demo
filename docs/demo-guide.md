# Kịch bản seminar (5–7 phút)

## 0:00–0:45 — Bài toán

Giả sử SQLite lưu hồ sơ sinh viên. Khi ứng dụng liên tục tra cứu một MSSV, có thể giữ bản sao tạm thời trong Redis để giảm truy vấn lặp. SQLite vẫn là dữ liệu chính; cache có thể hết hạn hoặc bị xóa.

## 0:45–1:45 — Cache miss và hit

Chọn **6**, nhập `SV001`. Chương trình xóa cache trước demo: lần đầu hiện `CACHE MISS` vì lấy từ SQLite và lưu vào Redis; lần thứ hai hiện `CACHE HIT` vì đọc bản lưu. Chọn **2** để tự tra cứu lại nếu muốn.

## 1:45–2:30 — TTL

Chọn **7**. Demo đặt TTL 3 giây, chờ 4 giây rồi tra cứu lại. Lần sau là `CACHE MISS`, vì Redis tự bỏ khóa hết hạn. TTL mặc định của ứng dụng là 60 giây.

## 2:30–3:30 — Invalidation

Chọn **2**, tra `SV001` để tạo cache. Chọn **4** và cập nhật tên hoặc ngành. Tra lại bằng **2**: cache cũ đã bị xóa, kết quả mới được lấy từ SQLite (MISS). Xóa bằng **5** cũng xóa khóa cache liên quan.

## 3:30–5:00 — Benchmark

Chọn **8** với MSSV tồn tại. Chương trình đo trung bình 1.000 lần đọc SQLite trực tiếp và 1.000 lần đọc qua đường cache Redis bằng `time.perf_counter()`. Kết quả có thể chênh rất ít hoặc SQLite nhanh hơn do dữ liệu nhỏ, Redis chạy local và có overhead mạng/serialization. Đây không phải kết luận cho tải lớn.

## 5:00–6:00 — Kết luận và giới hạn

Cache hữu ích khi dữ liệu được đọc lặp lại, nhưng cần TTL và invalidation để giảm nguy cơ dữ liệu cũ. Demo dùng một tiến trình và một máy; chưa mô phỏng tải đồng thời, cache eviction, hoặc lỗi ghi giữa SQLite và Redis.

## Câu hỏi giảng viên có thể hỏi

- **Cache hit là gì?** Redis đã có khóa hợp lệ, ứng dụng trả dữ liệu từ Redis.
- **Cache miss là gì?** Redis không có khóa; ứng dụng đọc SQLite và lưu kết quả có TTL.
- **Vì sao không cache kết quả không tìm thấy?** Demo đơn giản tránh lưu trạng thái vắng mặt lâu; hệ thống lớn có thể dùng negative caching với TTL ngắn.
- **TTL có tác dụng gì?** Tự giới hạn thời gian giữ bản sao, tránh dữ liệu cũ tồn tại mãi.
- **Vì sao phải invalidation khi cập nhật/xóa?** Nếu không, Redis có thể trả hồ sơ cũ sau khi SQLite đã thay đổi.
- **Redis luôn nhanh hơn SQLite không?** Không. Kết quả tùy kích thước dữ liệu, tải, vị trí Redis và chi phí kết nối/serialization.
- **Dữ liệu gốc ở đâu?** SQLite; Redis chỉ là bản cache có thể tái tạo.
