"""Student Management System - FastAPI + MySQL (mysql.connector), no JavaScript.

Run:   uvicorn main:app --reload
Open:  http://127.0.0.1:8000
"""
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Student photos are saved here and served at /static/uploads/<filename>
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
MAX_PHOTO_BYTES = 2 * 1024 * 1024  # 2 MB

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
    photo      VARCHAR(255) NULL,
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
    ensure_photo_column()


def ensure_photo_column():
    """Add the `photo` column to a table that was created before photos existed."""
    rows = query(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'students' AND COLUMN_NAME = 'photo'",
        (DB_NAME,),
    )
    if not rows:
        execute("ALTER TABLE students ADD COLUMN photo VARCHAR(255) NULL")


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
# Photo helpers
# ---------------------------------------------------------------
def detect_image_ext(data):
    """Look at the first bytes of the file to find its real type (never trust the filename)."""
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def read_photo(upload):
    """Check an uploaded photo.

    Returns (photo, error). `photo` is (new_filename, file_bytes), or None when
    no file was chosen. `error` is a message when the file is not acceptable.
    """
    if upload is None or not upload.filename:
        return None, None
    data = upload.file.read(MAX_PHOTO_BYTES + 1)
    if not data:
        return None, None
    if len(data) > MAX_PHOTO_BYTES:
        return None, "Photo must be smaller than 2 MB."
    ext = detect_image_ext(data)
    if ext is None:
        return None, "Photo must be a JPG, PNG or WEBP image."
    return (f"{uuid.uuid4().hex}{ext}", data), None


def save_photo_file(photo):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename, data = photo
    (UPLOAD_DIR / filename).write_bytes(data)


def delete_photo_file(filename):
    if filename:
        (UPLOAD_DIR / Path(filename).name).unlink(missing_ok=True)


# ---------------------------------------------------------------
# App
# ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
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
    photo: UploadFile = File(None),
):
    values, errors = clean_and_validate(name, email, phone, course, age)
    new_photo, photo_error = read_photo(photo)
    if photo_error:
        errors.append(photo_error)

    if not errors:
        try:
            execute(
                "INSERT INTO students (name, email, phone, course, age, photo) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (values["name"], values["email"], values["phone"] or None,
                 values["course"], values["age"], new_photo[0] if new_photo else None),
            )
        except mysql.connector.IntegrityError as err:
            if err.errno == 1062:  # duplicate entry
                errors.append("A student with this email already exists.")
            else:
                raise
        else:
            if new_photo:
                save_photo_file(new_photo)
            return redirect("/?msg=added")

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
    photo: UploadFile = File(None),
    remove_photo: str = Form(""),
):
    current = get_student_or_404(student_id)
    values, errors = clean_and_validate(name, email, phone, course, age)
    new_photo, photo_error = read_photo(photo)
    if photo_error:
        errors.append(photo_error)

    if not errors:
        # Decide which photo the student ends up with
        photo_name = current["photo"]
        if new_photo:
            photo_name = new_photo[0]          # replaced with the new upload
        elif remove_photo:
            photo_name = None                  # "Remove current photo" ticked

        try:
            execute(
                "UPDATE students SET name=%s, email=%s, phone=%s, course=%s, age=%s, "
                "photo=%s WHERE id=%s",
                (values["name"], values["email"], values["phone"] or None,
                 values["course"], values["age"], photo_name, student_id),
            )
        except mysql.connector.IntegrityError as err:
            if err.errno == 1062:
                errors.append("Another student already uses this email.")
            else:
                raise
        else:
            if new_photo:
                save_photo_file(new_photo)
            if photo_name != current["photo"]:
                delete_photo_file(current["photo"])   # remove the old image file
            return redirect("/?msg=updated")

    values["photo"] = current["photo"]  # keep showing the current photo on the form
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
    student = get_student_or_404(student_id)
    execute("DELETE FROM students WHERE id = %s", (student_id,))
    delete_photo_file(student["photo"])
    return redirect("/?msg=deleted")