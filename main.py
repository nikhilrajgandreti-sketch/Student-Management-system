"""Student Management System - FastAPI + MySQL (mysql.connector), no JavaScript.

Run:   uvicorn main:app --reload
Open:  http://127.0.0.1:8000
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "student_db")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    email      VARCHAR(150) NOT NULL UNIQUE,
    phone      VARCHAR(20)  NULL,
    course     VARCHAR(100) NOT NULL,
    age        INT          NOT NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

MESSAGES = {
    "added": "Student added successfully.",
    "updated": "Student updated successfully.",
    "deleted": "Student deleted.",
}


# ---------------------------------------------------------------
# Database helpers (mysql.connector)
# ---------------------------------------------------------------
def get_connection(with_db=True):
    config = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
    }
    if with_db:
        config["database"] = DB_NAME
    return mysql.connector.connect(**config)


def query(sql, params=()):
    """Run a SELECT and return a list of dict rows."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def execute(sql, params=()):
    """Run an INSERT / UPDATE / DELETE and return the number of affected rows."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        affected = cur.rowcount
        cur.close()
        return affected
    finally:
        conn.close()


def init_db():
    """Create the database and table if they do not exist yet."""
    conn = get_connection(with_db=False)
    try:
        cur = conn.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
    execute(CREATE_TABLE_SQL)


def get_student_or_404(student_id):
    rows = query("SELECT * FROM students WHERE id = %s", (student_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Student not found")
    return rows[0]


# ---------------------------------------------------------------
# Validation
# ---------------------------------------------------------------
def clean_and_validate(name, email, phone, course, age):
    """Return (cleaned_values_dict, list_of_error_messages)."""
    errors = []
    name, email, phone, course = name.strip(), email.strip(), phone.strip(), course.strip()

    if not 2 <= len(name) <= 100:
        errors.append("Name must be 2 to 100 characters.")
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 150:
        errors.append("Please enter a valid email address.")
    if len(phone) > 20:
        errors.append("Phone must be at most 20 characters.")
    if not 2 <= len(course) <= 100:
        errors.append("Course must be 2 to 100 characters.")

    age_value = None
    try:
        age_value = int(age)
        if not 16 <= age_value <= 100:
            errors.append("Age must be between 16 and 100.")
    except ValueError:
        errors.append("Age must be a number.")

    values = {
        "name": name,
        "email": email,
        "phone": phone,
        "course": course,
        "age": age_value if age_value is not None else age,
    }
    return values, errors


# ---------------------------------------------------------------
# App
# ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="Student Management System", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def redirect(url):
    # 303 makes the browser switch to GET after a form POST
    return RedirectResponse(url, status_code=303)


# ---------- READ (list + search) ----------
@app.get("/")
def home(request: Request, q: str = "", msg: str = ""):
    q = q.strip()
    if q:
        like = f"%{q}%"
        students = query(
            "SELECT * FROM students "
            "WHERE name LIKE %s OR email LIKE %s OR course LIKE %s "
            "ORDER BY id DESC",
            (like, like, like),
        )
    else:
        students = query("SELECT * FROM students ORDER BY id DESC")

    total = len(students)
    courses = len({s["course"].lower() for s in students})
    avg_age = round(sum(s["age"] for s in students) / total, 1) if total else None

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "students": students,
            "q": q,
            "message": MESSAGES.get(msg),
            "total": total,
            "courses": courses,
            "avg_age": avg_age,
        },
    )


# ---------- CREATE ----------
@app.get("/add")
def add_form(request: Request):
    return templates.TemplateResponse(
        request,
        "form.html",
        {"title": "Add Student", "action": "/add", "student": {}, "errors": []},
    )


@app.post("/add")
def add_student(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    course: str = Form(""),
    age: str = Form(""),
):
    values, errors = clean_and_validate(name, email, phone, course, age)

    if not errors:
        try:
            execute(
                "INSERT INTO students (name, email, phone, course, age) "
                "VALUES (%s, %s, %s, %s, %s)",
                (values["name"], values["email"], values["phone"] or None,
                 values["course"], values["age"]),
            )
            return redirect("/?msg=added")
        except mysql.connector.IntegrityError as err:
            if err.errno == 1062:  # duplicate entry
                errors.append("A student with this email already exists.")
            else:
                raise

    return templates.TemplateResponse(
        request,
        "form.html",
        {"title": "Add Student", "action": "/add", "student": values, "errors": errors},
    )


# ---------- UPDATE ----------
@app.get("/edit/{student_id}")
def edit_form(request: Request, student_id: int):
    student = get_student_or_404(student_id)
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "title": "Edit Student",
            "action": f"/edit/{student_id}",
            "student": student,
            "errors": [],
        },
    )


@app.post("/edit/{student_id}")
def edit_student(
    request: Request,
    student_id: int,
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    course: str = Form(""),
    age: str = Form(""),
):
    get_student_or_404(student_id)
    values, errors = clean_and_validate(name, email, phone, course, age)

    if not errors:
        try:
            execute(
                "UPDATE students SET name=%s, email=%s, phone=%s, course=%s, age=%s "
                "WHERE id=%s",
                (values["name"], values["email"], values["phone"] or None,
                 values["course"], values["age"], student_id),
            )
            return redirect("/?msg=updated")
        except mysql.connector.IntegrityError as err:
            if err.errno == 1062:
                errors.append("Another student already uses this email.")
            else:
                raise

    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "title": "Edit Student",
            "action": f"/edit/{student_id}",
            "student": values,
            "errors": errors,
        },
    )


# ---------- DELETE ----------
@app.get("/delete/{student_id}")
def delete_confirm(request: Request, student_id: int):
    student = get_student_or_404(student_id)
    return templates.TemplateResponse(request, "confirm_delete.html", {"student": student})


@app.post("/delete/{student_id}")
def delete_student(student_id: int):
    get_student_or_404(student_id)
    execute("DELETE FROM students WHERE id = %s", (student_id,))
    return redirect("/?msg=deleted")
