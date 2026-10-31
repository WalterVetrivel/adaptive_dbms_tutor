import sqlite3

from tutor import config


def q(sql):
    conn = sqlite3.connect(f"file:{config.SAMPLE_DB_PATH}?mode=ro", uri=True)
    return conn.execute(sql).fetchall()


def test_sample_db_has_teaching_edge_cases():
    assert q("SELECT COUNT(*) FROM employee WHERE dept_id IS NULL")[0][0] == 2
    # department with no employees (outer join case)
    assert q("SELECT COUNT(*) FROM department d WHERE NOT EXISTS "
             "(SELECT 1 FROM employee e WHERE e.dept_id = d.dept_id)")[0][0] >= 1
    # COUNT(*) vs COUNT(commission) differ (NULL handling)
    total, with_comm = q("SELECT COUNT(*), COUNT(commission) FROM employee")[0]
    assert total > with_comm > 0
    # NOT IN with a NULL in the subquery returns nothing
    assert q("SELECT COUNT(*) FROM department WHERE dept_id NOT IN (SELECT dept_id FROM employee)")[0][0] == 0
    # right/full outer joins supported by this SQLite build
    assert q("SELECT COUNT(*) FROM employee e FULL OUTER JOIN department d ON e.dept_id = d.dept_id")[0][0] > 0
