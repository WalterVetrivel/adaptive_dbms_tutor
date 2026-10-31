from tutor import schedule_tools as st


def test_conflict_serializable():
    ops = st.parse_schedule("r1(A) w1(A) r2(A) w2(A) r1(B) w1(B) r2(B) w2(B)")
    ok, order = st.conflict_serializable(ops)
    assert ok and order == [1, 2]
    assert st.solve({"schedule": "r1(A) r2(A) w1(A) w2(A)", "ask": "conflict_serializable"}) == "no"
    assert st.grade({"schedule": "r1(A) r2(A) w1(A) w2(A)", "ask": "serial_order"}, "not serializable")


def test_recoverable_and_cascadeless():
    unrec = st.parse_schedule("w1(A) r2(A) c2 c1")
    assert not st.is_recoverable(unrec)
    rec = st.parse_schedule("w1(A) r2(A) c1 c2")
    assert st.is_recoverable(rec) and not st.is_cascadeless(rec)
    assert st.is_cascadeless(st.parse_schedule("w1(A) c1 r2(A) c2"))
