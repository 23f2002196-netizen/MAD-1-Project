from contextlib import closing
import getpass
from pathlib import Path
import sqlite3
import re
import os
import secrets
from functools import wraps

from flask import (
    Flask, abort, g, redirect, render_template, request, session, url_for
)

from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
database_path = Path(__file__).parent / "examinationapp.db"

app.config["SECRET_KEY"] = (
    os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

with closing(sqlite3.connect(database_path)) as database:
    database.execute("PRAGMA foreign_keys = ON")

    # user login table 
    database.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,

            email TEXT NOT NULL UNIQUE
                CHECK (length(trim(email)) > 0),

            password_hash TEXT NOT NULL
                CHECK (length(password_hash) > 0),

            role TEXT NOT NULL
                CHECK (role IN ('Admin', 'Examiner', 'Student'))
        );
    """)
    
    # course table
    database.execute("""
        CREATE TABLE IF NOT EXISTS course (
            course_id INTEGER PRIMARY KEY,

            course_code INTEGER NOT NULL
                CHECK (
                    typeof(course_code) = 'integer'
                    AND course_code BETWEEN 1000 AND 9999
                ),

            course_name TEXT NOT NULL
                CHECK (
                    length(trim(course_name)) > 0
                    AND course_name NOT GLOB '*[^A-Za-z0-9 ]*'
                ),

            description TEXT
                CHECK (length(description) <= 200),

            status TEXT
                CHECK (length(status) <= 20)
        );
    """)

    # examination table 
    database.execute("""
        CREATE TABLE IF NOT EXISTS examination (
            exam_id INTEGER PRIMARY KEY,

            course_id INTEGER NOT NULL
                REFERENCES course(course_id),

            exam_name TEXT NOT NULL
                CHECK (length(trim(exam_name)) > 0),

            exam_type TEXT NOT NULL
                CHECK (
                    exam_type IN ('Viva', 'Practical', 'Project Demo', 'Assessment')
                ),

            duration INTEGER NOT NULL
                CHECK (
                    typeof(duration) = 'integer'
                    AND duration >= 0
                ),

            max_marks INTEGER NOT NULL
                CHECK (
                    typeof(max_marks) = 'integer'
                    AND max_marks >= 0
                ),

            slot_creation_start_date TEXT NOT NULL
                CHECK (
                    length(slot_creation_start_date) = 10
                    AND date(slot_creation_start_date, '+0 days')
                        IS slot_creation_start_date
                ),

            slot_creation_end_date TEXT NOT NULL
                CHECK (
                    length(slot_creation_end_date) = 10
                    AND date(slot_creation_end_date, '+0 days')
                        IS slot_creation_end_date
                ),

            slot_booking_start_date TEXT NOT NULL
                CHECK (
                    length(slot_booking_start_date) = 10
                    AND date(slot_booking_start_date, '+0 days')
                        IS slot_booking_start_date
                ),

            slot_booking_end_date TEXT NOT NULL
                CHECK (
                    length(slot_booking_end_date) = 10
                    AND date(slot_booking_end_date, '+0 days')
                        IS slot_booking_end_date
                ),

            status TEXT
                CHECK (length(status) <= 200),

            CHECK (
                slot_creation_end_date > slot_creation_start_date
            ),

            CHECK (
                slot_booking_end_date > slot_booking_start_date
            )
        );
    """)

    # examination rubric table
    database.execute("""
        CREATE TABLE IF NOT EXISTS examination_rubric (
            rubric_id INTEGER PRIMARY KEY,

            exam_id INTEGER NOT NULL
                REFERENCES examination(exam_id),

            criterion_name TEXT NOT NULL
                CHECK (length(trim(criterion_name)) BETWEEN 1 AND 100),

            max_marks REAL NOT NULL
                CHECK (
                    typeof(max_marks) IN ('integer', 'real')
                    AND max_marks >= 0
                ),

            weightage REAL NOT NULL
                CHECK (typeof(weightage) IN ('integer', 'real')),

            description TEXT
                CHECK (length(description) <= 200)
        );
    """)

    # exam slot table
    database.execute("""
        CREATE TABLE IF NOT EXISTS examination_slot (
            slot_id INTEGER PRIMARY KEY,

            exam_id INTEGER NOT NULL
                REFERENCES examination(exam_id),

            examiner_id INTEGER NOT NULL
                REFERENCES examiner_profile(examiner_id),

            slot_date TEXT NOT NULL
                CHECK (
                    length(slot_date) = 10
                    AND date(slot_date, '+0 days') IS slot_date
                ),

            start_time TEXT NOT NULL
                CHECK (
                    length(start_time) = 8
                    AND time(start_time) IS start_time
                    AND start_time BETWEEN '00:00:00' AND '23:59:59'
                ),

            end_time TEXT NOT NULL
                CHECK (
                    length(end_time) = 8
                    AND time(end_time) IS end_time
                    AND end_time BETWEEN '00:00:00' AND '23:59:59'
                ),

            max_student_capacity INTEGER NOT NULL
                CHECK (
                    typeof(max_student_capacity) = 'integer'
                    AND max_student_capacity > 0
                ),

            available_seats INTEGER NOT NULL
                CHECK (
                    typeof(available_seats) = 'integer'
                    AND available_seats >= 0
                ),

            status TEXT NOT NULL
                CHECK (
                    status IN ('Available', 'Full', 'Cancelled', 'Completed')
                ),

            CHECK (end_time > start_time),

            CHECK (available_seats <= max_student_capacity)
        );
    """)

    # booking table
    database.execute("""
            CREATE TABLE IF NOT EXISTS booking (
                booking_id INTEGER PRIMARY KEY,

                student_id INTEGER NOT NULL
                    REFERENCES student(student_id),

                slot_id INTEGER NOT NULL
                    REFERENCES examination_slot(slot_id),

                booking_date TEXT NOT NULL
                    CHECK (
                        length(booking_date) = 10
                        AND date(booking_date, '+0 days') IS booking_date
                    ),

                status TEXT NOT NULL
                    CHECK (status IN ('Booked', 'Cancelled', 'Completed'))
            );
        """)

    # examiner profile
    database.execute("""
        CREATE TABLE IF NOT EXISTS examiner_profile (
            examiner_id INTEGER PRIMARY KEY,

            user_id INTEGER NOT NULL
                REFERENCES users(user_id),

            name TEXT NOT NULL
                CHECK (length(trim(name)) BETWEEN 1 AND 150),

            contact_details TEXT,

            department TEXT
                CHECK (length(department) <= 100),

            status TEXT
                CHECK (length(status) <= 200)
        );
    """)

    # student 
    database.execute("""
        CREATE TABLE IF NOT EXISTS student (
            student_id INTEGER PRIMARY KEY,

            user_id INTEGER NOT NULL
                REFERENCES users(user_id),

            name TEXT NOT NULL
                CHECK (length(trim(name)) BETWEEN 1 AND 150),

            contact_details TEXT,

            status TEXT
                CHECK (length(status) <= 200)
        );
    """)

    database.commit() 

def account_is_enabled(database, user):
    if user["role"] == "Admin":
        return True

    if user["role"] == "Student":
        profile = database.execute(
            "SELECT status FROM student WHERE user_id = ?",
            (user["user_id"],)
        ).fetchone()

        return profile is not None and profile["status"] == "Active"

    if user["role"] == "Examiner":
        profile = database.execute(
            "SELECT status FROM examiner_profile WHERE user_id = ?",
            (user["user_id"],)
        ).fetchone()

        return profile is not None and profile["status"] == "Approved"

    return False

def create_student(email, password, name, contact_details=""):
    return _create_account(
        email=email,
        password=password,
        name=name,
        contact_details=contact_details,
        role="Student"
    )

def create_examiner(
    email, password, name, contact_details="", department=""
):
    return _create_account(
        email=email,
        password=password,
        name=name,
        contact_details=contact_details,
        role="Examiner",
        department=department
    )

def _create_account(
    email, password, name, contact_details, role, department=""
):
    # Normalize text, but preserve the password exactly as entered.
    email = email.strip().lower()
    name = name.strip()
    contact_details = contact_details.strip()
    department = department.strip()

    if role not in ("Student", "Examiner"):
        raise ValueError("Only students and examiners can register.")

    if not email:
        raise ValueError("Email is required.")

    if not password:
        raise ValueError("Password is required.")

    if not 1 <= len(name) <= 150:
        raise ValueError("Name must contain 1 to 150 characters.")

    if len(department) > 100:
        raise ValueError("Department must be at most 100 characters.")

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")

        with database:
            existing_user = database.execute(
                "SELECT user_id FROM users WHERE email = ?",
                (email,)
            ).fetchone()

            if existing_user:
                raise ValueError("An account with this email already exists.")

            password_hash = generate_password_hash(password)

            cursor = database.execute(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES (?, ?, ?)
                """,
                (email, password_hash, role)
            )

            user_id = cursor.lastrowid

            if role == "Student":
                database.execute(
                    """
                    INSERT INTO student (
                        user_id, name, contact_details, status
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, name, contact_details, "Active")
                )

            else:
                database.execute(
                    """
                    INSERT INTO examiner_profile (
                        user_id, name, contact_details, department, status
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, name, contact_details,
                        department, "Pending"
                    )
                )

    return user_id

