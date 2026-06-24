from app.rag.qdrant_store import build_payload_filter, build_tm_point


def test_build_tm_point_uses_minimal_payload() -> None:
    point = build_tm_point(
        point_id="abc123",
        vector=[0.1, 0.2],
        tm_entry_id=7,
        mod_id="example_mod",
        unit_key="descriptions.Joker.j_test.text[0]",
        context_type="joker_description_line",
        token_signature="style_mult|var_1|style_reset",
        quality="imported_human",
    )

    assert point.id == "abc123"
    assert point.vector == [0.1, 0.2]
    assert point.payload["tm_entry_id"] == 7
    assert point.payload["mod_id"] == "example_mod"
    assert point.payload["context_type"] == "joker_description_line"
    assert "source_text" not in point.payload
    assert "target_text" not in point.payload


def test_build_payload_filter_matches_exact_values() -> None:
    query_filter = build_payload_filter(
        {"mod_id": "example_mod", "context_type": "joker_description_line"}
    )

    assert query_filter is not None
    assert len(query_filter.must) == 2
    assert query_filter.must[0].key == "mod_id"
    assert query_filter.must[0].match.value == "example_mod"
