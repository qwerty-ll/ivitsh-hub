"""Generate docs/db-schema.drawio from the SQLAlchemy models (run from the repo root).

Tables are placed on a fixed grid per page and FK edges are routed by hand (orthogonal, staggered),
so draw.io does not re-layout anything. Usage: python server/scripts/gen_drawio.py docs/db-schema.drawio
"""
import os
import sys
from collections import defaultdict
from xml.sax.saxutils import escape

os.environ.setdefault("SECRET_KEY", "x" * 48)  # config refuses to load without one
sys.path.insert(0, "server")
from app.db.database import Base  # noqa: E402
from app.models import models  # noqa: E402,F401

TABLES = Base.metadata.tables
ROW_H, HEAD_H, KEY_W, COL_GAP, ROW_GAP, TOP = 20, 30, 34, 130, 44, 90

TYPE_NAMES = {"INTEGER": "int", "VARCHAR": "str", "TEXT": "text", "DATETIME": "datetime", "BOOLEAN": "bool", "DATE": "date"}

PALETTE = {  # header fill, border
    "users": ("#f8cecc", "#b85450"),
    "forum": ("#dae8fc", "#6c8ebf"),
    "assoc": ("#d5e8d4", "#82b366"),
    "events": ("#fff2cc", "#d6b656"),
    "tribes": ("#e1d5e7", "#9673a6"),
}

# Each page: title, colour, columns (left to right), each column = (dy, [tables top to bottom]).
PAGES = [
    ("Пользователи и форум", "forum", [
        (0, ["forum_answers", "forum_questions", "votes"]),
        (0, ["users"]),
        (0, ["sdo_courses", "group_homework", "revoked_tokens"]),
    ]),
    ("Объединения и задачи", "assoc", [
        (0, ["task_assignees", "task_comments", "association_post_recipients"]),
        (0, ["tasks", "attachments", "association_posts"]),
        (0, ["associations"]),
        (0, ["memberships", "meetings"]),
        (0, ["meeting_attendance"]),
    ]),
    ("События, достижения, брони", "events", [
        (0, ["event_registrations", "event_removals", "event_feedback"]),
        (0, ["events"]),
        (0, ["manual_achievements", "bookings"]),
    ]),
    ("Турнир племён, биты, магазин", "tribes", [
        (0, ["bits_grants", "tournaments", "tribe_members"]),
        (0, ["tribes"]),
        (0, ["tribe_awards", "shop_items"]),
        (0, ["shop_orders"]),
    ]),
]
NOTES = {
    "Пользователи и форум": "Голос уникален по паре (user_id, question_id). group_homework привязана к номеру группы текстом: таблицы групп нет. "
                            "Курсы СДО обновляются при каждом входе через ЭИОС.",
    "Объединения и задачи": "attachments ссылается ровно на одну сущность: задачу, пост, событие или достижение (ссылки на events и manual_achievements "
                            "ведут на следующую страницу). У задачи association_id пустой для личных задач. "
                            "Заявка и место в объединении хранятся одной строкой memberships (статус pending, approved, rejected, left, removed).",
    "События, достижения, брони": "Запись, снятие со списка и отзыв уникальны по паре (event_id, user_id). У события scope: association или institute. "
                                  "Отменённые брони остаются для истории.",
    "Турнир племён, биты, магазин": "tournaments.winner_tribe_id хранится числом без внешнего ключа. Заказ копирует название и цену товара, "
                                    "а item_id при удалении товара обнуляется.",
}
# Optional manual vertical nudges: table -> extra y offset (px) applied on top of the stacked position.
NUDGE = {}


def row_text(col, on_page):
    t = TYPE_NAMES.get(str(col.type).split("(")[0], str(col.type).lower())
    text = f"{col.name}  {t}{'?' if col.nullable and not col.primary_key else ''}"
    fk = next(iter(col.foreign_keys), None)
    if fk is not None:
        text += f"  → {fk.column.table.name}"
    return text, fk