@app.before_request
def load_logged_in_user():
    g.user = None
    user_id = session.get("user_id")

    if user_id is None:
        return

    with closing(sqlite3.connect(database_path)) as database:
        database.row_factory = sqlite3.Row

        user = database.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if user is None or not account_is_enabled(database, user):
            session.clear()
            return

        g.user = user

def require_role(*allowed_roles):
    def decorate(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("home"))

            if g.user["role"] not in allowed_roles:
                abort(403)

            return view_function(*args, **kwargs)

        return wrapped_view

    return decorate       

@app.route("/admin/courses", methods=["GET", "POST"])
@require_role("Admin")
def admin_courses():
    error = None

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        if request.method == "POST":
            course_name = request.form.get("course_name", "").strip()
            description = request.form.get("description", "").strip()
            status = request.form.get("status", "").strip()

            try:
                course_code = int(request.form.get("course_code", ""))

                database.execute(
                    """
                    INSERT INTO course (
                        course_code, course_name, description, status
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (course_code, course_name, description, status)
                )

                database.commit()
                return redirect(url_for("admin_courses"))

            except ValueError:
                error = "Enter a whole number for the course code."

            except sqlite3.IntegrityError:
                error = (
                    "Check the course details: code must be 1000–9999; "
                    "name must contain only English letters, numbers, "
                    "and spaces and cannot be blank; description must "
                    "be at most 200 characters and status at most 20."
                )

        courses = database.execute(
            "SELECT * FROM course ORDER BY course_id DESC"
        ).fetchall()

    return render_template(
        "admin_courses.html",
        courses=courses,
        error=error
    )

@app.cli.command("create-admin")
def create_admin():
    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")

        existing_admin = database.execute(
            "SELECT user_id FROM users WHERE role = ?",
            ("Admin",)
        ).fetchone()

        if existing_admin:
            print("An admin already exists. No changes made.")
            return

        email = input("Admin email: ").strip().lower()
        password = getpass("Admin password: ")
        confirmation = getpass("Confirm password: ")

        if not email or not password:
            print("Email and password are required.")
            return

        if password != confirmation:
            print("Passwords do not match. No account created.")
            return

        password_hash = generate_password_hash(password)

        try:
            database.execute(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES (?, ?, ?)
                """,
                (email, password_hash, "Admin")
            )
            database.commit()

        except sqlite3.IntegrityError:
            print("Account creation failed. Check whether the email exists.")
            return

        print("Admin account created.")

