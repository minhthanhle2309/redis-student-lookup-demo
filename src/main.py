"""Interactive terminal demo."""

import time
import redis

from src import database
from src.cache import StudentService, benchmark, cache_key, create_redis_client


def ask_required(label):
    while True:
        value = input(label).strip()
        if value:
            return value
        print("Giá trị không được để trống.")


def show_student(student):
    if not student:
        print("Không tìm thấy sinh viên. Kết quả không tồn tại cũng không được lưu vào cache.")
        return
    print(f"MSSV: {student['student_id']} | Họ tên: {student['name']} | Email: {student['email']} | Ngành: {student['major']}")


def run_demo(service, client):
    while True:
        print("\n=== Redis Student Lookup Demo ===")
        print("1. Xem danh sách sinh viên\n2. Tra cứu bằng MSSV\n3. Thêm sinh viên\n4. Cập nhật sinh viên")
        print("5. Xóa sinh viên\n6. Demo Cache Hit / Miss\n7. Demo TTL hết hạn\n8. Benchmark SQLite / Redis\n0. Thoát")
        choice = input("Chọn chức năng: ").strip()
        try:
            if choice == "1":
                for student in database.list_students():
                    show_student(student)
            elif choice == "2":
                student, status = service.get_student(ask_required("MSSV: "))
                print(f"CACHE {status}")
                show_student(student)
            elif choice == "3":
                sid = ask_required("MSSV: ")
                service.add_student(sid, ask_required("Họ tên: "), ask_required("Email: "), ask_required("Ngành: "))
                print("Đã thêm sinh viên.")
            elif choice == "4":
                sid = ask_required("MSSV cần cập nhật: ")
                if service.update_student(sid, ask_required("Họ tên mới: "), ask_required("Email mới: "), ask_required("Ngành mới: ")):
                    print("Đã cập nhật và xóa cache cũ.")
                else:
                    print("Không tìm thấy sinh viên.")
            elif choice == "5":
                sid = ask_required("MSSV cần xóa: ")
                print("Đã xóa và xóa cache." if service.delete_student(sid) else "Không tìm thấy sinh viên.")
            elif choice == "6":
                sid = ask_required("MSSV (ví dụ SV001): ")
                client.delete(cache_key(sid))
                for _ in range(2):
                    student, status = service.get_student(sid)
                    print(f"Lần tra cứu: CACHE {status}")
                    show_student(student)
            elif choice == "7":
                sid = ask_required("MSSV (ví dụ SV001): ")
                client.delete(cache_key(sid))
                short_service = StudentService(database, client, ttl=3)
                show_student(short_service.get_student(sid)[0])
                print("Cache TTL 3 giây; đang chờ...")
                time.sleep(4)
                _, status = short_service.get_student(sid)
                print(f"Sau khi TTL hết hạn: CACHE {status}")
            elif choice == "8":
                sid = ask_required("MSSV (ví dụ SV001): ")
                direct_ms, cache_ms = benchmark(database, service, sid)
                print(f"SQLite trực tiếp: {direct_ms:.4f} ms/lần; qua Redis (cache hit): {cache_ms:.4f} ms/lần, trung bình 1.000 lần.")
                print("Demo local với ít dữ liệu; độ trễ đo được nhỏ và Redis không nhất thiết nhanh hơn mọi trường hợp.")
            elif choice == "0":
                print("Kết thúc demo. Tạm biệt!")
                return
            else:
                print("Lựa chọn không hợp lệ. Hãy nhập số trong menu.")
        except database.StudentExistsError as exc:
            print(exc)
        except (ValueError, TypeError) as exc:
            print(f"Dữ liệu không hợp lệ: {exc}")


def main():
    database.initialize_database()
    client = create_redis_client()
    try:
        client.ping()
    except redis.RedisError:
        print("Không kết nối được Redis tại cấu hình hiện tại. Hãy chạy Docker Compose và kiểm tra cổng 6379.")
        return
    run_demo(StudentService(database, client), client)


if __name__ == "__main__":
    main()
