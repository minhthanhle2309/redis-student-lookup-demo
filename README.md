# Redis Student Lookup Demo

Ứng dụng terminal nhỏ minh họa Redis cache khi tra cứu sinh viên bằng MSSV. SQLite lưu dữ liệu chính; Redis giữ bản sao có TTL.

## Chuẩn bị trên Windows

1. Cài [Git for Windows](https://git-scm.com/download/win), [Python 3.11 trở lên](https://www.python.org/downloads/windows/) (đánh dấu **Add Python to PATH**) và [Docker Desktop](https://www.docker.com/products/docker-desktop/). Mở Docker Desktop và đợi trạng thái chạy.
2. Mở PowerShell, thay `YOUR_GITHUB_URL` bằng URL repository thật:

   ```powershell
   git clone YOUR_GITHUB_URL
   cd redis-student-lookup-demo
   ```

3. Tạo và kích hoạt môi trường ảo:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   Nếu PowerShell chặn script, chỉ cho phép trong cửa sổ hiện tại bằng `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, rồi chạy lệnh kích hoạt lại.
4. Cài thư viện và khởi chạy Redis:

   ```powershell
   python -m pip install -r requirements.txt
   docker compose up -d
   docker compose ps
   docker compose exec redis redis-cli ping
   ```

   Lệnh cuối phải trả về `PONG`. Ứng dụng kết nối `localhost:6379` mặc định. Có thể cấu hình `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_TIMEOUT` và `CACHE_TTL_SECONDS` bằng biến môi trường.
5. Chạy ứng dụng và test:

   ```powershell
   python -m src.main
   python -m pytest
   ```

6. Chọn **0** để thoát ứng dụng. Khi demo xong:

   ```powershell
   docker compose down
   deactivate
   ```

## Lỗi thường gặp

- **Docker chưa chạy:** mở Docker Desktop, đợi khởi động xong, thử lại `docker compose up -d`.
- **Cổng 6379 đang được dùng:** xem tiến trình giữ cổng bằng `Get-NetTCPConnection -LocalPort 6379`; dừng dịch vụ Redis khác hoặc đổi cổng host trong `docker-compose.yml` rồi cập nhật `REDIS_PORT`.
- **Redis chưa khởi động / connection refused:** chạy `docker compose ps`, `docker compose logs redis` và kiểm tra `docker compose exec redis redis-cli ping`.
- **Không kích hoạt được virtualenv:** dùng lệnh `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` như bước 3. Có thể chạy trực tiếp `\.venv\Scripts\python.exe -m src.main` nếu chính sách vẫn chặn.
- **Sai phiên bản Python:** chạy `py -0p` để xem các phiên bản đã cài, cài Python 3.11+ và tạo lại `.venv`.

Ứng dụng tự tạo `data/students.db` và thêm dữ liệu mẫu khi cơ sở dữ liệu chưa có sinh viên. SQLite là dữ liệu chính; thao tác thêm/sửa/xóa sẽ xóa cache của MSSV liên quan.

## Demo nhanh

Chọn **6** để xóa cache và tra cứu cùng MSSV hai lần, **7** để xem TTL ngắn hết hạn, **8** để so sánh SQLite trực tiếp với luồng tra cứu cache. Kịch bản 5–7 phút và câu hỏi thường gặp ở [docs/demo-guide.md](docs/demo-guide.md).
