from tutor import sql_sandbox as sb


def test_rejects_writes_and_multiple_statements():
    assert not sb.run_query("DELETE FROM employee").ok
    assert not sb.run_query("SELECT 1; DROP TABLE employee").ok
    assert "SELECT" in sb.run_query("PRAGMA table_info(employee)").error


def test_grading_detects_where_vs_having():
    ref = "SELECT dept_id FROM employee WHERE dept_id IS NOT NULL GROUP BY dept_id HAVING COUNT(*) > 5"
    g = sb.grade_sql("SELECT dept_id FROM employee WHERE COUNT(*) > 5 GROUP BY dept_id", ref)
    assert not g.correct and "misuse of aggregate" in g.student.error
    g2 = sb.grade_sql("select dept_id from employee group by dept_id having count(*) > 5 and dept_id is not null", ref)
    assert g2.correct


def test_order_sensitivity_and_row_diff():
    ref = "SELECT name FROM employee WHERE salary > 100000 ORDER BY salary DESC"
    wrong_order = "SELECT name FROM employee WHERE salary > 100000 ORDER BY salary ASC"
    g = sb.grade_sql(wrong_order, ref)
    assert not g.correct and "order" in g.feedback.lower()
    g2 = sb.grade_sql("SELECT name FROM employee WHERE salary > 150000", "SELECT name FROM employee WHERE salary > 100000")
    assert not g2.correct and g2.missing_rows > 0


def test_verify_item_requires_discrimination():
    ok, _ = sb.verify_sql_item("SELECT COUNT(commission) FROM employee", ["SELECT COUNT(*) FROM employee"])
    assert ok
    ok2, note = sb.verify_sql_item("SELECT COUNT(*) FROM employee", ["SELECT COUNT(emp_id) FROM employee"])
    assert not ok2 and "same result" in note


def test_timeout():
    slow = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT COUNT(*) FROM c")
    r = sb.run_query(slow, timeout_s=0.3)
    assert not r.ok and "stopped" in r.error
