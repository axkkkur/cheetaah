from app.execution.handlers import HANDLERS, in_scope


def test_forbidden_for_every_kind():
    forbidden = [
        ".env",
        ".env.local",
        "secrets/token.txt",
        "credentials.json",
        "key.pem",
        "id.key",
        ".git/config",
        ".github/workflows/ci.yml",
    ]
    for kind, handler in HANDLERS.items():
        for path in forbidden:
            assert not in_scope(path, handler), f"{path} should be forbidden for {kind}"


def test_py_allowed_for_code_not_doc():
    assert in_scope("app/main.py", HANDLERS["code_change"])
    assert not in_scope("app/main.py", HANDLERS["doc_change"])


def test_env_always_rejected():
    for handler in HANDLERS.values():
        assert not in_scope(".env", handler)
        assert not in_scope("config/.env", handler)


def test_md_for_doc():
    assert in_scope("README.md", HANDLERS["doc_change"])
    assert not in_scope("README.md", HANDLERS["code_change"])
