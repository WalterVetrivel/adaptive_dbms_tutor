"""Build data/sample.db: the read-only teaching database used for SQL questions.

Two small schemas with deliberate NULLs, unmatched rows and duplicates so that
NULL / JOIN / GROUP BY / subquery misconceptions produce visibly different results.
Deterministic (fixed seed), so reference answers are stable.
"""
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tutor import config  # noqa: E402

SCHEMA = """
CREATE TABLE department (
    dept_id   INTEGER PRIMARY KEY,
    dept_name TEXT NOT NULL UNIQUE,
    location  TEXT NOT NULL,
    budget    INTEGER
);
CREATE TABLE employee (
    emp_id     INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    job        TEXT NOT NULL,
    dept_id    INTEGER REFERENCES department(dept_id),   -- NULL = not yet assigned
    manager_id INTEGER REFERENCES employee(emp_id),     -- NULL = top-level
    salary     INTEGER NOT NULL,
    commission INTEGER,                                 -- NULL for most staff
    hire_date  TEXT NOT NULL
);
CREATE TABLE project (
    proj_id   INTEGER PRIMARY KEY,
    proj_name TEXT NOT NULL,
    dept_id   INTEGER REFERENCES department(dept_id),
    budget    INTEGER NOT NULL
);
CREATE TABLE works_on (
    emp_id  INTEGER NOT NULL REFERENCES employee(emp_id),
    proj_id INTEGER NOT NULL REFERENCES project(proj_id),
    hours   INTEGER,
    PRIMARY KEY (emp_id, proj_id)
);
CREATE TABLE student (
    student_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    dept       TEXT NOT NULL,
    year       INTEGER NOT NULL CHECK (year BETWEEN 1 AND 4),
    city       TEXT,
    cgpa       REAL
);
CREATE TABLE course (
    course_id TEXT PRIMARY KEY,
    title     TEXT NOT NULL,
    dept      TEXT NOT NULL,
    credits   INTEGER NOT NULL
);
CREATE TABLE enrollment (
    student_id INTEGER NOT NULL REFERENCES student(student_id),
    course_id  TEXT NOT NULL REFERENCES course(course_id),
    semester   TEXT NOT NULL,
    grade      TEXT,                                    -- NULL = result not published
    PRIMARY KEY (student_id, course_id, semester)
);
"""

DEPARTMENTS = [
    (10, "Engineering", "Chennai", 900000), (20, "Sales", "Mumbai", 400000),
    (30, "HR", "Chennai", 150000), (40, "Finance", "Bengaluru", 300000),
    (50, "Research", "Salem", None),          # NULL budget
    (60, "Legal", "Delhi", 120000),           # no employees -> outer-join cases
]
FIRST = ["Arun", "Priya", "Karthik", "Divya", "Rahul", "Meena", "Vijay", "Anitha", "Suresh", "Lakshmi",
         "Ravi", "Deepa", "Ganesh", "Kavya", "Manoj", "Nithya", "Prakash", "Revathi", "Sanjay", "Swathi",
         "Ajay", "Bhavani", "Dinesh", "Gayathri", "Hari", "Indhu", "Jagan", "Keerthi", "Mohan", "Pooja"]
LAST = ["Kumar", "Raman", "Iyer", "Nair", "Reddy", "Sharma", "Pillai", "Das", "Menon", "Rao"]
JOBS = {10: ["Engineer", "Senior Engineer", "Tester"], 20: ["Sales Executive", "Account Manager"],
        30: ["HR Executive"], 40: ["Accountant", "Analyst"], 50: ["Scientist", "Research Assistant"]}
PROJECTS = [(101, "Payroll Revamp", 40, 250000), (102, "Mobile App", 10, 500000), (103, "CRM Migration", 20, 300000),
            (104, "Data Lake", 10, 450000), (105, "Hiring Portal", 30, 80000), (106, "Quantum Pilot", 50, 200000),
            (107, "Compliance Audit", None, 60000)]   # project without a department
COURSES = [("CS201", "Database Management Systems", "CSE", 4), ("CS202", "Operating Systems", "CSE", 4),
           ("CS203", "Computer Networks", "CSE", 3), ("IT204", "Web Technologies", "IT", 3),
           ("AD205", "Machine Learning", "AIDS", 4), ("MA206", "Discrete Mathematics", "MATH", 4),
           ("CS299", "Compiler Design", "CSE", 3)]   # no enrollments
