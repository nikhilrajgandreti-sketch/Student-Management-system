# Student Management System

A full-stack CRUD web application for managing student records, built with **FastAPI**, **MySQL** and plain **HTML/CSS**. Pages are rendered on the server with Jinja2 templates, so the frontend needs no JavaScript.

## Features

- **Create, read, update and delete** student records
- **Search** by name, email or course
- **Dashboard stats:** total students, number of distinct courses and average age
- **Validation on both sides:** HTML5 form constraints in the browser, plus server-side checks
- **Student photos:** upload, replace or remove a photo; avatars appear in the list (initials are shown when there is no photo)
- **Duplicate protection:** a unique email constraint with a friendly error message
- **Delete confirmation page** to prevent accidental deletions
- **Automatic setup:** the database and table are created on first start
- **Post/Redirect/Get pattern:** refreshing the page never resubmits a form
- **Secure queries:** parameterized SQL (`%s` placeholders) to prevent SQL injection

## Tech Stack

| Layer      | Technology                                  |
|------------|---------------------------------------------|
| Backend    | Python, FastAPI, Uvicorn                    |
| Templating | Jinja2                                      |
| Database   | MySQL 8, accessed with `mysql-connector-python` |
| Frontend   | HTML5, CSS3 (no JavaScript)                 |
| Config     | `python-dotenv` (environment variables)     |

## Project Structure

```
student-management/
├── main.py                  # FastAPI app: routes, validation and database code
├── requirements.txt         # Python dependencies
├── schema.sql               # Optional manual database setup
├── .env.example             # Template for environment variables
├── .gitignore
├── templates/
│   ├── base.html            # Shared layout
│   ├── index.html           # Student list, search and stats
│   ├── form.html            # Add / edit form (shared template)
│   └── confirm_delete.html  # Delete confirmation page
└── static/
    ├── style.css            # Styling
    └── uploads/             # Uploaded student photos (created automatically, not tracked by Git)
```

## Routes

HTML forms can only send `GET` and `POST`, so each action has its own URL.

| Operation | URL            | Method     | Description                                        |
|-----------|----------------|------------|----------------------------------------------------|
| Read      | `/`            | GET        | List all students; `?q=text` filters the results   |
| Create    | `/add`         | GET / POST | Show the form / insert a new student               |
| Update    | `/edit/{id}`   | GET / POST | Show the pre-filled form / update the student      |
| Delete    | `/delete/{id}` | GET / POST | Show the confirmation page / delete the student    |

## Database Schema

```sql
CREATE TABLE students (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    email      VARCHAR(150) NOT NULL UNIQUE,
    phone      VARCHAR(20)  NULL,
    course     VARCHAR(100) NOT NULL,
    age        INT          NOT NULL,
    photo      VARCHAR(255) NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Only the photo's file name is stored in the database. The image itself is saved in `static/uploads/` under a random name.

## Getting Started

### Prerequisites

- Python 3.10 or newer
- MySQL 8 (or compatible) installed and running
- A MySQL user that can create databases (for example `root`)

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/<your-username>/student-management.git
   cd student-management
   ```

2. **Create and activate a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux / macOS
   venv\Scripts\activate           # Windows
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure the database connection**

   Copy the example file and set your MySQL credentials:

   ```bash
   cp .env.example .env            # Linux / macOS
   copy .env.example .env          # Windows
   ```

   Then edit `.env`:

   ```env
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_NAME=student_db
   ```

   The `.env` file holds your real credentials and is excluded from Git. Never commit it.

5. **Run the application**

   ```bash
   uvicorn main:app --reload
   ```

   On startup the app creates the `student_db` database and the `students` table if they don't exist.

6. **Open the app** at http://127.0.0.1:8000

## Configuration

| Variable      | Default      | Description                  |
|---------------|--------------|------------------------------|
| `DB_HOST`     | `localhost`  | MySQL server host            |
| `DB_PORT`     | `3306`       | MySQL server port            |
| `DB_USER`     | `root`       | MySQL username               |
| `DB_PASSWORD` | *(empty)*    | MySQL password               |
| `DB_NAME`     | `student_db` | Database name (auto-created) |

## Validation Rules

| Field  | Rule                                |
|--------|-------------------------------------|
| Name   | Required, 2 to 100 characters       |
| Email  | Required, valid format, must be unique |
| Phone  | Optional, up to 20 characters       |
| Course | Required, 2 to 100 characters       |
| Age    | Required, whole number from 16 to 100 |
| Photo  | Optional, JPG, PNG or WEBP, up to 2 MB (the file type is checked by content, not by name) |


