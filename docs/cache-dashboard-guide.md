# Hướng dẫn Redis Cache Dashboard

Dashboard là ứng dụng cục bộ riêng cho phần cache, mở tại `http://127.0.0.1:5001`. Session Demo vẫn chạy tại `http://127.0.0.1:5000`. Dashboard dùng `src.cache.StudentService` hiện có cho cache-aside, key, TTL và BYPASS; không có đường cache thứ hai. Nó chỉ gọi SQLite để tra cứu, không gọi hàm khởi tạo database và không thêm dữ liệu mẫu.

## Cài dependency và chạy

Từ thư mục project trong PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
docker compose up -d
docker compose exec redis redis-cli ping
```

Lệnh ping cần trả về `PONG`. Chạy dashboard trong terminal riêng:

```powershell
python -m src.cache_dashboard
```

Mở `http://127.0.0.1:5001`. Server chỉ bind vào loopback. Nếu database hiện tại chưa có bảng `students`, dashboard không tự sửa schema; cần dùng một database đã được khởi tạo sẵn bởi workflow hiện có. Có thể cấu hình `STUDENT_DB_PATH` trước khi chạy để trỏ tới database seminar đã chuẩn bị.

## Kịch bản MISS → HIT

1. Nhập một MSSV có thật, ví dụ `SV001`, rồi chọn **Tra cứu**.
2. Nếu Redis chưa có `student:SV001`, trạng thái là **MISS**. Nguồn kết quả là SQLite. Khi hồ sơ có thật, ứng dụng ghi vào Redis theo TTL đã cấu hình; dashboard hiển thị TTL Redis trả về.
3. Tra cứu lại cùng MSSV. Khi Redis còn key hợp lệ, trạng thái là **HIT** và nguồn lần này là Redis.
4. Thử một MSSV hợp lệ nhưng không có trong SQLite: trạng thái **MISS**, nguồn truy vấn là SQLite và khu vực kết quả nói không tìm thấy. Kết quả rỗng không được cache.

`BYPASS` là trạng thái riêng khi Redis lỗi và service hiện có chuyển sang SQLite. `ERROR` xuất hiện nếu thao tác không lấy được kết quả hợp lệ, ví dụ SQLite gặp lỗi. Dashboard không hiển thị stack trace hay chi tiết kết nối nội bộ.

## TTL hết hạn

TTL mặc định theo `CACHE_TTL_SECONDS` (60 giây). Để demo nhanh, dừng dashboard nếu đang chạy, đặt TTL ngắn trong cùng PowerShell rồi khởi động lại:

```powershell
$env:CACHE_TTL_SECONDS = "5"
python -m src.cache_dashboard
```

Xóa cache MSSV đó bằng nút **Xóa cache của MSSV này**, tra cứu một lần để tạo lại, rồi chọn **Kiểm tra TTL**. TTL hiển thị lấy trực tiếp từ Redis; chờ hơn 5 giây và kiểm tra lại để thấy key không tồn tại. Nút **Làm mới trạng thái** gửi PING mới tới Redis.

## Cache invalidation

Nhập MSSV cần demo rồi bấm **Xóa cache của MSSV này**. Dashboard dùng hàm invalidation hiện có và chỉ gửi lệnh xóa key `student:<MSSV>` đó. Các key Redis khác không bị động tới. Nếu key chưa tồn tại, UI nói rõ lệnh thành công nhưng không có key nào bị xóa. Tra cứu cùng MSSV tiếp theo thường là **MISS** nếu Redis đang hoạt động và hồ sơ còn trong SQLite.

## Demo BYPASS an toàn

Chỉ làm bước này nếu Redis đang chạy bằng Compose của project và không dùng chung container đó với ứng dụng khác. Trong một terminal:

```powershell
docker compose stop redis
```

Tra cứu MSSV có thật trên dashboard. Nếu Redis không truy cập được, UI hiện **BYPASS**, nguồn SQLite và sự kiện Redis lỗi. Khởi động lại đúng service sau demo:

```powershell
docker compose start redis
```

Không cần xóa database hay Redis database để trình diễn lỗi.

## Nhật ký và sơ đồ

Nhật ký hiển thị các phản hồi Redis, lần đọc SQLite, lần ghi cache, TTL và invalidation mà service xác nhận. Sơ đồ tô sáng nhánh HIT, MISS, BYPASS hoặc ERROR theo cùng trace. `-2` từ TTL nghĩa là key không tồn tại; `-1` nghĩa là key có nhưng không có thời hạn; giá trị không âm là TTL còn lại theo Redis.

## Dừng

Dừng dashboard bằng `Ctrl+C` ở cửa sổ đang chạy. Khi không còn cần Redis cho CLI hoặc Session Demo:

```powershell
docker compose down
deactivate
```

Không dùng `docker compose down -v`, `FLUSHDB` hoặc `FLUSHALL`.

## Giới hạn

Dashboard chỉ chạy trên máy cục bộ, dùng HTTP local và không phù hợp để đưa ra mạng. MSSV dashboard chấp nhận chữ ASCII, số, dấu gạch dưới hoặc gạch ngang, tối đa 32 ký tự. Kết nối Redis và TTL chỉ phản ánh thời điểm lệnh Redis trả lời; một key có thể hết hạn ngay sau khi được đọc. Nếu Redis hoặc SQLite chưa chạy, dashboard hiển thị trạng thái lỗi thay vì tạo dữ liệu thay thế.
