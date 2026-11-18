from contextlib import closing
from pathlib import Path
import sqlite3

from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)
database_path = Path(__file__).parent / "examinationapp.db"

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


@app.route("/", methods=["GET", "POST"])
def home():
    with closing(sqlite3.connect(database_path)) as database:
        if request.method == "POST":
            name = request.form.get("name", "").strip()

            if not name or len(name) > 100:
                return "Enter a name between 1 and 100 characters.", 400

            database.execute(
                "INSERT INTO person (name) VALUES (?)",
                (name,)
            )
            database.commit()

            return redirect(url_for("home"))

        names = database.execute(
            "SELECT name FROM person ORDER BY id DESC"
        ).fetchall()

    return render_template("index.html", names=names)

@app.route("/admin/courses", methods=["GET", "POST"])
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