from tutor.retrieval import Chunk, NotesIndex, tokenize


def test_bm25_search_with_unit_and_section_boost():
    chunks = [
        Chunk(0, "u2.pdf", 2, 1, "Having", "HAVING filters groups after GROUP BY aggregation"),
        Chunk(1, "u3.pdf", 3, 1, "Two Phase Locking", "growing phase and shrinking phase locks deadlock"),
        Chunk(2, "u1.pdf", 1, 1, "Select", "WHERE filters rows before grouping in SQL queries"),
    ]
    ix = NotesIndex(chunks)
    assert ix.search("having group by")[0].id == 0
    assert ix.search("locking deadlock", unit=3)[0].id == 1
    assert NotesIndex([]).search("anything") == []
    assert "the" not in tokenize("The WHERE clause")
