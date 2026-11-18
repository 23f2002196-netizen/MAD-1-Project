from contextlib import closing
from getpass import getpass
from pathlib import Path
import sqlite3
import re
import os
import secrets
from functools import wraps
from datetime import date, time, datetime
from flask import (
    Flask, abort, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import generate_password_hash, check_password_hash
import math

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

            slot_creation_start_date TEXT
                CHECK (
                    length(slot_creation_start_date) = 10
                    AND date(slot_creation_start_date, '+0 days')
                        IS slot_creation_start_date
                ),

            slot_creation_end_date TEXT
                CHECK (
                    length(slot_creation_end_date) = 10
                    AND date(slot_creation_end_date, '+0 days')
                        IS slot_creation_end_date
                ),

            slot_booking_start_date TEXT
                CHECK (
                    length(slot_booking_start_date) = 10
                    AND date(slot_booking_start_date, '+0 days')
                        IS slot_booking_start_date
                ),

            slot_booking_end_date TEXT
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

            examiner_id INTEGER
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

    # student user id - unique
    database.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS student_user_unique
        ON student(user_id)
    """)

    # examiner user id - unique
    database.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS examiner_user_unique
        ON examiner_profile(user_id)
    """)

    # evaluation table
    database.execute("""
        CREATE TABLE IF NOT EXISTS evaluation (
            evaluation_id INTEGER PRIMARY KEY,

            booking_id INTEGER NOT NULL UNIQUE
                REFERENCES booking(booking_id),

            status TEXT NOT NULL DEFAULT 'Draft'
                CHECK (status IN ('Draft', 'Submitted')),

            submitted_by INTEGER
                REFERENCES examiner_profile(examiner_id),

            submitted_at TEXT
        )
    """)

    # evaluation score table
    database.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_score (
            evaluation_id INTEGER NOT NULL
                REFERENCES evaluation(evaluation_id),

            rubric_id INTEGER NOT NULL
                REFERENCES examination_rubric(rubric_id),

            marks_awarded REAL NOT NULL
                CHECK (
                    typeof(marks_awarded) IN ('integer', 'real')
                    AND marks_awarded >= 0
                ),

            PRIMARY KEY (evaluation_id, rubric_id)
        )
    """)


    evaluation_columns = {
        row[1]
        for row in database.execute("PRAGMA table_info(evaluation)")
    }

    if "is_published" not in evaluation_columns:
        database.execute("""
            ALTER TABLE evaluation
            ADD COLUMN is_published INTEGER NOT NULL DEFAULT 0
                CHECK (is_published IN (0, 1))
        """)

    # examiner assignment table
    database.execute("""
        CREATE TABLE IF NOT EXISTS examiner_assignment (
            exam_id INTEGER NOT NULL
                REFERENCES examination(exam_id),

            examiner_id INTEGER NOT NULL
                REFERENCES examiner_profile(examiner_id),

            PRIMARY KEY (exam_id, examiner_id)
        )
    """)

    database.commit() 

def validate_awarded_marks(raw_value, maximum):
    try:
        marks = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError("Enter a number for the awarded marks.")

    if not math.isfinite(marks):
        raise ValueError("Marks must be a finite number.")

    if marks < 0 or marks > maximum:
        raise ValueError(
            f"Awarded marks must be between 0 and {maximum}."
        )

    return marks

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
    return redirect(url_for("admin_dashboard", _anchor="courses"))

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
    if g.user["role"] == "Admin":
        return redirect(url_for("admin_dashboard"))

    if g.user["role"] == "Examiner":
        return redirect(url_for("examiner_dashboard"))

    return redirect(url_for("student_dashboard"))

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route(
    "/admin/courses/new",
    defaults={"course_id": None},
    methods=["GET", "POST"]
)
@app.route(
    "/admin/courses/<int:course_id>/edit",
    methods=["GET", "POST"]
)
@require_role("Admin")
def add_course(course_id):
    error = None
    delete_mode = (
        course_id is not None
        and request.args.get("mode") == "delete"
    )

    values = {
        "course_code": "",
        "course_name": "",
        "description": "",
        "active": False
    }

    if (
        request.method == "POST"
        and request.form.get("action") == "cancel"
    ):
        return redirect(url_for("admin_dashboard"))

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        if course_id is not None:
            course = database.execute(
                "SELECT * FROM course WHERE course_id = ?",
                (course_id,)
            ).fetchone()

            if course is None:
                abort(404)

            values = {
                "course_code": course["course_code"],
                "course_name": course["course_name"],
                "description": course["description"] or "",
                "active": course["status"] == "Active"
            }

        if request.method == "POST":
            if request.form.get("action") == "delete":
                if course_id is None:
                    abort(400)

                try:
                    database.execute(
                        "DELETE FROM course WHERE course_id = ?",
                        (course_id,)
                    )
                    database.commit()

                except sqlite3.IntegrityError:
                    database.rollback()
                    delete_mode = True
                    error = (
                        "This course has related records and cannot "
                        "be deleted."
                    )

                else:
                    return redirect(url_for("admin_dashboard"))

            else:
                values = {
                    "course_code": request.form.get(
                        "course_code", ""
                    ).strip(),
                    "course_name": request.form.get(
                        "course_name", ""
                    ).strip(),
                    "description": request.form.get(
                        "description", ""
                    ).strip(),
                    "active": request.form.get("active") == "1"
                }

                status = "Active" if values["active"] else "Inactive"

                try:
                    course_code = int(values["course_code"])

                    if course_id is None:
                        database.execute(
                            """
                            INSERT INTO course (
                                course_code, course_name,
                                description, status
                            )
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                course_code,
                                values["course_name"],
                                values["description"],
                                status
                            )
                        )

                    else:
                        database.execute(
                            """
                            UPDATE course
                            SET course_code = ?,
                                course_name = ?,
                                description = ?,
                                status = ?
                            WHERE course_id = ?
                            """,
                            (
                                course_code,
                                values["course_name"],
                                values["description"],
                                status,
                                course_id
                            )
                        )

                    database.commit()

                except ValueError:
                    error = "Course code must be a whole number."

                except sqlite3.IntegrityError:
                    database.rollback()
                    error = (
                        "Use a code from 1000 to 9999, a nonempty "
                        "name containing English letters, numbers "
                        "and spaces, and a description of at most "
                        "200 characters."
                    )

                else:
                    return redirect(url_for("admin_dashboard"))

    return render_template(
        "course.html",
        values=values,
        course_id=course_id,
        delete_mode=delete_mode,
        error=error
    )

def validate_booking_window(start_text, end_text, status):
    allowed_statuses = (
        "Draft", "Slot Creation", "Booking Open", "Closed", "Completed"
    )

    if status not in allowed_statuses:
        raise ValueError("Choose a valid examination status.")

    if bool(start_text) != bool(end_text):
        raise ValueError("Enter both booking dates, or leave both empty.")

    if not start_text:
        if status == "Booking Open":
            raise ValueError(
                "Set both booking dates before opening booking."
            )
        return None, None

    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except ValueError:
        raise ValueError("Enter valid booking dates.")

    if end <= start:
        raise ValueError(
            "Booking end date must be after the start date."
        )

    return start.isoformat(), end.isoformat()

