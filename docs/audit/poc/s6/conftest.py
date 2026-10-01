"""Re-exports the fixtures of server/tests/conftest.py so the S6 PoCs run with one command:

    cd server && python -m pytest ../docs/audit/poc/s6 -q -p no:cacheprovider
"""
import importlib.util
import os
import sys

_SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "server"))
_spec = importlib.util.spec_from_file_location("server_tests_conftest", os.path.join(_SERVER, "tests", "conftest.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["server_tests_conftest"] = _mod
_spec.loader.exec_module(_mod)

from server_tests_conftest import *  # noqa: E402,F401,F403
from server_tests_conftest import CSRF, add_eios_account, login_admin, login_student  # noqa: E402,F401