def box_size(name, on_page):
    t = TABLES[name]
    longest = max([len(row_text(c, on_page)[0]) for c in t.columns] + [len(name) + 2])
    w = max(210, int(KEY_W + 7.2 * longest + 20))
    return w, HEAD_H + ROW_H * len(t.columns)


def fk_edges(names):
    """(parent, child, nullable) for every FK between two tables of the page."""
    out = []
    for n in names:
        for c in TABLES[n].columns:
            for fk in c.foreign_keys:
                p = fk.column.table.name
                if p in names and p != n:
                    out.append((p, n, c.nullable))
    return out


def layout(columns):
    pos, x = {}, 0
    for dy, tables in columns:
        sizes = [box_size(t, None) for t in tables]
        cw = max(s[0] for s in sizes)
        y = TOP + dy
        for t, (w, h) in zip(tables, sizes):
            y_t = y + NUDGE.get(t, 0)
            pos[t] = dict(x=x + (cw - w) / 2 if False else x, y=y_t, w=cw, h=h, col=x)
            y += h + ROW_GAP
        x += cw + COL_GAP
    return pos


def route(edges, pos):
    """Return a dict edge -> (exit(fx,fy), entry(fx,fy), waypoints)."""
    side_use = defaultdict(list)  # (table, side) -> [(edge_idx, other_center)]
    vgaps = defaultdict(list)
    hgaps = defaultdict(list)
    kinds = {}
    for i, (p, c, _n) in enumerate(edges):
        a, b = pos[p], pos[c]
        if a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]:
            left, right = (p, c) if a["x"] < b["x"] else (c, p)
            kinds[i] = "h"
            side_use[(left, "r")].append((i, pos[right]["y"] + pos[right]["h"] / 2))
            side_use[(right, "l")].append((i, pos[left]["y"] + pos[left]["h"] / 2))
            hgaps[(pos[left]["x"] + pos[left]["w"], pos[right]["x"])].append(i)
        else:
            top, bot = (p, c) if a["y"] < b["y"] else (c, p)
            kinds[i] = "v"
            vgaps[(top, bot)].append(i)
    res = {}
    # horizontal edges: spread attachment points along sides, stagger the vertical mid-segment
    attach = {}
    for (t, side), lst in side_use.items():
        lst.sort(key=lambda e: e[1])
        n = len(lst)
        for k, (i, _o) in enumerate(lst):
            f = (k + 1) / (n + 1)
            attach[(i, t)] = f
    for (x0, x1), idxs in hgaps.items():
        ys = {}
        for i in idxs:
            p, c, _n = edges[i]
            ys[i] = (attach[(i, p)], attach[(i, c)])
        idxs = sorted(idxs, key=lambda i: (pos[edges[i][0]]["y"] + ys[i][0] * pos[edges[i][0]]["h"] +
                                           pos[edges[i][1]]["y"] + ys[i][1] * pos[edges[i][1]]["h"]))
        m = len(idxs)
        for k, i in enumerate(idxs):
            p, c, _n = edges[i]
            a, b = pos[p], pos[c]
            fa, fb = attach[(i, p)], attach[(i, c)]
            y1, y2 = a["y"] + fa * a["h"], b["y"] + fb * b["h"]
            xm = x0 + (x1 - x0) * (k + 1) / (m + 1)
            a_right = a["x"] < b["x"]
            ex = (1 if a_right else 0, fa)
            en = (0 if a_right else 1, fb)
            res[i] = (ex, en, [(xm, y1), (xm, y2)])
    for (top, bot), idxs in vgaps.items():
        a, b = pos[top], pos[bot]
        lo, hi = max(a["x"], b["x"]), min(a["x"] + a["w"], b["x"] + b["w"])
        m = len(idxs)
        for k, i in enumerate(idxs):
            p, c, _n = edges[i]
            x = lo + (hi - lo) * (k + 1) / (m + 1)
            fa_t, fb_t = (x - a["x"]) / a["w"], (x - b["x"]) / b["w"]
            top_is_parent = p == top
            ex = (fa_t, 1) if top_is_parent else (fb_t, 0)
            en = (fb_t, 0) if top_is_parent else (fa_t, 1)
            res[i] = (ex, en, [])
    return res


