from app.services.learning_memory_retriever import _dedupe_note_rows_by_id


class Row:
    def __init__(self, memory_id):
        self.memory_id = memory_id


def test_dedupe_note_rows_by_id_preserves_first_seen_order():
    rows = [Row("a"), Row("b"), Row("a"), Row("c")]

    result = _dedupe_note_rows_by_id(rows)

    assert [row.memory_id for row in result] == ["a", "b", "c"]
