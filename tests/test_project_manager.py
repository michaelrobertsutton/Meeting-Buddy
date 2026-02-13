from ingest.project_manager import _sanitize_name


def test_sanitize_name_basic():
    assert _sanitize_name("My Project") == "my-project"


def test_sanitize_name_symbols():
    assert _sanitize_name("  Hello, World!! ") == "hello-world"


def test_sanitize_name_empty():
    assert _sanitize_name("   ") == "default"
