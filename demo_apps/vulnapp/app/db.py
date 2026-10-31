import sqlite3


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (name TEXT, email TEXT)")
    conn.execute("INSERT INTO users VALUES ('alice', 'alice@example.com')")
    conn.execute("INSERT INTO users VALUES ('bob', 'bob@example.com')")
    return conn


def find_user(conn, name):
    # VULN: SQL injection (string formatting into the query)
    query = "SELECT name, email FROM users WHERE name = '%s'" % name
    return conn.execute(query).fetchall()