@app.route(
    "/admin/examinations/new",
    defaults={"exam_id": None},
    methods=["GET", "POST"]
)

@app.route(
    "/admin/examinations/<int:exam_id>/edit",
    methods=["GET", "POST"]
)

@require_role("Admin")
def examination_form(exam_id):
    error = None

    delete_mode = (
        exam_id is not None
        and request.args.get("mode") == "delete"
    )

    values = {
        "course_code": "",
        "exam_name": "",
        "exam_type": "",
        "duration": "",
        "max_marks": "",
        "slot_booking_start_date": "",
        "slot_booking_end_date": "",
        "status": "Draft"
    }

    if (
        request.method == "POST"
        and request.form.get("action") == "cancel"
    ):
        return redirect(url_for("admin_dashboard"))

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        if exam_id is not None:
            examination = database.execute(
                """
                SELECT e.*, c.course_code
                FROM examination e
                JOIN course c ON c.course_id = e.course_id
                WHERE e.exam_id = ?
                """,
                (exam_id,)
            ).fetchone()

            if examination is None:
                abort(404)

            values = dict(examination)

        if (
            request.method == "POST"
            and request.form.get("action") == "delete"
        ):
            if exam_id is None:
                abort(400)

            try:
                database.execute(
                    "DELETE FROM examination WHERE exam_id = ?",
                    (exam_id,)
                )
                database.commit()

            except sqlite3.IntegrityError:
                database.rollback()
                delete_mode = True
                error = (
                    "This examination has related records "
                    "and cannot be deleted."
                )

            else:
                return redirect(url_for("admin_dashboard"))

        elif request.method == "POST":
            action = request.form.get("action")

            if action not in ("update", "slots"):
                abort(400)

            values = {
                "course_code": request.form.get(
                    "course_code", ""
                ).strip(),
                "exam_name": request.form.get("exam_name", "").strip(),
                "exam_type": request.form.get("exam_type", ""),
                "duration": request.form.get("duration", ""),
                "max_marks": request.form.get("max_marks", ""),
                "slot_booking_start_date": request.form.get(
                    "slot_booking_start_date", ""
                ).strip(),
                "slot_booking_end_date": request.form.get(
                    "slot_booking_end_date", ""
                ).strip(),
                "status": request.form.get("status", "")
            }

            try:
                try:
                    course_code = int(values["course_code"])
                    duration = int(values["duration"])
                    max_marks = int(values["max_marks"])
                except ValueError:
                    raise ValueError(
                        "Course code, duration and maximum marks "
                        "must be whole numbers."
                    )

                if duration < 0 or max_marks < 0:
                    raise ValueError(
                        "Duration and maximum marks cannot be negative."
                    )

                if not values["exam_name"]:
                    raise ValueError("Examination name is required.")

                if values["exam_type"] not in (
                    "Viva", "Practical", "Project Demo", "Assessment"
                ):
                    raise ValueError("Choose a valid examination type.")

                booking_start, booking_end = validate_booking_window(
                    values["slot_booking_start_date"],
                    values["slot_booking_end_date"],
                    values["status"]
                )

                courses = database.execute(
                    "SELECT course_id FROM course WHERE course_code = ?",
                    (course_code,)
                ).fetchall()

                if len(courses) != 1:
                    raise ValueError(
                        "Course code must identify exactly one "
                        "existing course."
                    )

                fields = (
                    courses[0]["course_id"],
                    values["exam_name"],
                    values["exam_type"],
                    duration,
                    max_marks,
                    booking_start,
                    booking_end,
                    values["status"]
                )

                if exam_id is None:
                    cursor = database.execute(
                        """
                        INSERT INTO examination (
                            course_id, exam_name, exam_type, duration,
                            max_marks, slot_booking_start_date,
                            slot_booking_end_date, status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        fields
                    )

                    saved_exam_id = cursor.lastrowid

                else:
                    database.execute(
                        """
                        UPDATE examination
                        SET course_id = ?,
                            exam_name = ?,
                            exam_type = ?,
                            duration = ?,
                            max_marks = ?,
                            slot_booking_start_date = ?,
                            slot_booking_end_date = ?,
                            status = ?
                        WHERE exam_id = ?
                        """,
                        fields + (exam_id,)
                    )

                    saved_exam_id = exam_id

                database.commit()

            except ValueError as exception:
                error = str(exception)

            except sqlite3.IntegrityError:
                database.rollback()
                error = "The examination could not be saved."

            else:
                if action == "slots":
                    return redirect(
                        url_for(
                            "examination_slots",
                            exam_id=saved_exam_id
                        )
                    )

                return redirect(url_for("admin_dashboard"))

    return render_template(
        "examination_form.html",
        values=values,
        error=error,
        exam_id=exam_id,
        delete_mode=delete_mode
    )

@app.route(
    "/admin/examinations/<int:exam_id>/slots/<int:slot_id>/edit",
    methods=["GET", "POST"]
)

@app.route(
    "/admin/examinations/<int:exam_id>/slots",
    defaults={"slot_id": None},
    methods=["GET", "POST"]
)

@require_role("Admin")
def examination_slots(exam_id, slot_id):
    error = None
    allowed_statuses = ("Available", "Full", "Cancelled", "Completed")

    values = {
        "slot_date": "",
        "start_time": "",
        "end_time": "",
        "max_student_capacity": "",
        "status": "Available"
    }

    if (
        request.method == "POST"
        and request.form.get("action") == "cancel"
    ):
        return redirect(
            url_for("examination_form", exam_id=exam_id)
        )

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        examination = database.execute(
            "SELECT exam_id, exam_name FROM examination WHERE exam_id = ?",
            (exam_id,)
        ).fetchone()

        if examination is None:
            abort(404)

        if slot_id is not None:
            slot = database.execute(
                """
                SELECT * FROM examination_slot
                WHERE slot_id = ? AND exam_id = ?
                """,
                (slot_id, exam_id)
            ).fetchone()

            if slot is None:
                abort(404)

            values = dict(slot)

        if request.method == "POST":
            values = {
                "slot_date": request.form.get("slot_date", ""),
                "start_time": request.form.get("start_time", ""),
                "end_time": request.form.get("end_time", ""),
                "max_student_capacity": request.form.get(
                    "max_student_capacity", ""
                ),
                "status": request.form.get("status", "")
            }

            try:
                slot_date = date.fromisoformat(values["slot_date"])
                start = time.fromisoformat(values["start_time"])
                end = time.fromisoformat(values["end_time"])
                capacity = int(values["max_student_capacity"])
                status = values["status"]

                if (
                    start.tzinfo is not None
                    or end.tzinfo is not None
                    or start.microsecond
                    or end.microsecond
                ):
                    raise ValueError(
                        "Use local times with whole seconds."
                    )

                if end <= start:
                    raise ValueError(
                        "End time must be later than start time."
                    )

                if capacity <= 0:
                    raise ValueError("Capacity must be greater than zero.")

                if status not in allowed_statuses:
                    raise ValueError("Choose a valid status.")

                # Read bookings and save the slot in one transaction.
                database.execute("BEGIN IMMEDIATE")

                occupied = database.execute(
                    """
                    SELECT COUNT(*)
                    FROM booking
                    WHERE slot_id = ?
                      AND status IN ('Booked', 'Completed')
                    """,
                    (slot_id,)
                ).fetchone()[0]

                if capacity < occupied:
                    raise ValueError(
                        "Capacity cannot be below existing bookings."
                    )

                available_seats = capacity - occupied

                if status == "Full" and available_seats > 0:
                    raise ValueError(
                        "A slot can be Full only when no seats remain."
                    )

                if status == "Available" and available_seats == 0:
                    status = "Full"

                if slot_id is None:
                    database.execute(
                        """
                        INSERT INTO examination_slot (
                            exam_id, slot_date, start_time, end_time,
                            max_student_capacity, available_seats, status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            exam_id,
                            slot_date.isoformat(),
                            start.isoformat(),
                            end.isoformat(),
                            capacity,
                            available_seats,
                            status
                        )
                    )

                else:
                    database.execute(
                        """
                        UPDATE examination_slot
                        SET slot_date = ?,
                            start_time = ?,
                            end_time = ?,
                            max_student_capacity = ?,
                            available_seats = ?,
                            status = ?
                        WHERE slot_id = ? AND exam_id = ?
                        """,
                        (
                            slot_date.isoformat(),
                            start.isoformat(),
                            end.isoformat(),
                            capacity,
                            available_seats,
                            status,
                            slot_id,
                            exam_id
                        )
                    )

                database.commit()

            except ValueError as exception:
                database.rollback()
                error = str(exception)

            except sqlite3.IntegrityError:
                database.rollback()
                error = "The slot could not be saved."

            else:
                return redirect(
                    url_for("examination_slots", exam_id=exam_id)
                )

        slots = database.execute(
            """
            SELECT * FROM examination_slot
            WHERE exam_id = ?
            ORDER BY slot_date, start_time
            """,
            (exam_id,)
        ).fetchall()

    return render_template(
        "examination_slots.html",
        examination=examination,
        values=values,
        slots=slots,
        slot_id=slot_id,
        allowed_statuses=allowed_statuses,
        error=error
    )

