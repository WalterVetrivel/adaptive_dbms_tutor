from tutor import fd_tools as fd


def test_closure_and_keys():
    fds = fd.parse_fds("A->B, B->C, CD->E")
    assert fd.fmt(fd.closure("A", fds)) == "ABC"
    rel = fd.parse_attrs("ABCDE")
    assert [fd.fmt(k) for k in fd.candidate_keys(rel, fds)] == ["AD"]


def test_multiple_candidate_keys():
    fds = fd.parse_fds("A->B, B->C, C->A")
    assert fd.solve({"attributes": "ABC", "fds": "A->B, B->C, C->A", "ask": "candidate_keys"}) == "A, B, C"
    assert fd.grade({"attributes": "ABC", "fds": "A->B, B->C, C->A", "ask": "candidate_keys"}, "C, A, B")
    assert fd.highest_normal_form(fd.parse_attrs("ABC"), fds) == "BCNF"


def test_normal_forms():
    nf = lambda r, f: fd.highest_normal_form(fd.parse_attrs(r), fd.parse_fds(f))  # noqa: E731
    assert nf("ABCD", "AB->C, B->D") == "1NF"        # partial dependency B->D
    assert nf("ABC", "A->B, B->C") == "2NF"          # transitive
    assert nf("ABC", "AB->C, C->B") == "3NF"         # C->B, B prime, C not superkey
    assert nf("ABC", "A->BC") == "BCNF"


def test_named_attributes():
    fds = fd.parse_fds("emp_id -> name, dept_id; dept_id -> dept_name")
    rel = fd.parse_attrs("emp_id, name, dept_id, dept_name")
    assert fd.candidate_keys(rel, fds) == [frozenset({"emp_id"})]
    assert fd.highest_normal_form(rel, fds) == "2NF"


def test_decomposition():
    fds = fd.parse_fds("A->B, B->C")
    assert fd.is_lossless_binary(frozenset("AB"), frozenset("BC"), fds)
    assert not fd.is_lossless_binary(frozenset("AB"), frozenset("AC"), fd.parse_fds("B->C"))
    # classic BCNF-but-not-preserving: R(ABC), AB->C, C->B, decompose into AC, BC
    fds2 = fd.parse_fds("AB->C, C->B")
    assert not fd.preserves_dependencies([frozenset("AC"), frozenset("BC")], fds2)
    assert fd.preserves_dependencies([frozenset("AB"), frozenset("BC")], fds)
