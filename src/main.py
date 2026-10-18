"""Interactive terminal demo."""

import time
import redis

from src import database
from src.cache import StudentService, cache_key, create_redis_client


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


def show_lookup(service, student, status):
    info = service.last_lookup
    ttl = f"{info['ttl']} giây" if info["ttl"] is not None else "không có (MISS/BYPASS)"
    print(f"MSSV: {info['student_id']} | CACHE {status} | Redis key: {info['key']} | TTL còn lại: {ttl}")
    if status == "BYPASS":
        print("Redis không khả dụng; kết quả được đọc trực tiếp từ SQLite, không tính là cache HIT.")
    show_student(student)


def run_demo(service, client):
    while True:
        print("\n=== Redis Student Lookup Demo ===")
        print("1. Xem danh sách sinh viên\n2. Tra cứu bằng MSSV\n3. Thêm sinh viên\n4. Cập nhật sinh viên")
        print("5. Xóa sinh viên\n6. Demo Cache Hit / Miss\n7. Demo TTL hết hạn\n8. Hướng dẫn benchmark chi tiết\n0. Thoát")
        choice = input("Chọn chức năng: ").strip()
        try:
            if choice == "1":
                for student in database.list_students():
                    show_student(student)
            elif choice == "2":
                student, status = service.get_student(ask_required("MSSV: "))
                show_lookup(service, student, status)
            elif choice == "3":
                sid = ask_required("MSSV: ")
                service.add_student(sid, ask_required("Họ tên: "), ask_required("Email: "), ask_required("Ngành: "))
                print("Đã thêm sinh viên.")
                if not service.last_invalidation_ok:
                    print("Cảnh báo: Redis chưa xác nhận xóa khóa cũ.")
            elif choice == "4":
                sid = ask_required("MSSV cần cập nhật: ")
                if service.update_student(sid, ask_required("Họ tên mới: "), ask_required("Email mới: "), ask_required("Ngành mới: ")):
                    print("Đã cập nhật và xóa cache cũ.")
                    if not service.last_invalidation_ok:
                        print("Cảnh báo: Redis chưa xác nhận xóa khóa cũ; hãy kiểm tra Redis trước khi đọc lại.")
                else:
                    print("Không tìm thấy sinh viên.")
            elif choice == "5":
                sid = ask_required("MSSV cần xóa: ")
                if service.delete_student(sid):
                    print("Đã xóa sinh viên và khóa cache." if service.last_invalidation_ok else "Đã xóa sinh viên; Redis chưa xác nhận xóa khóa cache.")
                else:
                    print("Không tìm thấy sinh viên.")
            elif choice == "6":
                sid = ask_required("MSSV (ví dụ SV001): ")
                client.delete(cache_key(sid))
                for _ in range(2):
                    student, status = service.get_student(sid)
                    print(f"Lần tra cứu:")
                    show_lookup(service, student, status)
            elif choice == "7":
                sid = ask_required("MSSV (ví dụ SV001): ")
                client.delete(cache_key(sid))
                short_service = StudentService(database, client, ttl=3)
                student, status = short_service.get_student(sid)
                show_lookup(short_service, student, status)
                print("Cache TTL 3 giây; đang chờ...")
                time.sleep(4)
                student, status = short_service.get_student(sid)
                print("Sau khi TTL hết hạn:")
                show_lookup(short_service, student, status)
            elif choice == "8":
                print("Benchmark độc lập dùng database riêng: python -m scripts.benchmark")
            elif choice == "0":
                print("Kết thúc demo. Tạm biệt!")
                return
            else:
                print("Lựa chọn không hợp lệ. Hãy nhập số trong menu.")
        except database.StudentExistsError as exc:
            print(exc)
        except (ValueError, TypeError) as exc:
            print(f"Dữ liệu không hợp lệ: {exc}")
        except redis.RedisError:
            print("Redis vừa mất kết nối. Kiểm tra Redis rồi thử lại; dữ liệu SQLite không bị thay đổi bởi thao tác tra cứu.")


def main():
    database.initialize_database()
    client = create_redis_client()
    try:
        client.ping()
    except redis.RedisError:
        print("Cảnh báo: Redis chưa kết nối được. CLI sẽ tiếp tục đọc SQLite; lookup hiện trạng thái BYPASS cho đến khi Redis hoạt động.")
    run_demo(StudentService(database, client), client)


if __name__ == "__main__":
    main()