class Doc:
    def __init__(self):
        self.pages = []

    def add_page(self, name, cells):
        self.pages.append((name, cells))

    def xml(self):
        out = ['<mxfile host="app.diagrams.net">']
        for n, (name, cells) in enumerate(self.pages):
            out.append(f'<diagram id="p{n}" name="{escape(name)}"><mxGraphModel dx="1400" dy="900" grid="0" gridSize="10" '
                       f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" math="0" shadow="0" '
                       f'background="#ffffff"><root><mxCell id="0"/><mxCell id="1" parent="0"/>')
            out.extend(cells)
            out.append("</root></mxGraphModel></diagram>")
        out.append("</mxfile>")
        return "\n".join(out)


def cell(id_, value, style, x, y, w, h, parent="1", vertex=True):
    return (f'<mxCell id="{id_}" value="{escape(value, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" as="geometry"/></mxCell>')


def table_cells(name, p, colour, on_page, uid):
    head, border = PALETTE[colour]
    t = TABLES[name]
    cells = [cell(uid, name,
                  f"swimlane;fontStyle=1;fontSize=13;startSize={HEAD_H};horizontal=1;collapsible=0;rounded=0;html=1;"
                  f"fillColor={head};strokeColor={border};fontColor=#1b2330;swimlaneFillColor=#ffffff;",
                  p["x"], p["y"], p["w"], p["h"])]
    pk = {c.name for c in t.primary_key.columns}
    uq = {c.name for c in t.columns if c.unique}
    for i, c in enumerate(t.columns):
        text, fk = row_text(c, on_page)
        cross = fk is not None and fk.column.table.name not in on_page
        key = "PK" if c.name in pk else ("FK" if fk is not None else ("UK" if c.name in uq else ""))
        y = HEAD_H + i * ROW_H
        fill = "#f4f6f8" if i % 2 == 0 else "#ffffff"
        cells.append(cell(f"{uid}_k{i}", key,
                          f"text;html=1;align=center;verticalAlign=middle;fontSize=10;fontStyle=1;fontColor={border};"
                          f"fillColor={fill};strokeColor=#e3e7ec;rounded=0;spacing=0;", 0, y, KEY_W, ROW_H, uid))
        style = ("text;html=1;align=left;verticalAlign=middle;spacingLeft=6;fontSize=12;fillColor=%s;strokeColor=#e3e7ec;rounded=0;"
                 "fontColor=%s;fontStyle=%d;") % (fill, "#8a94a3" if cross else "#1b2330", 1 if key == "PK" else (2 if fk is not None else 0))
        cells.append(cell(f"{uid}_v{i}", text, style, KEY_W, y, p["w"] - KEY_W, ROW_H, uid))
    return cells


def edge_cell(i, src, dst, nullable, ex, en, pts, uid):
    start = "ERzeroToOne" if nullable else "ERmandOne"
    style = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;orthogonalLoop=1;jettySize=auto;strokeColor=#5b6676;strokeWidth=1.5;"
             f"startArrow={start};startFill=0;endArrow=ERmany;endFill=0;"
             f"exitX={ex[0]:.4f};exitY={ex[1]:.4f};exitDx=0;exitDy=0;entryX={en[0]:.4f};entryY={en[1]:.4f};entryDx=0;entryDy=0;")
    points = "".join(f'<mxPoint x="{x:g}" y="{y:g}"/>' for x, y in pts)
    arr = f'<Array as="points">{points}</Array>' if pts else ""
    return (f'<mxCell id="{uid}" style="{style}" edge="1" parent="1" source="{src}" target="{dst}">'
            f'<mxGeometry relative="1" as="geometry">{arr}</mxGeometry></mxCell>')


