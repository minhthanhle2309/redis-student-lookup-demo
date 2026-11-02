# Hướng dẫn chạy `Run-RedisProject.ps1`

Script kiểm tra project Redis Student Lookup Demo từ PowerShell. Nó tự tạo `.venv` nếu chưa có, cài dependencies đã khai báo khi import chưa đủ, khởi động đúng hai service Compose (`redis`, `memcached`) khi Docker Engine sẵn sàng, rồi chạy các kiểm tra có thể xác nhận an toàn.

## Mở PowerShell tại project

Mở thư mục project trong File Explorer, chọn thanh địa chỉ, gõ `powershell` rồi Enter. Xác nhận đang ở thư mục có `Run-RedisProject.ps1`, `README.md` và `docker-compose.yml`:

```powershell
Get-Location
Get-ChildItem Run-RedisProject.ps1, README.md, docker-compose.yml
```

Hoặc nếu đã mở PowerShell, chuyển vào đường dẫn project của bạn bằng `Set-Location`.

## Chạy script

Mở Docker Desktop và chờ Docker Engine sẵn sàng trước khi chạy để các bước Redis, Memcached, cache-aside, Session Demo, Dashboard và benchmark có thể thực hiện:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\Run-RedisProject.ps1
```

Execution policy chỉ đổi cho cửa sổ PowerShell hiện tại. Script không nhận tham số. Chạy lại cùng lệnh để lặp lại kiểm tra.

## Cách đọc kết quả

Mỗi hạng mục hiển thị một trong các trạng thái:

- **PASS**: bước đó thực sự chạy và điều kiện kiểm tra đạt.
- **FAIL**: bước đã kiểm tra nhưng thất bại; lỗi được đưa vào danh sách cuối.
- **SKIP**: không thể hoặc không an toàn để chạy bước đó; phần chi tiết nêu lý do.

Bảng cuối có số PASS/FAIL/SKIP. `Docker` FAIL đồng nghĩa các bước cần container thường SKIP; không có PASS giả cho Redis, benchmark hoặc HTTP khi chưa kiểm tra. Script không tự mở browser. Nếu app được khởi chạy, bảng in URL và PID để bạn mở và dừng đúng process.

## Những bước script thực hiện

1. Xác nhận thư mục project và các source/config chính; đọc phiên bản Python, Docker CLI, Docker Engine và kiểm tra Compose config.
2. Tạo `.venv` nếu chưa có. Import `redis`, `pymemcache`, `pytest`; chỉ khi import thiếu, cài các package trong `requirements.txt`.
3. Chạy `docker compose up -d redis memcached`, kiểm tra Redis `PONG`, Memcached healthcheck và kết nối Redis từ Python.
4. Mở database đang được cấu hình bởi `STUDENT_DB_PATH` (hoặc `data/students.db`) ở chế độ SQLite read-only; chỉ kiểm tra bảng `students` và số dòng. Không khởi tạo schema/sample.
5. Compile Python files trong `src`, `scripts`, `tests` và chạy `python -m pytest -q` bằng interpreter trong `.venv`.
6. Kiểm tra cache-aside bằng một student record trong memory và key ngẫu nhiên trong namespace `seminar:project-check:`. Xác nhận MISS → HIT, cùng kết quả và TTL; xóa đúng key test ở cuối.
7. Khi Redis sẵn sàng và cổng `5000` trống, khởi chạy Session Demo trên `127.0.0.1:5000`; dùng credential mặc định từ source để kiểm tra login, `/status`, route `/protected`, TTL, logout và key đã bị vô hiệu hóa. Session ID không được in ra.
8. Khi Redis sẵn sàng và cổng `5001` trống, khởi chạy Dashboard và kiểm tra đúng `GET /` cùng `GET /api/status` đã có trong source.
9. Chạy Cache Performance Lab với payload nhỏ. Khi Redis/Memcached cùng sẵn sàng, script so sánh đủ ba mode; nếu thiếu backend vẫn chạy NO CACHE và từng mode có backend, các mode còn lại là SKIP. SQLite/Redis benchmark chạy từ bản sao script/database trong thư mục tạm và dùng prefix key riêng của lượt kiểm tra.

Nếu một cổng đang được dùng, script không dừng process đó; bước tương ứng được đánh dấu SKIP. Các app do script khởi chạy chạy nền để bạn có thể mở URL sau khi kiểm tra.

## Dữ liệu và file script tạo/thay đổi

- Có thể tạo `.venv` và cài các package có trong `requirements.txt` vào đó.
- `compileall` tạo bytecode `__pycache__`; pytest có thể tạo file tạm của riêng pytest.
- Docker Compose có thể tạo/chạy containers và network theo `docker-compose.yml`. Script không chạy `docker compose down`, `down -v`, `FLUSHDB` hoặc `FLUSHALL`.
- Cache-aside dùng MSSV giả trong memory, key có suffix ngẫu nhiên và xóa đúng key đó. Performance Lab dùng prefix ngẫu nhiên riêng cho Redis/Memcached và xóa đúng các key được tạo. Session test tạo phiên demo rồi gọi logout; helper cũng xóa chính xác key của phiên test nếu cần dọn dẹp.
- Database sinh viên đang cấu hình chỉ được đọc qua URI `mode=ro`; script không tự khởi tạo, thêm, sửa hoặc xóa hồ sơ.
- File log, report CSV/Markdown và bản sao project/database benchmark được đặt trong thư mục con ngẫu nhiên dưới Windows temporary directory. Bản sao benchmark chỉ đổi namespace Redis để giới hạn xóa trong key riêng của lần chạy. Đường dẫn chính xác được in ở đầu/cuối; script không ghi đè report cũ và không tự xóa thư mục này.
- Session Demo và Cache Dashboard được giữ chạy nền nếu khởi động thành công. PID/URL được in ra để dừng đúng process.

## Lỗi thường gặp

| Kết quả | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Python FAIL` | Thiếu `py` hoặc Python dưới 3.10. | Cài Python 3.10+ và bật Python Launcher, mở PowerShell mới rồi chạy lại. |
| `Docker FAIL` | Docker CLI có nhưng Docker Desktop/Engine chưa chạy, hoặc Compose config sai. | Mở Docker Desktop, đợi Engine sẵn sàng; chạy `docker info` và `docker compose config`, sau đó chạy lại script. |
| `Dependencies FAIL` | Không thể tải requirements hoặc package vẫn import lỗi. | Kiểm tra mạng/PyPI, rồi chạy `python -m pip install -r requirements.txt` trong `.venv`; chạy lại script. |
| `Redis`/`Memcached FAIL` | Container không khởi động, healthcheck chưa đạt, hoặc cổng host bị chiếm. | Xem `docker compose ps`, `docker compose logs --tail 100 redis`, `docker compose logs --tail 100 memcached`; giải phóng cổng mặc định `6379`/`11211`, rồi chạy lại. |
| `Database SKIP` | DB chưa tồn tại. | Script cố ý không tạo DB. Nếu muốn khởi tạo database demo, tự chạy CLI sau khi xác nhận đúng `STUDENT_DB_PATH`: `python -m src.main`. |
| `Database FAIL` | DB không đọc được hoặc thiếu bảng `students`. | Kiểm tra đường dẫn `STUDENT_DB_PATH` và quyền đọc. CLI có thể khởi tạo schema, nhưng chỉ chạy khi bạn chủ động muốn thay đổi đúng DB đó. |
| `Session Storage`/`Dashboard SKIP` | Redis chưa sẵn sàng, cổng đang bận hoặc auth environment được override. | Khắc phục Redis/cổng. Nếu `SESSION_DEMO_USERNAME` hoặc `SESSION_PASSWORD_HASH` đã đặt, script bỏ qua login với credential mặc định thay vì sửa cấu hình. |
| `Benchmark SKIP` | Một hoặc cả hai backend không sẵn sàng. | Khởi động Redis và Memcached, xác nhận health, rồi chạy lại. Cache Performance Lab `--mode no-cache` vẫn có thể chạy thủ công không cần service. |
| App bị chiếm cổng | Cổng `5000` (Session) hoặc `5001` (Dashboard) đang được process khác dùng. | Không để script dừng process đó. Xác định chủ sở hữu cổng; chỉ dừng nếu bạn biết đó là app cũ của project, rồi chạy lại. |

## Dừng sau seminar

Trong output, tìm PID được script in cạnh `Session Demo` và `Cache Dashboard`; dừng đúng PID bằng:

```powershell
$processId = [int](Read-Host "Nhap PID cua app do script khoi dong")
Stop-Process -Id $processId
```

Nhập đúng PID của app do chính lượt script này tạo và được in trong output. Khi muốn dừng Redis/Memcached containers:

```powershell
docker compose down
```

Lệnh này không xóa database sinh viên hoặc reports và an toàn hơn `docker compose down -v`; tuyệt đối không thêm `-v`.

## Chạy lại toàn bộ quy trình

Giảng viên mở PowerShell tại project root, mở Docker Desktop, sau đó copy/paste:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\Run-RedisProject.ps1
```

Đọc bảng tổng kết; chỉ coi một phần đã xác nhận khi trạng thái là PASS. Xem danh sách SKIP/FAIL, sửa nguyên nhân môi trường, rồi chạy lại. Script không commit hoặc push Git.
