"""PoC harness for refute: reuses the fixtures of server/tests/conftest.py (temp SQLite DB, fake EIOS).

Run from the repo root:  cd server && python -m pytest ../docs/audit/poc/s5 -q -s -p no:cacheprovider
No real network is used: EIOS and GigaChat are replaced by fakes/mocks.
"""
import os
import runpy
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
SERVER_TESTS = os.path.join(REPO, "server", "tests")
sys.path.insert(0, SERVER_TESTS)

_ns = runpy.run_path(os.path.join(SERVER_TESTS, "conftest.py"))
globals().update({k: v for k, v in _ns.items() if not k.startswith("__")})
