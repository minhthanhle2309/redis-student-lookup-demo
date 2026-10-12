from src.cache import StudentService
from src.main import run_demo


class Database:
    def get_student(self, sid):
        return {"student_id": sid, "name": "An", "email": "an@example.edu", "major": "CS"} if sid == "SV001" else None


class Redis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.data[key] = value

    def ttl(self, key):
        return 60

    def delete(self, key):
        self.data.pop(key, None)


def test_original_cli_lookup_and_exit_remain_usable(monkeypatch, capsys):
    answers = iter(["2", "SV001", "0"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    run_demo(StudentService(Database(), Redis()), Redis())
    output = capsys.readouterr().out
    assert "CACHE MISS" in output
    assert "student:SV001" in output
    assert "MSSV: SV001" in output
    assert "Tạm biệt" in output