LEGEND = ("PK — первичный ключ · FK → таблица — внешний ключ (серым: таблица на другой странице) · "
          "UK — уникальное поле · «?» — допускает NULL · линия: «один» — «много»")


def build_page(title, colour, columns):
    names = [t for _d, ts in columns for t in ts]
    pos = layout(columns)
    cells = [cell("title", title, "text;html=1;align=left;verticalAlign=middle;fontSize=22;fontStyle=1;fontColor=#1b2330;strokeColor=none;fillColor=none;",
                  0, 0, 700, 36),
             cell("legend", LEGEND, "text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontSize=11;fontColor=#5b6676;strokeColor=none;fillColor=none;",
                  0, 40, 900, 30)]
    for n in names:
        cells += table_cells(n, pos[n], "users" if n == "users" else colour, set(names), f"t_{n}")
    edges = fk_edges(names)
    routes = route(edges, pos)
    for i, (p, c, nul) in enumerate(edges):
        ex, en, pts = routes[i]
        cells.append(edge_cell(i, f"t_{p}", f"t_{c}", nul, ex, en, pts, f"e_{p}_{c}_{i}"))
    bottom = max(p["y"] + p["h"] for p in pos.values()) + 40
    cells.append(cell("note", "Примечания: " + NOTES[title], "text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontSize=11;fontColor=#5b6676;strokeColor=none;fillColor=none;",
                      0, bottom, 900, 50))
    return cells, pos, edges, routes


# ---- General page: every table, every FK, lines routed around the boxes on a 10px grid ----
G = 10
CLUSTERS = {  # title, palette key, columns (tables top to bottom)
    "forum": ("Форум и учёба", [["forum_answers", "forum_questions", "votes"], ["sdo_courses", "group_homework"]]),
    "tribes": ("Турнир, биты, магазин", [["bits_grants", "tournaments", "tribe_members"],
                                        ["tribes", "tribe_awards"], ["shop_items", "shop_orders"]]),
    "events": ("События, достижения, брони", [["event_registrations", "event_removals", "event_feedback"],
                                               ["events", "bookings", "manual_achievements"]]),
    "assoc": ("Объединения и задачи", [["task_assignees", "task_comments", "association_post_recipients"],
                                       ["tasks", "attachments", "association_posts"], ["associations"],
                                       ["memberships", "meetings", "meeting_attendance"]]),
}
LOOSE = ["teachers", "announcements", "faq_items", "subjects", "revoked_tokens"]


def rows_for(name, mode):
    """Rows of a table box: (key, text, is_fk). 'keys' mode shows only PK/FK/UK columns plus a counter."""
    t = TABLES[name]
    pk = {c.name for c in t.primary_key.columns}
    rows, hidden = [], 0
    for c in t.columns:
        text, fk = row_text(c, None)
        key = "PK" if c.name in pk else ("FK" if fk is not None else ("UK" if c.unique else ""))
        if mode == "keys" and not key:
            hidden += 1
            continue
        rows.append((key, text, fk is not None))
    if hidden:
        rows.append(("", f"+ ещё полей: {hidden}", None))
    return rows


