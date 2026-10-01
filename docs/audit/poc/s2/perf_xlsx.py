"""S2 PoC: the Excel writer in services/pgas.py is quadratic in the number of rows (ws.max_row is O(rows) and is
called for every cell). Run from the repo root:  cd server && python ../docs/audit/poc/s2/perf_xlsx.py
Expected: 1000 rows ~1 s, 2000 ~5 s, 3000 ~10 s, 5000 ~26 s (nginx proxy_read_timeout is 25 s)."""
import datetime
import os
import sys
import time

os.environ.setdefault("SECRET_KEY", "audit-s2-secret-key-that-is-long-enough-123456")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "server"))
from app.services import pgas  # noqa: E402


def rows(n):
    return [{"day": datetime.date(2026, 9, 1), "title": "Событие", "level": "Институт", "organizer": "Администрация ИВИТШ",
             "full_name": "Иванов Иван Иванович", "group": "24-ИСбо-1", "role": "participant", "source": "admin_group",
             "attended": None} for _ in range(n)]


for n in (500, 1000, 2000, 3000, 5000):
    t = time.time()
    pgas.events_report_xlsx(datetime.date(2026, 9, 1), datetime.date(2027, 1, 31), rows(n))
    print(f"xlsx {n:5d} rows: {time.time() - t:5.1f} s")
t = time.time()
pgas.events_report_docx(datetime.date(2026, 9, 1), datetime.date(2027, 1, 31), rows(5000), datetime.date.today())
print(f"docx  5000 rows: {time.time() - t:5.1f} s")
