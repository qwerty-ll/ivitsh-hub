"""Audit S1 PoCs reuse the fixtures of server/tests/conftest.py (temp SQLite DB, fake EIOS).

Run from the repo root:  python -m pytest docs/audit/poc/s1 -q -p no:cacheprovider
"""
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_spec = importlib.util.spec_from_file_location("srv_conftest", os.path.join(ROOT, "server", "tests", "conftest.py"))
srv = importlib.util.module_from_spec(_spec)
sys.modules["srv_conftest"] = srv
_spec.loader.exec_module(srv)

# Re-export the fixtures so pytest sees them here
app = srv.app
clean_state = srv.clean_state
client = srv.client
db = srv.db
fake_eios = srv.fake_eios