CITIES = ["Salem", "Chennai", "Coimbatore", "Madurai", "Erode", None]
GRADES = ["O", "A+", "A", "B+", "B", "C", None]


def build(path: Path) -> None:
    rnd = random.Random(42)
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO department VALUES (?,?,?,?)", DEPARTMENTS)

    emps = []
    managers = {10: 1, 20: 2, 30: 3, 40: 4, 50: 5}
    heads = [(1, "Arun Kumar", "Engineering Manager", 10), (2, "Priya Raman", "Sales Manager", 20),
             (3, "Karthik Iyer", "HR Manager", 30), (4, "Divya Nair", "Finance Manager", 40),
             (5, "Rahul Reddy", "Research Lead", 50)]
    for eid, name, job, dept in heads:
        emps.append((eid, name, job, dept, None, rnd.randrange(120, 181) * 1000, None,
                     f"20{rnd.randint(12, 17)}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}"))
    used = {e[1] for e in emps}
    eid = 6
    dept_sizes = {10: 12, 20: 8, 30: 3, 40: 5, 50: 4}
    for dept, size in dept_sizes.items():
        for _ in range(size):
            while True:
                name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
                if name not in used:
                    used.add(name)
                    break
            job = rnd.choice(JOBS[dept])
            salary = rnd.randrange(35, 110) * 1000
            commission = rnd.randrange(2, 15) * 1000 if dept == 20 and rnd.random() < 0.75 else None
            emps.append((eid, name, job, dept, managers[dept], salary, commission,
                         f"20{rnd.randint(16, 25)}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}"))
            eid += 1
    # two unassigned employees (dept_id NULL) -> LEFT JOIN / NOT IN cases
    for name in ("Swathi Menon", "Jagan Rao"):
        emps.append((eid, name, "Trainee", None, None, 30000, None, "2025-07-01"))
        eid += 1
    # duplicate salaries in Engineering for DISTINCT / ties
    emps[6] = emps[6][:5] + (75000,) + emps[6][6:]
    emps[7] = emps[7][:5] + (75000,) + emps[7][6:]
    conn.executemany("INSERT INTO employee VALUES (?,?,?,?,?,?,?,?)", emps)
    conn.executemany("INSERT INTO project VALUES (?,?,?,?)", PROJECTS)

    works = set()
    by_dept: dict = {}
    for e in emps:
        by_dept.setdefault(e[3], []).append(e[0])
    for pid, _, dept, _ in PROJECTS:
        pool = by_dept.get(dept) or by_dept[10]
        for emp in rnd.sample(pool, min(len(pool), rnd.randint(2, 5))):
            works.add((emp, pid, rnd.choice([5, 10, 15, 20, 25, 40, None])))
    conn.executemany("INSERT INTO works_on VALUES (?,?,?)", sorted(works))

    students = []
    depts = ["CSE", "CSE", "IT", "AIDS", "CSBS"]
    used = set()
    for sid in range(1, 31):
        while True:
            name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        cgpa = None if sid in (7, 19) else round(rnd.uniform(5.5, 9.8), 2)
        students.append((sid, name, rnd.choice(depts), rnd.randint(1, 4), rnd.choice(CITIES), cgpa))
    conn.executemany("INSERT INTO student VALUES (?,?,?,?,?,?)", students)
    conn.executemany("INSERT INTO course VALUES (?,?,?,?)", COURSES)
    enr = set()
    for sid, *_ in students:
        if sid in (29, 30):          # students with no enrollments
            continue
        for cid in rnd.sample([c[0] for c in COURSES[:-1]], rnd.randint(1, 4)):
            enr.add((sid, cid, rnd.choice(["2025-ODD", "2026-EVEN"]), rnd.choice(GRADES)))
    conn.executemany("INSERT INTO enrollment VALUES (?,?,?,?)", sorted(enr))
    conn.commit()
    conn.close()


def schema_description() -> str:
    return SCHEMA.strip()


if __name__ == "__main__":
    build(config.SAMPLE_DB_PATH)
    c = sqlite3.connect(config.SAMPLE_DB_PATH)
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        print(f"{t:12s} {c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} rows")
