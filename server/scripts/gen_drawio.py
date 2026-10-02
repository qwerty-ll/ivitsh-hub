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
ROW_H, HEAD_H, KEY_W, COL_GAP, ROW_GAP, TOP = 20, 28, 34, 130, 44, 90

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


def overview():
    """Hub-and-spoke: users in the middle, the four domains around it."""
    RIGHT_X = 860
    groups = {
        "forum": ("Форум и учёба", ["forum_questions", "forum_answers", "votes", "sdo_courses", "group_homework"], 0, 0),
        "assoc": ("Объединения и задачи", ["associations", "memberships", "tasks", "task_assignees", "task_comments", "association_posts",
                                          "association_post_recipients", "meetings", "meeting_attendance", "attachments"], RIGHT_X, 0),
        "events": ("События и брони", ["events", "event_registrations", "event_removals", "event_feedback", "manual_achievements", "bookings"], 0, 420),
        "tribes": ("Турнир, биты, магазин", ["tournaments", "tribes", "tribe_members", "tribe_awards", "bits_grants", "shop_items", "shop_orders"], RIGHT_X, 420),
    }
    cells = [cell("title", "Обзор: пользователь в центре", "text;html=1;align=left;verticalAlign=middle;fontSize=22;fontStyle=1;fontColor=#1b2330;strokeColor=none;fillColor=none;", 0, 0, 700, 36),
             cell("legend", "Справочники без связей: teachers, announcements, faq_items, subjects, revoked_tokens (revoked_tokens — на странице форума). events и bookings ссылаются на associations. Подробные схемы — на следующих страницах.",
                  "text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontSize=11;fontColor=#5b6676;strokeColor=none;fillColor=none;", 0, 40, 900, 30)]
    W, base_y = 290, 90
    box = {}
    for key, (title, tabs, x, y) in groups.items():
        head, border = PALETTE[key]
        h = HEAD_H + 8 + 20 * len(tabs) + 8
        box[key] = (x, y + base_y, W, h)
        body = "<br>".join(tabs)
        cells.append(cell(f"g_{key}", title, f"swimlane;fontStyle=1;fontSize=13;startSize={HEAD_H};horizontal=1;collapsible=0;rounded=0;html=1;"
                          f"fillColor={head};strokeColor={border};fontColor=#1b2330;swimlaneFillColor=#ffffff;", x, y + base_y, W, h))
        cells.append(cell(f"g_{key}_t", body, "text;html=1;align=left;verticalAlign=top;spacingLeft=10;spacingTop=6;fontSize=12;fontFamily=Courier New;"
                          "fillColor=none;strokeColor=none;fontColor=#1b2330;", 0, HEAD_H, W, h - HEAD_H, f"g_{key}"))
    # users in the middle between the columns
    users_w, users_h = 220, 80
    cx = (W + RIGHT_X) / 2 - users_w / 2
    cy = base_y + 210 - users_h / 2 + 10
    cells.append(cell("g_users", "users", "swimlane;fontStyle=1;fontSize=13;startSize=%d;horizontal=1;collapsible=0;rounded=0;html=1;fillColor=%s;strokeColor=%s;"
                      "fontColor=#1b2330;swimlaneFillColor=#ffffff;" % (HEAD_H, *PALETTE["users"]), cx, cy, users_w, users_h))
    cells.append(cell("g_users_t", "id, username, role, group_number…", "text;html=1;align=center;verticalAlign=middle;fontSize=12;fillColor=none;strokeColor=none;fontColor=#5b6676;",
                      0, HEAD_H, users_w, users_h - HEAD_H, "g_users"))
    # spokes: straight lines to the near corner of each group so they do not cross the boxes
    spokes = [("forum", "users", "вопросы, ответы, голоса"), ("assoc", "users", "заявки, задачи, посты"),
              ("events", "users", "записи, отзывы, брони"), ("tribes", "users", "племена, биты, заказы")]
    for key, _u, label in spokes:
        gx, gy, gw, gh = box[key]
        left = gx < cx
        up = gy < cy
        ex_x = 0 if left else 1
        ex_y = 0.3 if up else 0.7
        en_x = 1 if left else 0
        cells.append(f'<mxCell id="s_{key}" value="{escape(label)}" style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#5b6676;strokeWidth=1.5;'
                     f'startArrow=ERmandOne;startFill=0;endArrow=ERmany;endFill=0;fontSize=11;fontColor=#5b6676;labelBackgroundColor=#ffffff;'
                     f'exitX={ex_x};exitY={ex_y};exitDx=0;exitDy=0;entryX={en_x};entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="g_users" target="g_{key}">'
                     f'<mxGeometry relative="1" as="geometry"/></mxCell>')
    return cells


def main():
    out = sys.argv[1]
    doc = Doc()
    doc.add_page("Обзор", overview())
    for title, colour, columns in PAGES:
        cells = build_page(title, colour, columns)[0]
        doc.add_page(title, cells)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc.xml())


if __name__ == "__main__":
    main()