@app.route("/", methods=["GET", "POST"])
def home():
    error = None
    values = {}

    if request.method == "POST":
        # Keep non-password values so errors don't erase the form.
        values = {
            "email": request.form.get("email", "").strip().lower(),
            "name": request.form.get("name", "").strip(),
            "contact_details": request.form.get(
                "contact_details", ""
            ).strip(),
            "department": request.form.get("department", "").strip(),
            "role": request.form.get("role", "")
        }

        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")

        if values["role"] not in ("Student", "Examiner"):
            error = "Choose Student or Examiner."

        elif not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", values["email"]
        ):
            error = "Enter a valid email address."

        elif password != confirmation:
            error = "Passwords do not match."

        else:
            try:
                if values["role"] == "Student":
                    create_student(
                        email=values["email"],
                        password=password,
                        name=values["name"],
                        contact_details=values["contact_details"]
                    )

                else:
                    create_examiner(
                        email=values["email"],
                        password=password,
                        name=values["name"],
                        contact_details=values["contact_details"],
                        department=values["department"]
                    )

            except ValueError as exception:
                error = str(exception)

            except sqlite3.IntegrityError:
                error = (
                    "Registration could not be completed. "
                    "The email may already be registered."
                )

            else:
                return redirect(url_for("home", created="1"))

    return render_template(
        "index.html",
        error=error,
        values=values,
        created=request.args.get("created") == "1"
    )

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    with closing(sqlite3.connect(database_path)) as database:
        database.row_factory = sqlite3.Row

        user = database.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if (
            user is None
            or not password
            or not check_password_hash(user["password_hash"], password)
        ):
            return render_template(
                "index.html",
                error="Invalid email or password.",
                values={},
                created=False
            ), 401

        if not account_is_enabled(database, user):
            return render_template(
                "index.html",
                error=(
                    "This account is awaiting approval or is inactive. "
                    "Contact the admin."
                ),
                values={},
                created=False
            ), 403

        session.clear()
        session["user_id"] = user["user_id"]

    return redirect(url_for("dashboard"))

@app.route("/dashboard")
@require_role("Admin", "Examiner", "Student")
def dashboard():
    return render_template("dashboard.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))