@app.route(
    "/admin/examinations/<int:exam_id>/rubrics",
    defaults={"rubric_id": None},
    methods=["GET", "POST"]
)
@app.route(
    "/admin/examinations/<int:exam_id>/rubrics/<int:rubric_id>/edit",
    methods=["GET", "POST"]
)
@require_role("Admin")

def admin_rubrics(exam_id, rubric_id):
    error = None
    values = {
        "criterion_name": "",
        "max_marks": "",
        "weightage": "",
        "description": ""
    }

    if (
        request.method == "POST"
        and request.form.get("action") == "cancel"
    ):
        return redirect(url_for("dashboard"))

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        examination = database.execute(
            "SELECT exam_id, exam_name FROM examination WHERE exam_id = ?",
            (exam_id,)
        ).fetchone()

        if examination is None:
            abort(404)

        if rubric_id is not None:
            rubric = database.execute(
                """
                SELECT * FROM examination_rubric
                WHERE rubric_id = ? AND exam_id = ?
                """,
                (rubric_id, exam_id)
            ).fetchone()

            if rubric is None:
                abort(404)

            values = dict(rubric)

        if request.method == "POST":
            values = {
                "criterion_name": request.form.get(
                    "criterion_name", ""
                ).strip(),
                "max_marks": request.form.get("max_marks", ""),
                "weightage": request.form.get("weightage", ""),
                "description": request.form.get(
                    "description", ""
                ).strip()
            }

            try:
                max_marks = float(values["max_marks"])
                weightage = float(values["weightage"])

                if not math.isfinite(max_marks) or not math.isfinite(weightage):
                    raise ValueError(
                        "Maximum marks and weightage must be finite numbers."
                    )

                if max_marks < 0:
                    raise ValueError("Maximum marks cannot be negative.")

                if not 1 <= len(values["criterion_name"]) <= 100:
                    raise ValueError(
                        "Criterion name must contain 1 to 100 characters."
                    )

                if len(values["description"]) > 200:
                    raise ValueError(
                        "Description must be at most 200 characters."
                    )

                if rubric_id is None:
                    database.execute(
                        """
                        INSERT INTO examination_rubric (
                            exam_id, criterion_name,
                            max_marks, weightage, description
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            exam_id,
                            values["criterion_name"],
                            max_marks,
                            weightage,
                            values["description"]
                        )
                    )

                else:
                    database.execute(
                        """
                        UPDATE examination_rubric
                        SET criterion_name = ?,
                            max_marks = ?,
                            weightage = ?,
                            description = ?
                        WHERE rubric_id = ? AND exam_id = ?
                        """,
                        (
                            values["criterion_name"],
                            max_marks,
                            weightage,
                            values["description"],
                            rubric_id,
                            exam_id
                        )
                    )

                database.commit()

            except ValueError as exception:
                error = str(exception)

            except sqlite3.IntegrityError:
                error = "The rubric criterion could not be saved."

            else:
                return redirect(
                    url_for("admin_rubrics", exam_id=exam_id)
                )

        rubrics = database.execute(
            """
            SELECT * FROM examination_rubric
            WHERE exam_id = ?
            ORDER BY rubric_id
            """,
            (exam_id,)
        ).fetchall()

    return render_template(
        "admin_rubrics.html",
        examination=examination,
        rubric_id=rubric_id,
        values=values,
        rubrics=rubrics,
        error=error
    )

@app.route(
    "/admin/examiners/<int:examiner_id>/review",
    methods=["GET", "POST"]
)
@require_role("Admin")
def review_examiner(examiner_id):
    error = None

    if (
        request.method == "POST"
        and request.form.get("action") == "close"
    ):
        return redirect(url_for("dashboard"))

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        examiner = database.execute(
            """
            SELECT examiner_profile.*
            FROM examiner_profile
            JOIN users
                ON users.user_id = examiner_profile.user_id
            WHERE examiner_profile.examiner_id = ?
              AND users.role = 'Examiner'
            """,
            (examiner_id,)
        ).fetchone()

        if examiner is None:
            abort(404)

        selected = {
            "Approved": "approve",
            "Rejected": "reject"
        }.get(examiner["status"], "")

        if request.method == "POST":
            selected = request.form.get("decision", "")

            if selected not in ("approve", "reject"):
                error = "Choose Approve or Reject."

            else:
                new_status = (
                    "Approved" if selected == "approve" else "Rejected"
                )

                database.execute(
                    """
                    UPDATE examiner_profile
                    SET status = ?
                    WHERE examiner_id = ?
                    """,
                    (new_status, examiner_id)
                )
                database.commit()

                return redirect(url_for("dashboard"))

    return render_template(
        "review_examiner.html",
        examiner=examiner,
        selected=selected,
        error=error
    )

@app.route("/admin/students/bookings", methods=["GET"])
@require_role("Admin")
def registered_students():
    if request.args.get("action") == "close":
        return redirect(url_for("dashboard"))

    student_id_text = request.args.get("student_id", "").strip()
    exam_id_text = request.args.get("exam_id", "").strip()
    searched = "student_id" in request.args

    error = None
    student = None
    bookings = []

    with closing(sqlite3.connect(database_path)) as database:
        database.row_factory = sqlite3.Row

        examinations = database.execute(
            """
            SELECT exam_id, exam_name
            FROM examination
            ORDER BY exam_id
            """
        ).fetchall()

        if searched:
            try:
                student_id = int(student_id_text)
                exam_id = int(exam_id_text) if exam_id_text else None

                if student_id <= 0:
                    raise ValueError

                if exam_id is not None and exam_id <= 0:
                    raise ValueError

            except ValueError:
                error = (
                    "Enter a positive whole-number student ID "
                    "and choose an examination if needed."
                )

            else:
                student = database.execute(
                    """
                    SELECT student_id, name
                    FROM student
                    WHERE student_id = ?
                    """,
                    (student_id,)
                ).fetchone()

                if student is None:
                    error = "No student exists with that student ID."

                elif (
                    exam_id is not None
                    and exam_id not in {
                        examination["exam_id"]
                        for examination in examinations
                    }
                ):
                    error = "Choose an existing examination."

                else:
                    query = """
                        SELECT
                            booking.booking_id,
                            examination.course_id,
                            examination.exam_id,
                            booking.slot_id,
                            booking.booking_date,
                            booking.status
                        FROM booking
                        JOIN examination_slot
                            ON examination_slot.slot_id = booking.slot_id
                        JOIN examination
                            ON examination.exam_id = examination_slot.exam_id
                        WHERE booking.student_id = ?
                    """

                    parameters = [student_id]

                    if exam_id is not None:
                        query += " AND examination.exam_id = ?"
                        parameters.append(exam_id)

                    query += """
                        ORDER BY booking.booking_date DESC,
                                 booking.booking_id DESC
                    """

                    bookings = database.execute(
                        query, parameters
                    ).fetchall()

    return render_template(
        "registered_students.html",
        examinations=examinations,
        student=student,
        bookings=bookings,
        student_id_text=student_id_text,
        exam_id_text=exam_id_text,
        searched=searched,
        error=error
    )

@app.route("/admin/dashboard")
@require_role("Admin")
def admin_dashboard():
    section = request.args.get("section", "all")

    if section not in ("all", "courses", "examinations", "examiners"):
        abort(400)

    with closing(sqlite3.connect(database_path)) as database:
        database.row_factory = sqlite3.Row

        courses = database.execute(
            "SELECT * FROM course ORDER BY course_id"
        ).fetchall()

        examinations = database.execute(
            "SELECT * FROM examination ORDER BY exam_id"
        ).fetchall()

        examiners = database.execute(
            "SELECT * FROM examiner_profile ORDER BY examiner_id"
        ).fetchall()

        slots = database.execute(
            """
            SELECT
                slot_id,
                exam_id,
                slot_date,
                start_time,
                end_time,
                examiner_id
            FROM examination_slot
            ORDER BY exam_id, slot_date, start_time
            """
        ).fetchall()

        totals = {
            "courses": len(courses),
            "examinations": len(examinations),
            "examiners": len(examiners),
            "students": database.execute(
                "SELECT COUNT(*) FROM student"
            ).fetchone()[0],
            "slots": database.execute(
                "SELECT COUNT(*) FROM examination_slot"
            ).fetchone()[0],
            "bookings": database.execute(
                "SELECT COUNT(*) FROM booking"
            ).fetchone()[0]
        }

    return render_template(
        "admin_dashboard.html",
        courses=courses,
        examinations=examinations,
        examiners=examiners,
        totals=totals,
        section=section,
        slots=slots
    )

def save_slot_availability(
    database, exam_id, examiner_id, is_admin, selected_ids, only_slot_id=None
):
    slots = database.execute(
        """
        SELECT *
        FROM examination_slot
        WHERE exam_id = ?
        """,
        (exam_id,)
    ).fetchall()

    valid_ids = {slot["slot_id"] for slot in slots}

    if not selected_ids.issubset(valid_ids):
        raise ValueError("A selected slot does not belong to this examination.")

    if only_slot_id is not None and only_slot_id not in valid_ids:
        raise ValueError("That slot does not belong to this examination.")

    for slot in slots:
        slot_id = slot["slot_id"]

        if only_slot_id is not None and slot_id != only_slot_id:
            continue

        if slot["status"] in ("Cancelled", "Completed"):
            if only_slot_id is not None:
                raise ValueError("Cancelled or completed slots cannot change.")
            continue

        current_examiner = slot["examiner_id"]
        checked = slot_id in selected_ids

        # Unchecked slots belonging to someone else remain untouched.
        if not checked and current_examiner != examiner_id:
            continue

        # Already assigned as requested: nothing to change.
        if checked and current_examiner == examiner_id:
            continue

        if checked and current_examiner is not None and not is_admin:
            raise ValueError("You cannot replace another examiner.")

        bookings = database.execute(
            """
            SELECT COUNT(*) FROM booking
            WHERE slot_id = ?
              AND status IN ('Booked', 'Completed')
            """,
            (slot_id,)
        ).fetchone()[0]

        if not checked and bookings:
            raise ValueError(
                "A slot with bookings cannot be left unassigned. "
                "An admin can reassign it to another examiner."
            )

        if checked and bookings and not is_admin:
            raise ValueError(
                "An admin must assign this slot because it has bookings."
            )

        new_examiner = examiner_id if checked else None

        database.execute(
            """
            UPDATE examination_slot
            SET examiner_id = ?
            WHERE slot_id = ? AND exam_id = ?
            """,
            (new_examiner, slot_id, exam_id)
        )

@app.route("/availability", methods=["GET", "POST"])
@require_role("Admin", "Examiner")
def examiner_availability():
    if (
        request.method == "POST"
        and request.form.get("action") == "cancel"
    ):
        return redirect(url_for("dashboard"))

    is_admin = g.user["role"] == "Admin"
    source = request.form if request.method == "POST" else request.args

    exam_id_text = source.get("exam_id", "").strip()
    examiner_id_text = source.get("examiner_id", "").strip()

    examination = None
    examiner_id = None
    slots = []
    error = None

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        if not is_admin:
            profile = database.execute(
                """
                SELECT examiner_id FROM examiner_profile
                WHERE user_id = ?
                """,
                (g.user["user_id"],)
            ).fetchone()

            if profile is None:
                abort(403)

            # Ignore any submitted examiner ID.
            examiner_id_text = str(profile["examiner_id"])
        if (
            (exam_id_text and examiner_id_text)
            or request.method == "POST"
        ):
            try:
                exam_id = int(exam_id_text)
                examiner_id = int(examiner_id_text)

                if request.method == "POST":
                    database.execute("BEGIN IMMEDIATE")

                examination = database.execute(
                    "SELECT * FROM examination WHERE exam_id = ?",
                    (exam_id,)
                ).fetchone()

                if examination is None:
                    raise ValueError("Enter an existing examination ID.")

                target = database.execute(
                    """
                    SELECT examiner_profile.examiner_id
                    FROM examiner_profile
                    JOIN users
                        ON users.user_id = examiner_profile.user_id
                    WHERE examiner_profile.examiner_id = ?
                      AND examiner_profile.status = 'Approved'
                      AND users.role = 'Examiner'
                    """,
                    (examiner_id,)
                ).fetchone()

                if target is None:
                    raise ValueError("Enter an approved examiner's profile ID.")

                if not is_admin:
                    assigned = database.execute(
                        """
                        SELECT exam_id
                        FROM examiner_assignment
                        WHERE exam_id = ? AND examiner_id = ?
                        """,
                        (exam_id, examiner_id)
                    ).fetchone()

                    if assigned is None:
                        abort(403)

                slots = database.execute(
                    """
                    SELECT * FROM examination_slot
                    WHERE exam_id = ?
                    ORDER BY slot_date, start_time
                    """,
                    (exam_id,)
                ).fetchall()

                if request.method == "POST":
                    action = request.form.get("action", "update")
                    only_slot_id = None

                    if action.startswith("save:"):
                        only_slot_id = int(action.split(":", 1)[1])
                    elif action != "update":
                        raise ValueError("Unknown action.")

                    selected_ids = {
                        int(value)
                        for value in request.form.getlist("available_slot_ids")
                    }

                    save_slot_availability(
                        database,
                        exam_id,
                        examiner_id,
                        is_admin,
                        selected_ids,
                        only_slot_id
                    )
                    database.commit()

                    # If an examiner released their final slot, return home.
                    if not is_admin:
                        still_assigned = database.execute(
                            """
                            SELECT slot_id FROM examination_slot
                            WHERE exam_id = ? AND examiner_id = ?
                            LIMIT 1
                            """,
                            (exam_id, examiner_id)
                        ).fetchone()

                        if still_assigned is None:
                            return redirect(url_for("dashboard"))

                    return redirect(
                        url_for(
                            "examiner_availability",
                            exam_id=exam_id,
                            examiner_id=examiner_id
                        )
                    )

            except ValueError as exception:
                database.rollback()
                error = str(exception)

            except sqlite3.IntegrityError:
                database.rollback()
                error = "Availability could not be saved."

    return render_template(
        "examiner_availability.html",
        is_admin=is_admin,
        exam_id_text=exam_id_text,
        examiner_id_text=examiner_id_text,
        examiner_id=examiner_id,
        examination=examination,
        slots=slots,
        error=error
    )

@app.route(
    "/examiner/bookings/<int:booking_id>/evaluate",
    methods=["GET", "POST"]
)
@require_role("Examiner")
def examiner_evaluation(booking_id):

    if (
        request.method == "POST"
        and request.form.get("action") == "cancel"
    ):
        return redirect(url_for("dashboard"))

    error = None
    message = None

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        if request.method == "POST":
            database.execute("BEGIN IMMEDIATE")

        examiner = database.execute(
            """
            SELECT examiner_id FROM examiner_profile
            WHERE user_id = ?
            """,
            (g.user["user_id"],)
        ).fetchone()

        if examiner is None:
            abort(403)

        details = database.execute(
            """
            SELECT
                booking.booking_id,
                booking.student_id,
                booking.status AS booking_status,
                student.name AS student_name,
                examination_slot.slot_id,
                examination_slot.exam_id,
                examination_slot.examiner_id,
                examination_slot.slot_date,
                examination_slot.start_time,
                examination_slot.end_time,
                examination.exam_name
            FROM booking
            JOIN student
                ON student.student_id = booking.student_id
            JOIN examination_slot
                ON examination_slot.slot_id = booking.slot_id
            JOIN examination
                ON examination.exam_id = examination_slot.exam_id
            WHERE booking.booking_id = ?
            """,
            (booking_id,)
        ).fetchone()

        if details is None:
            abort(404)

        if details["examiner_id"] != examiner["examiner_id"]:
            abort(403)

        if details["booking_status"] not in ("Booked", "Completed"):
            abort(403)

        criteria = database.execute(
            """
            SELECT * FROM examination_rubric
            WHERE exam_id = ?
            ORDER BY rubric_id
            """,
            (details["exam_id"],)
        ).fetchall()

        evaluation = database.execute(
            "SELECT * FROM evaluation WHERE booking_id = ?",
            (booking_id,)
        ).fetchone()

        submitted = (
            evaluation is not None
            and evaluation["status"] == "Submitted"
        )

        marks = {}

        if evaluation is not None:
            saved_scores = database.execute(
                """
                SELECT rubric_id, marks_awarded
                FROM evaluation_score
                WHERE evaluation_id = ?
                """,
                (evaluation["evaluation_id"],)
            ).fetchall()

            marks = {
                score["rubric_id"]: score["marks_awarded"]
                for score in saved_scores
            }

        if request.method == "POST":
            # Preserve typed values if validation fails or one row is saved.
            for criterion in criteria:
                rubric_id = criterion["rubric_id"]
                marks[rubric_id] = request.form.get(
                    f"marks_{rubric_id}", ""
                )

            try:
                if submitted:
                    raise ValueError(
                        "This evaluation has already been submitted."
                    )

                if not criteria:
                    raise ValueError(
                        "The admin must define rubric criteria first."
                    )

                action = request.form.get("action", "")
                chosen = []

                if action == "submit":
                    chosen = list(criteria)

                elif action.startswith("save:"):
                    selected_id = int(action.split(":", 1)[1])

                    chosen = [
                        criterion for criterion in criteria
                        if criterion["rubric_id"] == selected_id
                    ]

                    if not chosen:
                        raise ValueError("Invalid rubric criterion.")

                else:
                    raise ValueError("Unknown action.")

                validated_scores = []

                for criterion in chosen:
                    rubric_id = criterion["rubric_id"]

                    awarded = validate_awarded_marks(
                        marks.get(rubric_id, ""),
                        criterion["max_marks"]
                    )

                    validated_scores.append((rubric_id, awarded))

                if evaluation is None:
                    cursor = database.execute(
                        """
                        INSERT INTO evaluation (booking_id)
                        VALUES (?)
                        """,
                        (booking_id,)
                    )
                    evaluation_id = cursor.lastrowid

                else:
                    evaluation_id = evaluation["evaluation_id"]

                for rubric_id, awarded in validated_scores:
                    database.execute(
                        """
                        INSERT INTO evaluation_score (
                            evaluation_id, rubric_id, marks_awarded
                        )
                        VALUES (?, ?, ?)
                        ON CONFLICT (evaluation_id, rubric_id)
                        DO UPDATE SET
                            marks_awarded = excluded.marks_awarded
                        """,
                        (evaluation_id, rubric_id, awarded)
                    )

                if action == "submit":
                    database.execute(
                        """
                        UPDATE evaluation
                        SET status = 'Submitted',
                            is_published = 1,
                            submitted_by = ?,
                            submitted_at = CURRENT_TIMESTAMP
                        WHERE evaluation_id = ?
                        """,
                        (examiner["examiner_id"], evaluation_id)
                    )

                    database.execute(
                        """
                        UPDATE booking
                        SET status = 'Completed'
                        WHERE booking_id = ?
                        """,
                        (booking_id,)
                    )

                database.commit()

                if action == "submit":
                    return redirect(
                        url_for(
                            "examiner_evaluation",
                            booking_id=booking_id
                        )
                    )

                message = "Criterion saved as a draft."

            except ValueError as exception:
                database.rollback()
                error = str(exception)

            except sqlite3.IntegrityError:
                database.rollback()
                error = "The evaluation could not be saved."

    return render_template(
        "examiner_evaluation.html",
        details=details,
        criteria=criteria,
        marks=marks,
        submitted=submitted,
        error=error,
        message=message
    )

@app.route("/examiner/dashboard")
@require_role("Examiner")
def examiner_dashboard():
    section = request.args.get("section", "all")

    if section not in ("all", "exams", "slots"):
        abort(400)

    with closing(sqlite3.connect(database_path)) as database:
        database.row_factory = sqlite3.Row

        examiner = database.execute(
            """
            SELECT examiner_id, name
            FROM examiner_profile
            WHERE user_id = ?
            """,
            (g.user["user_id"],)
        ).fetchone()

        if examiner is None:
            abort(403)

        examiner_id = examiner["examiner_id"]

        examinations = database.execute(
            """
            SELECT e.*
            FROM examination e
            JOIN examiner_assignment a ON a.exam_id = e.exam_id
            WHERE a.examiner_id = ?
            ORDER BY e.exam_id
            """,
            (examiner_id,)
        ).fetchall()

        bookings = database.execute(
            """
            SELECT
                booking.booking_id,
                examination_slot.exam_id,
                booking.slot_id,
                booking.student_id,
                booking.booking_date,
                booking.status,
                evaluation.status AS evaluation_status
            FROM booking
            JOIN examination_slot
                ON examination_slot.slot_id = booking.slot_id
            LEFT JOIN evaluation
                ON evaluation.booking_id = booking.booking_id
            WHERE examination_slot.examiner_id = ?
            ORDER BY examination_slot.slot_date,
                     examination_slot.start_time,
                     booking.booking_id
            """,
            (examiner_id,)
        ).fetchall()

    pending_evaluations = sum(
        1 for booking in bookings
        if booking["status"] in ("Booked", "Completed")
        and booking["evaluation_status"] != "Submitted"
    )

    return render_template(
        "examiner_dashboard.html",
        examiner=examiner,
        examinations=examinations,
        bookings=bookings,
        pending_evaluations=pending_evaluations,
        section=section
    )

@app.route("/student/dashboard")
@require_role("Student")
def student_dashboard():
    section = request.args.get("section", "home")

    if section not in ("home", "exams", "slots"):
        abort(400)

    now = datetime.now()
    today = now.date().isoformat()

    with closing(sqlite3.connect(database_path)) as database:
        database.row_factory = sqlite3.Row

        student = database.execute(
            "SELECT * FROM student WHERE user_id = ?",
            (g.user["user_id"],)
        ).fetchone()

        if student is None:
            abort(403)

        bookings = database.execute(
            """
            SELECT
                booking.*,
                examination_slot.exam_id,
                examination_slot.slot_date,
                examination_slot.start_time,
                examination.course_id,
                examination.exam_name,
                examination.exam_type,
                examination.duration,
                examination.max_marks
            FROM booking
            JOIN examination_slot
                ON examination_slot.slot_id = booking.slot_id
            JOIN examination
                ON examination.exam_id = examination_slot.exam_id
            WHERE booking.student_id = ?
            ORDER BY examination_slot.slot_date,
                     examination_slot.start_time
            """,
            (student["student_id"],)
        ).fetchall()

        booked_by_slot = {
            booking["slot_id"]: booking
            for booking in bookings
            if booking["status"] == "Booked"
        }

        booked_exam_ids = {
            booking["exam_id"]
            for booking in bookings
            if booking["status"] in ("Booked", "Completed")
        }

        rows = database.execute(
            """
            SELECT
                s.*,
                e.status AS exam_status,
                e.slot_booking_start_date,
                e.slot_booking_end_date,
                c.status AS course_status,
                ep.status AS examiner_status,
                u.role AS examiner_role,
                (
                    SELECT COUNT(*)
                    FROM booking b
                    WHERE b.slot_id = s.slot_id
                      AND b.status IN ('Booked', 'Completed')
                ) AS occupied
            FROM examination_slot s
            JOIN examination e ON e.exam_id = s.exam_id
            JOIN course c ON c.course_id = e.course_id
            LEFT JOIN examiner_profile ep
                ON ep.examiner_id = s.examiner_id
            LEFT JOIN users u ON u.user_id = ep.user_id
            WHERE s.slot_date >= ?
              AND s.status IN ('Available', 'Full')
            ORDER BY s.slot_date, s.start_time
            """,
            (today,)
        ).fetchall()

    slots = []

    for row in rows:
        slot = dict(row)

        starts_at = datetime.fromisoformat(
            slot["slot_date"] + "T" + slot["start_time"]
        )

        if starts_at <= now:
            continue

        slot["remaining"] = max(
            0, slot["max_student_capacity"] - slot["occupied"]
        )

        own_booking = booked_by_slot.get(slot["slot_id"])
        slot["booking_id"] = (
            own_booking["booking_id"] if own_booking else None
        )

        booking_start = slot["slot_booking_start_date"]
        booking_end = slot["slot_booking_end_date"]

        period_open = bool(
            booking_start
            and booking_end
            and booking_start <= today <= booking_end
        )

        slot["can_book"] = (
            own_booking is None
            and slot["exam_id"] not in booked_exam_ids
            and slot["status"] == "Available"
            and slot["remaining"] > 0
            and slot["course_status"] == "Active"
            and slot["exam_status"] == "Booking Open"
            and period_open
            and slot["examiner_id"] is not None
            and slot["examiner_status"] == "Approved"
            and slot["examiner_role"] == "Examiner"
        )

        slot["can_cancel"] = bool(
            own_booking
            and booking_end
            and today <= booking_end
        )

        slots.append(slot)

    upcoming = [
        booking
        for booking in bookings
        if booking["status"] == "Booked"
        and datetime.fromisoformat(
            booking["slot_date"] + "T" + booking["start_time"]
        ) > now
    ]

    return render_template(
        "student_dashboard.html",
        student=student,
        slots=slots,
        upcoming=upcoming,
        section=section,
        endpoints=set(app.view_functions)
    )

@app.route("/student/profile", methods=["GET", "POST"])
@require_role("Student")
def student_profile_page():
    error = None

    if (
        request.method == "POST"
        and request.form.get("action") == "cancel"
    ):
        return redirect(url_for("student_dashboard"))

    if "profile_csrf" not in session:
        session["profile_csrf"] = secrets.token_urlsafe(32)

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        student = database.execute(
            "SELECT * FROM student WHERE user_id = ?",
            (g.user["user_id"],)
        ).fetchone()

        if student is None:
            abort(403)

        values = {
            "name": student["name"],
            "contact_details": student["contact_details"] or ""
        }

        if request.method == "POST":
            token = request.form.get("csrf_token", "")

            if not secrets.compare_digest(
                token, session["profile_csrf"]
            ):
                abort(400, "Form expired. Reload the page and try again.")

            values = {
                "name": request.form.get("name", "").strip(),
                "contact_details": request.form.get(
                    "contact_details", ""
                ).strip()
            }

            if request.form.get("action") != "update":
                error = "Choose Update or Cancel."

            elif not 1 <= len(values["name"]) <= 150:
                error = "Name must contain 1 to 150 characters."

            else:
                database.execute(
                    """
                    UPDATE student
                    SET name = ?, contact_details = ?
                    WHERE student_id = ? AND user_id = ?
                    """,
                    (
                        values["name"],
                        values["contact_details"],
                        student["student_id"],
                        g.user["user_id"]
                    )
                )
                database.commit()

                return redirect(url_for("student_dashboard"))

    return render_template(
        "student_profile.html",
        student=student,
        values=values,
        csrf_token=session["profile_csrf"],
        error=error
    )

@app.route(
    "/student/slots/<int:slot_id>/booking",
    methods=["GET", "POST"]
)
@require_role("Student")
def student_update_booking(slot_id):
    error = None

    if "booking_csrf" not in session:
        session["booking_csrf"] = secrets.token_urlsafe(32)

    if request.method == "POST":
        token = request.form.get("csrf_token", "")

        if not secrets.compare_digest(token, session["booking_csrf"]):
            abort(400, "Form expired. Reload the page and try again.")

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        if request.method == "POST":
            database.execute("BEGIN IMMEDIATE")

        student = database.execute(
            "SELECT student_id FROM student WHERE user_id = ?",
            (g.user["user_id"],)
        ).fetchone()

        if student is None:
            abort(403)

        student_id = student["student_id"]

        slot = database.execute(
            """
            SELECT
                s.*,
                e.exam_name,
                e.status AS exam_status,
                e.slot_booking_start_date,
                e.slot_booking_end_date,
                c.course_name,
                c.status AS course_status,
                ep.status AS examiner_status,
                u.role AS examiner_role
            FROM examination_slot s
            JOIN examination e ON e.exam_id = s.exam_id
            JOIN course c ON c.course_id = e.course_id
            LEFT JOIN examiner_profile ep
                ON ep.examiner_id = s.examiner_id
            LEFT JOIN users u ON u.user_id = ep.user_id
            WHERE s.slot_id = ?
            """,
            (slot_id,)
        ).fetchone()

        if slot is None:
            abort(404)

        booking = database.execute(
            """
            SELECT * FROM booking
            WHERE student_id = ? AND slot_id = ?
              AND status IN ('Booked', 'Completed')
            ORDER BY booking_id DESC
            LIMIT 1
            """,
            (student_id, slot_id)
        ).fetchone()

        occupied = database.execute(
            """
            SELECT COUNT(*) FROM booking
            WHERE slot_id = ?
              AND status IN ('Booked', 'Completed')
            """,
            (slot_id,)
        ).fetchone()[0]

        remaining = max(0, slot["max_student_capacity"] - occupied)

        now = datetime.now()
        today = now.date().isoformat()
        starts_at = datetime.fromisoformat(
            slot["slot_date"] + "T" + slot["start_time"]
        )

        booking_start = slot["slot_booking_start_date"]
        booking_end = slot["slot_booking_end_date"]

        duplicate = database.execute(
            """
            SELECT b.booking_id
            FROM booking b
            JOIN examination_slot s ON s.slot_id = b.slot_id
            WHERE b.student_id = ? AND s.exam_id = ?
              AND b.status IN ('Booked', 'Completed')
            LIMIT 1
            """,
            (student_id, slot["exam_id"])
        ).fetchone()

        book_problem = None

        if duplicate is not None:
            book_problem = "You already have a booking for this examination."
        elif slot["course_status"] != "Active":
            book_problem = "This course is inactive."
        elif slot["exam_status"] != "Booking Open":
            book_problem = "Booking is not open for this examination."
        elif not booking_start or not booking_end:
            book_problem = "The booking period has not been configured."
        elif not booking_start <= today <= booking_end:
            book_problem = "This examination is outside its booking period."
        elif starts_at <= now:
            book_problem = "This slot has already started."
        elif (
            slot["examiner_id"] is None
            or slot["examiner_status"] != "Approved"
            or slot["examiner_role"] != "Examiner"
        ):
            book_problem = "An approved examiner must be assigned first."
        elif slot["status"] != "Available" or remaining == 0:
            book_problem = "This slot is not available for booking."

        cancel_problem = None

        if booking is None or booking["status"] != "Booked":
            cancel_problem = "You do not have a cancellable booking here."
        elif not booking_end:
            cancel_problem = "The cancellation deadline is not configured."
        elif today > booking_end:
            cancel_problem = "The cancellation deadline has passed."
        elif starts_at <= now:
            cancel_problem = "This slot has already started."

        if request.method == "POST":
            action = request.form.get("action", "")

            if action == "book":
                error = book_problem
            elif action == "cancel_booking":
                error = cancel_problem
            else:
                abort(400)

            if error is None:
                try:
                    if action == "book":
                        database.execute(
                            """
                            INSERT INTO booking (
                                student_id, slot_id, booking_date, status
                            )
                            VALUES (?, ?, ?, 'Booked')
                            """,
                            (student_id, slot_id, today)
                        )
                        new_remaining = remaining - 1

                    else:
                        database.execute(
                            """
                            UPDATE booking
                            SET status = 'Cancelled'
                            WHERE booking_id = ? AND student_id = ?
                            """,
                            (booking["booking_id"], student_id)
                        )
                        new_remaining = (
                            slot["max_student_capacity"] - occupied + 1
                        )

                    if slot["status"] in ("Cancelled", "Completed"):
                        new_status = slot["status"]
                    else:
                        new_status = (
                            "Full" if new_remaining == 0 else "Available"
                        )

                    database.execute(
                        """
                        UPDATE examination_slot
                        SET available_seats = ?, status = ?
                        WHERE slot_id = ?
                        """,
                        (new_remaining, new_status, slot_id)
                    )
                    database.commit()

                except sqlite3.IntegrityError:
                    database.rollback()
                    error = "The booking could not be updated."

                else:
                    return redirect(url_for("student_dashboard"))

            database.rollback()

    return render_template(
        "student_update_booking.html",
        slot=slot,
        booking=booking,
        remaining=remaining,
        book_problem=book_problem,
        cancel_problem=cancel_problem,
        error=error,
        csrf_token=session["booking_csrf"]
    )

@app.route("/student/history")
@require_role("Student")
def student_history():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with closing(sqlite3.connect(database_path)) as database:
        database.row_factory = sqlite3.Row

        student = database.execute(
            """
            SELECT student_id, name
            FROM student
            WHERE user_id = ?
            """,
            (g.user["user_id"],)
        ).fetchone()

        if student is None:
            abort(403)

        rows = database.execute(
            """
            SELECT
                b.booking_id,
                b.status AS booking_status,
                s.slot_id,
                s.slot_date,
                s.start_time,
                s.end_time,
                e.exam_id,
                e.exam_name,
                e.exam_type,
                e.duration,
                e.max_marks AS exam_max_marks,
                c.course_id,
                c.course_code,
                c.course_name,
                c.description,
                v.evaluation_id,
                v.status AS evaluation_status,
                v.is_published
            FROM booking b
            JOIN examination_slot s
                ON s.slot_id = b.slot_id
            JOIN examination e
                ON e.exam_id = s.exam_id
            JOIN course c
                ON c.course_id = e.course_id
            LEFT JOIN evaluation v
                ON v.booking_id = b.booking_id
            WHERE b.student_id = ?
                AND (
                    b.status = 'Completed'
                    OR (
                        b.status = 'Booked'
                        AND (s.slot_date || ' ' || s.end_time) <= ?
                    )
                )
            ORDER BY s.slot_date DESC,
                     s.start_time DESC,
                     b.booking_id DESC
            """,
            (student["student_id"], now)
        ).fetchall()

        history = []

        for row in rows:
            record = dict(row)
            record["scores"] = []

            if (
                record["evaluation_status"] == "Submitted"
                and record["is_published"] == 1
            ):
                record["scores"] = database.execute(
                    """
                    SELECT
                        r.criterion_name,
                        r.max_marks,
                        sc.marks_awarded
                    FROM evaluation_score sc
                    JOIN examination_rubric r
                        ON r.rubric_id = sc.rubric_id
                    WHERE sc.evaluation_id = ?
                    ORDER BY r.rubric_id
                    """,
                    (record["evaluation_id"],)
                ).fetchall()

            history.append(record)

    return render_template(
        "student_history.html",
        student=student,
        history=history
    )

@app.route("/student/examinations/<int:exam_id>")
@require_role("Student")
def student_exam_details(exam_id):
    with closing(sqlite3.connect(database_path)) as database:
        database.row_factory = sqlite3.Row

        student = database.execute(
            """
            SELECT student_id
            FROM student
            WHERE user_id = ?
            """,
            (g.user["user_id"],)
        ).fetchone()

        if student is None:
            abort(403)

        examination = database.execute(
            """
            SELECT
                e.*,
                c.course_code,
                c.course_name,
                c.description AS course_description
            FROM examination e
            JOIN course c ON c.course_id = e.course_id
            WHERE e.exam_id = ?
            """,
            (exam_id,)
        ).fetchone()

        if examination is None:
            abort(404)

        booked_slots = database.execute(
            """
            SELECT
                s.slot_id,
                s.slot_date,
                s.start_time,
                s.end_time,
                b.status AS booking_status,
                ep.name AS examiner_name
            FROM booking b
            JOIN examination_slot s ON s.slot_id = b.slot_id
            LEFT JOIN examiner_profile ep
                ON ep.examiner_id = s.examiner_id
            WHERE b.student_id = ?
              AND s.exam_id = ?
              AND b.status IN ('Booked', 'Completed')
            ORDER BY s.slot_date, s.start_time
            """,
            (student["student_id"], exam_id)
        ).fetchall()

    return render_template(
        "student_exam_details.html",
        examination=examination,
        booked_slots=booked_slots
    )

@app.route(
    "/admin/examinations/<int:exam_id>/assign-examiner",
    methods=["GET", "POST"]
)
@require_role("Admin")
def assign_examiner(exam_id):
    error = None
    selected_id = request.form.get("examiner_id", "")

    if (
        request.method == "POST"
        and request.form.get("action") == "cancel"
    ):
        return redirect(url_for("admin_dashboard"))

    if "assignment_csrf" not in session:
        session["assignment_csrf"] = secrets.token_urlsafe(32)

    with closing(sqlite3.connect(database_path)) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.row_factory = sqlite3.Row

        examination = database.execute(
            """
            SELECT exam_id, exam_name
            FROM examination
            WHERE exam_id = ?
            """,
            (exam_id,)
        ).fetchone()

        if examination is None:
            abort(404)

        examiners = database.execute(
            """
            SELECT ep.examiner_id, ep.name
            FROM examiner_profile ep
            JOIN users u ON u.user_id = ep.user_id
            WHERE ep.status = 'Approved'
              AND u.role = 'Examiner'
            ORDER BY ep.name, ep.examiner_id
            """
        ).fetchall()

        if request.method == "POST":
            token = request.form.get("csrf_token", "")

            if not secrets.compare_digest(
                token, session["assignment_csrf"]
            ):
                abort(400, "Form expired. Reload and try again.")

            if request.form.get("action") != "assign":
                abort(400)

            try:
                examiner_id = int(selected_id)
            except ValueError:
                error = "Choose an examiner."
            else:
                approved_ids = {
                    examiner["examiner_id"]
                    for examiner in examiners
                }

                if examiner_id not in approved_ids:
                    error = "Choose an approved examiner."

                else:
                    database.execute(
                        """
                        INSERT INTO examiner_assignment (
                            exam_id, examiner_id
                        )
                        VALUES (?, ?)
                        ON CONFLICT (exam_id, examiner_id)
                        DO NOTHING
                        """,
                        (exam_id, examiner_id)
                    )
                    database.commit()

                    return redirect(url_for("admin_dashboard"))

        assigned = database.execute(
            """
            SELECT ep.examiner_id, ep.name, ep.status
            FROM examiner_assignment a
            JOIN examiner_profile ep
                ON ep.examiner_id = a.examiner_id
            WHERE a.exam_id = ?
            ORDER BY ep.name
            """,
            (exam_id,)
        ).fetchall()

    return render_template(
        "assign_examiner.html",
        examination=examination,
        examiners=examiners,
        assigned=assigned,
        selected_id=selected_id,
        csrf_token=session["assignment_csrf"],
        error=error
    )