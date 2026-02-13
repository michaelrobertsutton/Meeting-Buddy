from backend.export.renderer import SessionData, render_markdown


def test_render_markdown_contains_headers():
    s = SessionData(
        transcript_segments=[{"start_time": 0, "text": "Hello"}],
        qa_history=[{"question": "What is X?", "answer": {"one_liner": "X is Y", "bullets": []}}],
        project_name="proj",
        session_start=1_700_000_000.0,
        session_end=1_700_000_060.0,
    )
    md = render_markdown(s)
    assert "# Meeting Buddy" in md
    assert "## Q&A Summary" in md
    assert "## Full Transcript" in md
