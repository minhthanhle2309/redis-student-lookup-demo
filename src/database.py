"""SQLite storage and student operations."""

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("STUDENT_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "students.db"))
SAMPLE_STUDENTS = [
    ("SV001", "Nguyen An", "an@example.edu", "Computer Science"),
    ("SV002", "Tran Binh", "binh@example.edu", "Information Systems"),
    ("SV003", "Le Chi", "chi@example.edu", "Data Science"),
]


class StudentExistsError(ValueError):
    """Raised when an MSSV is already in use."""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
            major TEXT NOT NULL)""")
        count = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        if count == 0:
            db.executemany("INSERT INTO students VALUES (?, ?, ?, ?)", SAMPLE_STUDENTS)


def list_students():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM students ORDER BY student_id")]


def get_student(student_id):
    with connect() as db:
        row = db.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
        return dict(row) if row else None


def add_student(student_id, name, email, major):
    try:
        with connect() as db:
            db.execute("INSERT INTO students VALUES (?, ?, ?, ?)", (student_id, name, email, major))
    except sqlite3.IntegrityError as exc:
        raise StudentExistsError(f"MSSV {student_id} đã tồn tại.") from exc


def update_student(student_id, name, email, major):
    with connect() as db:
        cursor = db.execute("UPDATE students SET name=?, email=?, major=? WHERE student_id=?",
                            (name, email, major, student_id))
        return cursor.rowcount > 0


def delete_student(student_id):
    with connect() as db:
        cursor = db.execute("DELETE FROM students WHERE student_id=?", (student_id,))
        return cursor.rowcount > 0