def gsize(name, mode):
    rows = rows_for(name, mode)
    longest = max([len(r[1]) for r in rows] + [len(name) + 2])
    w = -(-int(KEY_W + 7.2 * longest + 20) // G) * G
    return max(200, w), HEAD_H + ROW_H * len(rows)


def place_cluster(columns, x0, y0, col_gap=90, row_gap=60):
    pos, x, tw, th = {}, x0, 0, 0
    for col in columns:
        sizes = [gsize(t, "keys") for t in col]
        cw = max(w for w, _h in sizes)
        y = y0
        for t, (_w, h) in zip(col, sizes):
            pos[t] = dict(x=x, y=y, w=cw, h=h)
            y += h + row_gap
        th = max(th, y - row_gap - y0)
        x += cw + col_gap
    return pos, x - col_gap - x0, th


def slots(b):
    """Free attachment points on every side of a box: (side, px, py, outward dx, dy)."""
    out = []
    for yy in range(b["y"] + HEAD_H + 10, b["y"] + b["h"], 20):
        out.append(("l", b["x"], yy, -1, 0))
        out.append(("r", b["x"] + b["w"], yy, 1, 0))
    for xx in range(b["x"] + 20, b["x"] + b["w"], 20):
        out.append(("t", xx, b["y"], 0, -1))
        out.append(("b", xx, b["y"] + b["h"], 0, 1))
    return out


def route_all(boxes, edges):
    """Dijkstra on a grid: turns and re-used cells cost extra, cells near any box are blocked."""
    import heapq
    xs = [b["x"] for b in boxes.values()] + [b["x"] + b["w"] for b in boxes.values()]
    ys = [b["y"] for b in boxes.values()] + [b["y"] + b["h"] for b in boxes.values()]
    x_lo, x_hi, y_lo, y_hi = min(xs) - 80, max(xs) + 80, min(ys) - 80, max(ys) + 80
    blocked = set()
    for b in boxes.values():
        for px in range((b["x"] - 14) // G * G, b["x"] + b["w"] + 15, G):
            for py in range((b["y"] - 14) // G * G, b["y"] + b["h"] + 15, G):
                if b["x"] - 15 < px < b["x"] + b["w"] + 15 and b["y"] - 15 < py < b["y"] + b["h"] + 15:
                    blocked.add((px, py))
    free_slots = {n: slots(b) for n, b in boxes.items()}
    used = defaultdict(lambda: [0, 0])  # cell -> [horizontal uses, vertical uses]
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    def centre(n):
        b = boxes[n]
        return b["x"] + b["w"] / 2, b["y"] + b["h"] / 2

    order = sorted(range(len(edges)), key=lambda i: abs(centre(edges[i][0])[0] - centre(edges[i][1])[0]) +
                   abs(centre(edges[i][0])[1] - centre(edges[i][1])[1]))
    result = {}
    for i in order:
        src, dst = edges[i][0], edges[i][1]
        goals = {}
        for sl in free_slots[dst]:
            cell_ = (sl[1] + sl[3] * 2 * G, sl[2] + sl[4] * 2 * G)
            if cell_ not in blocked:
                goals[cell_] = sl
        heap, best, prev = [], {}, {}
        for sl in free_slots[src]:
            cell_ = (sl[1] + sl[3] * 2 * G, sl[2] + sl[4] * 2 * G)
            if cell_ in blocked:
                continue
            d = dirs.index((sl[3], sl[4]))
            st = (cell_, d)
            best[st] = 0
            prev[st] = ("start", sl)
            heapq.heappush(heap, (0, cell_, d))
        found = None
        while heap:
            cost, cell_, d = heapq.heappop(heap)
            if best.get((cell_, d), 1e18) < cost:
                continue
            if cell_ in goals:
                found = (cell_, d)
                break
            for nd, (dx, dy) in enumerate(dirs):
                if (dx, dy) == (-dirs[d][0], -dirs[d][1]):
                    continue
                nx, ny = cell_[0] + dx * G, cell_[1] + dy * G
                if (nx, ny) in blocked or not (x_lo <= nx <= x_hi and y_lo <= ny <= y_hi):
                    continue
                horiz = dy == 0
                u = used[(nx, ny)]
                step = 1 + (6 if nd != d else 0) + (30 if u[0 if horiz else 1] else 0) + (8 if u[1 if horiz else 0] else 0)
                nc = cost + step
                if nc < best.get(((nx, ny), nd), 1e18):
                    best[((nx, ny), nd)] = nc
                    prev[((nx, ny), nd)] = (cell_, d)
                    heapq.heappush(heap, (nc, (nx, ny), nd))
        if found is None:
            raise RuntimeError(f"no route for {edges[i]}")
        path, st = [], found
        while True:
            path.append(st[0])
            p_ = prev[st]
            if p_[0] == "start":
                start_slot = p_[1]
                break
            st = p_
        path.reverse()
        end_slot = goals[found[0]]
        for k, c in enumerate(path):
            if k:
                horiz = c[1] == path[k - 1][1]
                used[c][0 if horiz else 1] += 1
        used[path[0]][0 if start_slot[4] == 0 else 1] += 1
        free_slots[src].remove(start_slot)
        free_slots[dst].remove(end_slot)
        pts = [(start_slot[1], start_slot[2])] + path + [(end_slot[1], end_slot[2])]
        simp = [pts[0]]
        for k in range(1, len(pts) - 1):
            a, b, c = pts[k - 1], pts[k], pts[k + 1]
            if (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1]):
                continue
            simp.append(b)
        simp.append(pts[-1])
        result[i] = (start_slot, end_slot, simp)
    return result


def general_layout():
    """users in the middle; forum on its left, associations on its right, tournament above, events below."""
    pad_x, pad_top, pad_bot, gap = 40, 50, 40, 160
    sizes = {k: place_cluster(cols, 0, 0) for k, (_t, cols) in CLUSTERS.items()}
    users_w, users_h = gsize("users", "full")
    users_w = max(users_w, 340)
    full = {k: (v[1] + 2 * pad_x, v[2] + pad_top + pad_bot) for k, v in sizes.items()}
    mid_w = max(users_w, full["events"][0], full["tribes"][0])
    placed, groups = {}, {}

    def put(key, gx, gy):
        pos, w, h = sizes[key]
        for n, b in pos.items():
            placed[n] = dict(b, x=b["x"] + gx + pad_x, y=b["y"] + gy + pad_top)
        groups[key] = (gx, gy, full[key][0], full[key][1])

    mid_x = full["forum"][0] + gap
    centred = lambda w: (mid_w - w) // 2 // G * G
    put("tribes", mid_x + centred(full["tribes"][0]), 0)
    users_y = full["tribes"][1] + gap
    placed["users"] = dict(x=mid_x + centred(users_w), y=users_y, w=users_w, h=users_h)
    put("events", mid_x + centred(full["events"][0]), users_y + users_h + gap)
    put("forum", 0, (users_y + users_h // 2 - full["forum"][1] // 2) // G * G)
    put("assoc", mid_x + mid_w + gap, users_y)
    loose_y = max(g[1] + g[3] for g in groups.values()) + gap
    x = 0
    for n in LOOSE:
        w, h = gsize(n, "keys")
        placed[n] = dict(x=x + pad_x, y=loose_y + pad_top, w=w, h=h)
        x += w + 60
    groups["loose"] = (0, loose_y, x - 60 + 2 * pad_x, max(placed[n]["h"] for n in LOOSE) + pad_top + pad_bot)
    return placed, groups


DOMAIN_OF = {n: k for k, (_t, cols) in CLUSTERS.items() for col in cols for n in col}
DOMAIN_OF["users"] = "users"


def general_page():
    boxes, groups = general_layout()
    edges = [(p, c, nul) for n in boxes for (p, c, nul) in fk_edges(list(boxes)) if c == n]
    routed = route_all(boxes, edges)
    cells = [cell("title", "Общая схема: все таблицы и связи", "text;html=1;align=left;verticalAlign=middle;fontSize=22;fontStyle=1;fontColor=#1b2330;strokeColor=none;fillColor=none;",
                  0, -110, 800, 36),
             cell("legend", "Показаны ключи: PK, FK (→ таблица) и UK, остальные поля свёрнуты в «+ ещё полей». Полные списки полей — на следующих страницах. "
                  "Цвет линии к users совпадает с цветом области, остальные связи серые. Линия: «один» — «много».",
                  "text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontSize=11;fontColor=#5b6676;strokeColor=none;fillColor=none;", 0, -70, 1100, 34)]
    titles = {k: v[0] for k, v in CLUSTERS.items()}
    titles["loose"] = "Справочники (без связей)"
    for key, (gx, gy, gw, gh) in groups.items():
        head, border = PALETTE.get(key, ("#eceff3", "#8a94a3"))
        cells.append(cell(f"grp_{key}", titles[key], "rounded=0;html=1;verticalAlign=top;align=left;spacingLeft=14;spacingTop=8;fontStyle=1;fontSize=14;"
                          f"fillColor={head};strokeColor={border};fontColor=#1b2330;opacity=45;textOpacity=100;dashed=0;", gx, gy, gw, gh))
    for n, b in boxes.items():
        key = DOMAIN_OF.get(n, "loose")
        colour = "users" if n == "users" else (key if key in PALETTE else "forum")
        head, border = PALETTE[colour] if n != "loose" else PALETTE["forum"]
        if n in LOOSE:
            head, border = "#eceff3", "#8a94a3"
        uid = f"g_{n}"
        cells.append(cell(uid, n, f"swimlane;fontStyle=1;fontSize=13;startSize={HEAD_H};horizontal=1;collapsible=0;rounded=0;html=1;"
                          f"fillColor={head};strokeColor={border};fontColor=#1b2330;swimlaneFillColor=#ffffff;", b["x"], b["y"], b["w"], b["h"]))
        for i, (k, text, is_fk) in enumerate(rows_for(n, "full" if n == "users" else "keys")):
            fill = "#f4f6f8" if i % 2 == 0 else "#ffffff"
            y = HEAD_H + i * ROW_H
            cells.append(cell(f"{uid}_k{i}", k, f"text;html=1;align=center;verticalAlign=middle;fontSize=10;fontStyle=1;fontColor={border};"
                              f"fillColor={fill};strokeColor=#e3e7ec;rounded=0;spacing=0;", 0, y, KEY_W, ROW_H, uid))
            muted = is_fk is None
            style = (f"text;html=1;align=left;verticalAlign=middle;spacingLeft=6;fontSize=12;fillColor={fill};strokeColor=#e3e7ec;rounded=0;"
                     f"fontColor={'#8a94a3' if muted else '#1b2330'};fontStyle={1 if k == 'PK' else (2 if is_fk or muted else 0)};")
            cells.append(cell(f"{uid}_v{i}", text, style, KEY_W, y, b["w"] - KEY_W, ROW_H, uid))
    for i, (p, c, nul) in enumerate(edges):
        s_slot, e_slot, pts = routed[i]
        a, b = boxes[p], boxes[c]
        ex = ((s_slot[1] - a["x"]) / a["w"], (s_slot[2] - a["y"]) / a["h"])
        en = ((e_slot[1] - b["x"]) / b["w"], (e_slot[2] - b["y"]) / b["h"])
        colour = PALETTE[DOMAIN_OF[c]][1] if p == "users" else "#5b6676"
        start = "ERzeroToOne" if nul else "ERmandOne"
        style = (f"rounded=0;html=1;strokeColor={colour};strokeWidth=1.5;startArrow={start};startFill=0;endArrow=ERmany;endFill=0;"
                 f"exitX={ex[0]:.4f};exitY={ex[1]:.4f};exitDx=0;exitDy=0;entryX={en[0]:.4f};entryY={en[1]:.4f};entryDx=0;entryDy=0;")
        mid = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts[1:-1])
        cells.append(f'<mxCell id="ge_{i}" style="{style}" edge="1" parent="1" source="g_{p}" target="g_{c}">'
                     f'<mxGeometry relative="1" as="geometry"><Array as="points">{mid}</Array></mxGeometry></mxCell>')
    return cells


def main():
    out = sys.argv[1]
    doc = Doc()
    doc.add_page("Общая схема", general_page())
    for title, colour, columns in PAGES:
        cells = build_page(title, colour, columns)[0]
        doc.add_page(title, cells)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc.xml())


if __name__ == "__main__":
    main()
