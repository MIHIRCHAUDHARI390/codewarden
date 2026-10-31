# Normal-behaviour tests. A patch must keep all of these passing.
import os

from app import config, db, files, loader, shell


def test_find_user():
    conn = db.make_db()
    assert db.find_user(conn, "alice") == [("alice", "alice@example.com")]


def test_count_lines(tmp_path):
    p = tmp_path / "three.txt"
    p.write_text("a\nb\nc\n")
    assert shell.count_lines(str(p)) == 3


def test_read_note():
    assert files.read_note("hello.txt").startswith("hello")


def test_load_config():
    assert loader.load_config("a: 1") == {"a": 1}


def test_auth_header(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "x")
    assert config.auth_header()["Authorization"].startswith("Bearer ")
