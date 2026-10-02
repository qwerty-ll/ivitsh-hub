"""Generate docs/uml-diagrams.drawio: use case, state, activity (swimlane) and sequence diagrams.

Every shape and every line is placed by hand-written coordinates (no auto layout), so draw.io shows exactly
what is described here. Usage (no database needed):
    python server/scripts/gen_uml_drawio.py docs/uml-diagrams.drawio [PREVIEW_DIR]
PREVIEW_DIR is optional and needs Pillow: it writes one PNG per page to check the layout without draw.io.
"""
import math
import sys
from xml.sax.saxutils import escape

COLORS = {  # fill, stroke
    "blue": ("#dae8fc", "#6c8ebf"), "green": ("#d5e8d4", "#82b366"), "yellow": ("#fff2cc", "#d6b656"),
    "red": ("#f8cecc", "#b85450"), "purple": ("#e1d5e7", "#9673a6"), "grey": ("#f1f3f5", "#7a8591"),
    "white": ("#ffffff", "#5b6676"),
}
INK, MUTED, LINE = "#1b2330", "#5b6676", "#374151"


class Page:
    def __init__(self, name):
        self.name, self.shapes, self.edges = name, {}, []

    def shape(self, id_, kind, x, y, w, h, text="", color="white", **kw):
        self.shapes[id_] = dict(id=id_, kind=kind, x=x, y=y, w=w, h=h, text=text, color=color, **kw)

    def text(self, id_, x, y, w, h, text, size=12, align="left", color=MUTED, bold=False):
        self.shape(id_, "text", x, y, w, h, text, size=size, align=align, tcolor=color, bold=bold)

    def edge(self, src=None, dst=None, ex=None, en=None, wp=(), pts=None, label="", dashed=False,
             end="block", start="none", lpos=0.0):
        self.edges.append(dict(src=src, dst=dst, ex=ex, en=en, wp=list(wp), pts=pts, label=label, dashed=dashed,
                               end=end, start=start, lpos=lpos))

    def point(self, sid, f):
        s = self.shapes[sid]
        return s["x"] + f[0] * s["w"], s["y"] + f[1] * s["h"]

    def edge_points(self, e):
        if e["pts"] is not None:
            return e["pts"]
        return [self.point(e["src"], e["ex"])] + e["wp"] + [self.point(e["dst"], e["en"])]

    def link(self, a, sa, b, sb, fa=0.5, fb=0.5, m=0.5, ly=None, **kw):
        """Orthogonal line from side sa of shape a to side sb of shape b, with waypoints computed here."""
        side = {"r": lambda f: (1, f), "l": lambda f: (0, f), "t": lambda f: (f, 0), "b": lambda f: (f, 1)}
        ex, en = side[sa](fa), side[sb](fb)
        p1, p2 = self.point(a, ex), self.point(b, en)
        wp = []
        if (sa, sb) in (("r", "l"), ("l", "r")):
            if abs(p1[1] - p2[1]) > 3:
                xm = p1[0] + (p2[0] - p1[0]) * m
                wp = [(xm, p1[1]), (xm, p2[1])]
        elif (sa, sb) in (("b", "t"), ("t", "b")):
            if abs(p1[0] - p2[0]) > 3:
                ym = p1[1] + (p2[1] - p1[1]) * m
                wp = [(p1[0], ym), (p2[0], ym)]
        elif sa == sb:
            if sa == "r":
                x = max(p1[0], p2[0]) + 40
                wp = [(x, p1[1]), (x, p2[1])]
            elif sa == "l":
                x = min(p1[0], p2[0]) - 40
                wp = [(x, p1[1]), (x, p2[1])]
            elif sa == "t":
                y = min(p1[1], p2[1]) - (ly or 30)
                wp = [(p1[0], y), (p2[0], y)]
            else:
                y = max(p1[1], p2[1]) + (ly or 30)
                wp = [(p1[0], y), (p2[0], y)]
        elif sa in "rl":
            wp = [(p2[0], p1[1])]
        else:
            wp = [(p1[0], p2[1])]
        self.edge(a, b, ex, en, wp, **kw)


# ---- draw.io backend --------------------------------------------------------------------------------------

def _fill(color):
    f, s = COLORS[color]
    return f"fillColor={f};strokeColor={s};"


def shape_style(s):
    k, c = s["kind"], s["color"]
    base = f"html=1;whiteSpace=wrap;fontColor={INK};fontSize={s.get('size', 12)};"
    if k == "text":
        return (f"text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align={s['align']};verticalAlign=top;"
                f"fontSize={s['size']};fontColor={s['tcolor']};fontStyle={1 if s['bold'] else 0};")
    if k == "round":
        return base + "rounded=1;arcSize=18;" + _fill(c)
    if k == "state":
        return base + "rounded=1;arcSize=30;fontSize=13;" + _fill(c)
    if k == "rect":
        return base + "rounded=0;" + _fill(c)
    if k == "ellipse":
        return base + "ellipse;" + _fill(c)
    if k == "diamond":
        return base + "rhombus;" + _fill(c)
    if k == "start":
        return "ellipse;html=1;fillColor=#1b2330;strokeColor=#1b2330;"
    if k == "end":
        return "shape=endState;html=1;fillColor=#1b2330;strokeColor=#1b2330;"
    if k == "actor":
        return "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;fillColor=#ffffff;strokeColor=#374151;strokeWidth=1.5;"
    if k == "frame":
        return f"rounded=0;html=1;whiteSpace=wrap;verticalAlign=top;align=left;spacingLeft=10;spacingTop=4;fontSize=13;fontStyle=1;fontColor={INK};{_fill(c)}dashed={1 if s.get('dashed') else 0};"
    if k == "lane":
        return (f"swimlane;horizontal=0;html=1;startSize=44;fontSize=13;fontStyle=1;fontColor={INK};swimlaneFillColor={s['lane_fill']};"
                + _fill(c))
    if k == "lifeline":
        return f"html=1;rounded=0;fontSize=13;fontStyle=1;{_fill(c)}fontColor={INK};"
    if k == "tag":
        return f"html=1;rounded=0;fontSize=11;fontStyle=1;fontColor={INK};fillColor=#ffffff;strokeColor={LINE};"
    raise ValueError(k)


def cell_xml(s):
    return (f'<mxCell id="{s["id"]}" value="{escape(s["text"], {chr(34): "&quot;"})}" style="{shape_style(s)}" vertex="1" parent="1">'
            f'<mxGeometry x="{s["x"]:g}" y="{s["y"]:g}" width="{s["w"]:g}" height="{s["h"]:g}" as="geometry"/></mxCell>')


ARROWS = {"block": "endArrow=block;endFill=1;", "open": "endArrow=open;endFill=0;", "tri": "endArrow=block;endFill=0;",
          "none": "endArrow=none;"}


def edge_xml(page, i, e):
    pts = page.edge_points(e)
    style = f"html=1;rounded=0;strokeColor={LINE};strokeWidth=1.5;labelBackgroundColor=#ffffff;fontSize=11;fontColor={MUTED};"
    style += ARROWS[e["end"]] + ("startArrow=oval;startFill=1;startSize=4;" if e["start"] == "dot" else "")
    if e["dashed"]:
        style += "dashed=1;"
    attrs = ""
    if e["src"] and e["dst"]:
        style += (f"exitX={e['ex'][0]:.4f};exitY={e['ex'][1]:.4f};exitDx=0;exitDy=0;"
                  f"entryX={e['en'][0]:.4f};entryY={e['en'][1]:.4f};entryDx=0;entryDy=0;")
        attrs = f' source="{e["src"]}" target="{e["dst"]}"'
        inner = "".join(f'<mxPoint x="{x:g}" y="{y:g}"/>' for x, y in e["wp"])
        geo = f'<mxGeometry x="{e["lpos"]:g}" relative="1" as="geometry">' + (f'<Array as="points">{inner}</Array>' if inner else "")
    else:
        mid = "".join(f'<mxPoint x="{x:g}" y="{y:g}"/>' for x, y in pts[1:-1])
        geo = (f'<mxGeometry relative="1" as="geometry"><mxPoint x="{pts[0][0]:g}" y="{pts[0][1]:g}" as="sourcePoint"/>'
               f'<mxPoint x="{pts[-1][0]:g}" y="{pts[-1][1]:g}" as="targetPoint"/>' + (f'<Array as="points">{mid}</Array>' if mid else ""))
    return (f'<mxCell id="edge_{i}" value="{escape(e["label"])}" style="{style}" edge="1" parent="1"{attrs}>{geo}</mxGeometry></mxCell>')


def to_xml(pages):
    out = ['<mxfile host="app.diagrams.net">']
    for n, p in enumerate(pages):
        out.append(f'<diagram id="u{n}" name="{escape(p.name)}"><mxGraphModel dx="1400" dy="900" grid="0" gridSize="10" guides="1" '
                   f'tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" math="0" shadow="0" background="#ffffff">'
                   f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>')
        out += [cell_xml(s) for s in p.shapes.values()]
        out += [edge_xml(p, i, e) for i, e in enumerate(p.edges)]
        out.append("</root></mxGraphModel></diagram>")
    out.append("</mxfile>")
    return "\n".join(out)


# ---- Use case diagrams ------------------------------------------------------------------------------------

def usecase_page(name, title, actors, groups, externals=(), rels=()):
    """actors: [(id, name, parent_id)] top to bottom; groups: [(actor_id, [(case_id, text)])] in the same order.
    externals: [(ext_id, name, case_id)]; rels: [(from_case, to_case, '«include»')] between neighbouring cases."""
    p = Page(name)
    p.text("title", 0, 0, 900, 34, title, size=22, color=INK, bold=True)
    case_x, case_w, case_h, pitch, top = 300, 400, 46, 80, 110
    cases, row = {}, 0
    ordered = []
    for actor, items in groups:
        for cid, text in items:
            cases[cid] = (actor, row)
            ordered.append((cid, text, row))
            row += 1
    height = row * pitch + 50
    p.shape("boundary", "frame", case_x - 30, top - 50, case_w + 60, height, "Система «ИВИТШ Хаб»", color="white")
    for cid, text, r in ordered:
        p.shape(cid, "ellipse", case_x, top + r * pitch, case_w, case_h, text, color="blue", size=12)
    # actors: centred on their group, kept apart so the inheritance arrows have room
    ay, y_prev = {}, -1e9
    for aid, _n, _par in actors:
        rows = [r for (_c, (a, r)) in cases.items() if a == aid]
        centre = top + (min(rows) + max(rows)) / 2 * pitch + case_h / 2
        y = max(centre - 28, y_prev + 150)
        ay[aid], y_prev = y, y
    ax = 190
    for aid, nm, par in actors:
        p.shape(f"a_{aid}", "actor", ax, ay[aid], 36, 56)
        p.text(f"an_{aid}", 8, ay[aid] + 14, 168, 40, nm, size=13, align="right", color=INK, bold=True)
    for aid, _n, par in actors:
        if par:
            p.link(f"a_{aid}", "t", f"a_{par}", "b", end="tri")
    for aid, items in groups:
        for cid, _t in items:
            p.edge(f"a_{aid}", cid, (1, 0.5), (0, 0.5), end="none")
    for k, (eid, nm, cid) in enumerate(externals):
        y = top + cases[cid][1] * pitch
        p.shape(f"x_{eid}", "rect", case_x + case_w + 120, y - 4, 150, 54, f"«система»\n{nm}", color="grey", size=12)
        p.edge(cid, f"x_{eid}", (1, 0.5), (0, 0.5), end="none")
    for a, b, label in rels:
        ra, rb = cases[a][1], cases[b][1]
        if ra < rb:
            p.edge(a, b, (0.5, 1), (0.5, 0), dashed=True, end="open", label=label)
        else:
            p.edge(a, b, (0.5, 0), (0.5, 1), dashed=True, end="open", label=label)
    return p


# ---- State diagrams ---------------------------------------------------------------------------------------

def state_page(name, title, states, transitions, note, size=(900, 380)):
    """states: {id: (kind, x, y, w, h, text, color)} kind in start|end|state; transitions: link() args + label."""
    p = Page(name)
    p.text("title", 0, 0, 900, 34, title, size=22, color=INK, bold=True)
    for sid, (kind, x, y, w, h, text, color) in states.items():
        p.shape(sid, kind, x, y + 50, w, h, text, color=color)
    for a, sa, b, sb, label, kw in transitions:
        kw = dict(kw)
        kw.setdefault("lpos", 0.0)
        p.link(a, sa, b, sb, label=label, **kw)
    bottom = max(s["y"] + s["h"] for s in p.shapes.values())
    p.text("note", 0, bottom + 60, size[0], 60, note, size=12)
    return p


def S(x, y, w=150, h=52, text="", color="blue"):
    return ("state", x, y, w, h, text, color)


START = lambda x, y: ("start", x, y, 20, 20, "", "white")  # noqa: E731
END = lambda x, y: ("end", x, y, 26, 26, "", "white")  # noqa: E731


def state_pages():
    out = []
    out.append(state_page("Состояния: заявка в объединение", "Заявка в объединение (memberships.status)", {
        "s": START(20, 175), "pending": S(200, 160, 170, 52, "На рассмотрении (pending)", "yellow"),
        "approved": S(540, 60, 170, 52, "Участник (approved)", "green"),
        "rejected": S(540, 290, 170, 52, "Отклонена (rejected)", "red"),
        "left": S(900, 60, 160, 52, "Вышел (left)", "grey"),
        "removed": S(900, 175, 160, 52, "Исключён (removed)", "red"),
    }, [
        ("s", "r", "pending", "l", "подал заявку", {}),
        ("pending", "r", "approved", "l", "руководитель одобрил", dict(fa=0.25, m=0.5)),
        ("pending", "r", "rejected", "l", "руководитель отклонил", dict(fa=0.75, fb=0.5, m=0.5)),
        ("rejected", "b", "pending", "b", "студент подал заявку снова", dict(ly=40)),
        ("approved", "r", "left", "l", "студент вышел", dict(fa=0.3, fb=0.3)),
        ("left", "t", "pending", "t", "студент подал заявку снова", dict(ly=40, fa=0.5, fb=0.3)),
        ("approved", "r", "removed", "l", "руководитель исключил", dict(fa=0.75, fb=0.5, m=0.5)),
        ("removed", "l", "approved", "b", "руководитель вернул", dict(fa=0.85, fb=0.5)),
    ], "Студент может отозвать заявку в статусе «на рассмотрении»: запись удаляется. Исключённый не может подать заявку сам. "
       "При выходе или исключении снимаются незавершённые задачи объединения и запись на его будущие мероприятия.", size=(1060, 380)))
    out.append(state_page("Состояния: задача", "Карточка задачи у исполнителя (task_assignees.status)", {
        "s": START(20, 120),
        "todo": S(190, 105, 160, 52, "К выполнению (todo)", "grey"),
        "prog": S(550, 105, 160, 52, "В работе (in_progress)", "blue"),
        "review": S(910, 105, 160, 52, "На проверке (review)", "yellow"),
        "done": S(1270, 105, 160, 52, "Готово (done)", "green"),
        "arch": S(1630, 105, 160, 52, "В архиве", "grey"),
    }, [
        ("s", "r", "todo", "l", "поставили задачу", {}),
        ("todo", "r", "prog", "l", "взял в работу", dict(fa=0.3, fb=0.3)),
        ("prog", "l", "todo", "r", "вернул", dict(fa=0.7, fb=0.7)),
        ("prog", "r", "review", "l", "на проверку", dict(fa=0.3, fb=0.3)),
        ("review", "l", "prog", "r", "вернул", dict(fa=0.7, fb=0.7)),
        ("review", "r", "done", "l", "руководитель принял", dict(fa=0.3, fb=0.3)),
        ("done", "l", "review", "r", "руководитель вернул", dict(fa=0.7, fb=0.7)),
        ("done", "r", "arch", "l", "через день или по кнопке", dict(fa=0.3, fb=0.3)),
        ("arch", "l", "done", "r", "на доску", dict(fa=0.7, fb=0.7)),
    ], "«Готово» ставит руководитель (для задач объединения). При первом переходе в «На проверке» или «Готово» портал записывает время сдачи: "
       "вовремя или с опозданием. Биты начисляются только за принятые задачи со сроком, прожившие не меньше 12 часов.", size=(1800, 380)))
    out.append(state_page("Состояния: заказ в магазине", "Заказ в магазине (shop_orders.status)", {
        "s": START(20, 70),
        "new": S(200, 55, 160, 52, "Оформлен (new)", "yellow"),
        "ready": S(540, 55, 160, 52, "Готов к выдаче (ready)", "blue"),
        "issued": S(880, 55, 160, 52, "Выдан (issued)", "green"),
        "cancel": S(540, 210, 160, 52, "Отменён (cancelled)", "red"),
        "e1": END(1120, 68), "e2": END(790, 223),
    }, [
        ("s", "r", "new", "l", "купил за биты", {}),
        ("new", "r", "ready", "l", "администратор собрал", {}),
        ("ready", "r", "issued", "l", "администратор выдал", {}),
        ("new", "b", "cancel", "l", "студент или администратор", {}),
        ("ready", "b", "cancel", "t", "администратор", {}),
        ("issued", "r", "e1", "l", "", {}),
        ("cancel", "r", "e2", "l", "", {}),
    ], "Студент отменяет заказ сам, пока он «Оформлен»; после этого отменить может только администрация. При отмене биты и остаток товара "
       "возвращаются. Закрытый заказ (выдан или отменён) не меняется.", size=(1160, 320)))
    out.append(state_page("Состояния: турнир", "Турнир трайбов (tournaments.status)", {
        "s": START(20, 70),
        "draft": S(200, 55, 160, 52, "Черновик (draft)", "grey"),
        "active": S(560, 55, 160, 52, "Идёт (active)", "blue"),
        "finished": S(920, 55, 160, 52, "Завершён (finished)", "green"),
        "e": END(1160, 68),
    }, [
        ("s", "r", "draft", "l", "администратор создал", {}),
        ("draft", "r", "active", "l", "запуск турнира", {}),
        ("active", "r", "finished", "l", "завершение", {}),
        ("finished", "r", "e", "l", "", {}),
    ], "Запуск делит студентов на трайбы; он возможен, если участников не меньше, чем трайбов, и нет другого идущего турнира. Очки и составы "
       "меняются только во время турнира. При завершении места фиксируются, участники трайбов 1–3 мест получают биты. "
       "Турнир можно удалить из админки.", size=(1200, 220)))
    out.append(state_page("Состояния: бронь", "Бронь коворкинга 108 и ноутбуков (bookings)", {
        "s": START(20, 70),
        "ok": S(200, 55, 170, 52, "Подтверждена", "green"),
        "cancel": S(620, 20, 170, 52, "Отменена", "red"),
        "ended": S(620, 120, 170, 52, "Состоялась (время вышло)", "grey"),
        "e1": END(900, 33), "e2": END(900, 133),
    }, [
        ("s", "r", "ok", "l", "создана сразу", {}),
        ("ok", "r", "cancel", "l", "автор или администратор", dict(fa=0.3, fb=0.5)),
        ("ok", "r", "ended", "l", "время вышло", dict(fa=0.7, fb=0.5)),
        ("cancel", "r", "e1", "l", "", {}),
        ("ended", "r", "e2", "l", "", {}),
    ], "Бронь подтверждается сразу, без согласования. Отменить можно только ту, что ещё не закончилась, и обязательно с причиной. "
       "Отменённые брони остаются в истории с причиной и именем того, кто отменил.", size=(1000, 260)))
    out.append(state_page("Состояния: мероприятие", "Мероприятие (events)", {
        "s": START(20, 60),
        "open": S(200, 45, 200, 52, "Запись открыта", "green"),
        "closed": S(200, 190, 200, 52, "Запись закрыта", "grey"),
        "run": S(650, 118, 170, 52, "Идёт", "blue"),
        "done": S(980, 118, 170, 52, "Завершено", "yellow"),
        "e": END(1230, 131),
    }, [
        ("s", "r", "open", "l", "создано", {}),
        ("open", "b", "closed", "t", "закрыл запись", dict(fa=0.2, fb=0.2)),
        ("closed", "t", "open", "b", "открыл снова", dict(fa=0.8, fb=0.8)),
        ("open", "r", "run", "l", "время начала", dict(fa=0.5, fb=0.3)),
        ("closed", "r", "run", "l", "время начала", dict(fa=0.5, fb=0.7)),
        ("run", "r", "done", "l", "время окончания", {}),
        ("done", "r", "e", "l", "", {}),
    ], "С начала мероприятия запись, отписка и смена роли закрыты. Организаторы отмечают присутствие; от отметки зависят биты и сводка ПГАС. "
       "После окончания 30 дней можно оставить отзыв (оценка 1–5), если студент участвовал.", size=(1260, 360)))
    return out


# ---- Activity diagrams with swimlanes ---------------------------------------------------------------------

HEAD_W, LANE_H, PITCH, NODE_W, NODE_H, DEC_W, DEC_H, LTOP = 44, 190, 210, 160, 84, 170, 100, 60


def swimlane_page(name, title, lanes, nodes, edges):
    """nodes: {id: (lane, col, kind, text, [color], [dy])}; edges: (a, sa, b, sb, label, kwargs)."""
    p = Page(name)
    p.text("title", 0, 0, 1200, 34, title, size=22, color=INK, bold=True)
    ncols = max(n[1] for n in nodes.values()) + 1
    width = HEAD_W + 30 + ncols * PITCH
    for i, lane in enumerate(lanes):
        p.shape(f"lane{i}", "lane", 0, LTOP + i * LANE_H, width, LANE_H, lane, color=("blue", "green", "yellow")[i % 3],
                lane_fill="#ffffff" if i % 2 else "#f7f8fa")
    for nid, spec in nodes.items():
        lane, col, kind, text = spec[:4]
        color = spec[4] if len(spec) > 4 and spec[4] else "white"
        dy = spec[5] if len(spec) > 5 else 0
        cx = HEAD_W + 30 + col * PITCH + PITCH / 2 - 25
        cy = LTOP + lane * LANE_H + LANE_H / 2 + dy
        w, h = {"task": (NODE_W, NODE_H), "decision": (DEC_W, DEC_H), "start": (26, 26), "end": (30, 30)}[kind]
        p.shape(nid, {"task": "round", "decision": "diamond", "start": "start", "end": "end"}[kind], cx - w / 2, cy - h / 2, w, h,
                text, color=color, size=12)
    for a, sa, b, sb, label, kw in edges:
        kw = dict(kw)
        p.link(a, sa, b, sb, label=label, lpos=kw.pop("lpos", 0.0), **kw)
    return p


T, D, ST, EN = "task", "decision", "start", "end"


def swimlane_pages():
    out = []
    out.append(swimlane_page("Процесс: вступление в объединение", "Процесс: вступление в объединение", ["Студент", "Портал", "Руководитель"], {
        "s": (0, 0, ST, ""), "n2": (0, 1, T, "Выбирает объединение в каталоге и подаёт заявку с запиской"),
        "n3": (1, 2, T, "Создаёт заявку со статусом «на рассмотрении»"), "n4": (2, 3, T, "Видит заявку и контакты студента"),
        "d1": (2, 4, D, "Решение руководителя?", "yellow"),
        "n5": (1, 5, T, "Ставит статус «участник», даёт достижение «Участник объединения»", "green"),
        "n6": (0, 5, T, "Видит отказ, может подать заявку снова", "red"),
        "n7": (0, 6, T, "Получает задачи и объявления объединения"), "e": (0, 7, EN, ""),
    }, [
        ("s", "r", "n2", "l", "", {}), ("n2", "r", "n3", "l", "", {}), ("n3", "r", "n4", "l", "", {}), ("n4", "r", "d1", "l", "", {}),
        ("d1", "r", "n5", "l", "Одобрить", dict(lpos=-0.6)), ("d1", "t", "n6", "l", "Отклонить", dict(lpos=-0.6)),
        ("n5", "r", "n7", "l", "", {}), ("n7", "r", "e", "l", "", {}),
        ("n6", "t", "n2", "t", "подаёт снова", dict(ly=30, lpos=0.0)),
    ]))
    out.append(swimlane_page("Процесс: задача", "Процесс: задача от постановки до принятия", ["Руководитель", "Исполнитель", "Портал"], {
        "s": (0, 0, ST, ""), "n1": (0, 1, T, "Ставит задачу всем или выбранным участникам, указывает срок"),
        "n2": (2, 2, T, "Создаёт каждому исполнителю карточку «К выполнению»"),
        "n3": (1, 3, T, "Берёт в работу, прикладывает файлы и ссылки, пишет комментарии"),
        "n4": (1, 4, T, "Отправляет на проверку"), "n5": (2, 5, T, "Записывает время сдачи: вовремя или с опозданием"),
        "n6": (0, 6, T, "Проверяет работу"), "d1": (0, 7, D, "Принять?", "yellow"),
        "n7": (0, 8, T, "Ставит «Готово»", "green"), "n8": (2, 8, T, "Через день переносит в архив, считает биты"),
        "e": (2, 9, EN, ""), "n9": (1, 7, T, "Читает комментарий и возвращается к работе", "red"),
    }, [
        ("s", "r", "n1", "l", "", {}), ("n1", "r", "n2", "l", "", {}), ("n2", "r", "n3", "l", "", {}), ("n3", "r", "n4", "l", "", {}),
        ("n4", "r", "n5", "l", "", {}), ("n5", "r", "n6", "l", "", {}), ("n6", "r", "d1", "l", "", {}),
        ("d1", "r", "n7", "l", "Да", dict(lpos=-0.6)), ("d1", "b", "n9", "t", "Нет", dict(lpos=-0.6)),
        ("n7", "b", "n8", "t", "", {}), ("n8", "r", "e", "l", "", {}),
        ("n9", "b", "n3", "b", "снова в работе", dict(ly=40)),
    ]))
    out.append(swimlane_page("Процесс: мероприятие", "Процесс: мероприятие и ПГАС", ["Организатор", "Студент", "Портал"], {
        "s": (0, 0, ST, ""), "n1": (0, 1, T, "Создаёт мероприятие: время, место, лимиты участников и волонтёров"),
        "n2": (2, 2, T, "Публикует мероприятие, показывает его в календаре"),
        "n3": (1, 3, T, "Записывается участником или волонтёром до начала"),
        "d1": (2, 4, D, "Есть место, запись открыта?", "yellow"),
        "n4": (1, 5, T, "Видит отказ с причиной", "red", -28), "e1": (1, 5, EN, "", None, 58),
        "n5": (2, 5, T, "Сохраняет запись"),
        "n6": (0, 6, T, "Проводит мероприятие, отмечает присутствие, прикладывает PDF"),
        "n7": (2, 7, T, "Начисляет биты за присутствие, вносит в сводку ПГАС", "green"),
        "n8": (1, 8, T, "Заполняет опрос (1–5 и отзыв), скачивает документы"),
        "n9": (0, 9, T, "Читает отзывы без имён"), "e2": (0, 10, EN, ""),
    }, [
        ("s", "r", "n1", "l", "", {}), ("n1", "r", "n2", "l", "", {}), ("n2", "r", "n3", "l", "", {}), ("n3", "r", "d1", "l", "", {}),
        ("d1", "r", "n5", "l", "Да", dict(lpos=-0.6)), ("d1", "t", "n4", "l", "Нет", dict(lpos=-0.6)), ("n4", "b", "e1", "t", "", {}),
        ("n5", "r", "n6", "l", "", {}), ("n6", "r", "n7", "l", "", {}), ("n7", "r", "n8", "l", "", {}),
        ("n8", "r", "n9", "l", "", {}), ("n9", "r", "e2", "l", "", {}),
    ]))
    out.append(swimlane_page("Процесс: бронь 108", "Процесс: бронь коворкинга 108 («8 бит»)", ["Руководитель", "Портал", "Администратор"], {
        "s": (0, 0, ST, ""), "n1": (0, 1, T, "Выбирает день, зону (верх, низ, всё) или ноутбуки, время и цель"),
        "n2": (1, 2, T, "Проверяет роль, окно 08:00–21:00, срок до 90 дней, лимиты руководителя"),
        "d1": (1, 3, D, "Правила соблюдены?", "yellow"),
        "n3": (0, 4, T, "Видит причину отказа и меняет запрос", "red"),
        "n4": (1, 4, T, "Под блокировкой проверяет пересечения зон и лимит ноутбуков (5)"),
        "d2": (1, 5, D, "Слот свободен?", "yellow"),
        "n5": (0, 6, T, "Видит «Занято: кем и когда», выбирает другое время", "red"),
        "n6": (1, 6, T, "Создаёт бронь сразу, без подтверждения", "green"),
        "n7": (0, 7, T, "Проводит встречу или работу"), "e1": (0, 8, EN, ""),
        "n8": (2, 7, T, "При необходимости отменяет бронь и пишет причину"),
        "n9": (1, 8, T, "Освобождает слот, автор видит причину"), "e2": (1, 9, EN, ""),
    }, [
        ("s", "r", "n1", "l", "", {}), ("n1", "r", "n2", "l", "", {}), ("n2", "r", "d1", "l", "", {}),
        ("d1", "t", "n3", "l", "Нет", dict(lpos=-0.6)), ("d1", "r", "n4", "l", "Да", dict(lpos=-0.6)),
        ("n3", "t", "n1", "t", "меняет запрос", dict(ly=22, fb=0.7, fa=0.5)),
        ("n4", "r", "d2", "l", "", {}), ("d2", "t", "n5", "l", "Нет", dict(lpos=-0.6)), ("d2", "r", "n6", "l", "Да", dict(lpos=-0.6)),
        ("n5", "t", "n1", "t", "выбирает другое время", dict(ly=40, fb=0.3, fa=0.5)),
        ("n6", "r", "n7", "l", "", {}), ("n7", "r", "e1", "l", "", {}),
        ("n6", "b", "n8", "l", "при необходимости", dict(lpos=-0.5)), ("n8", "r", "n9", "l", "", {}), ("n9", "r", "e2", "l", "", {}),
    ]))
    out.append(swimlane_page("Процесс: вход через ЭИОС", "Процесс: вход через ЭИОС и подтягивание курсов СДО", ["Студент", "Портал", "ЭИОС и СДО"], {
        "s": (0, 0, ST, ""), "n1": (0, 1, T, "Вводит логин и пароль ЭИОС, ставит согласие на обработку ПД"),
        "d1": (1, 2, D, "Согласие есть, попыток не слишком много?", "yellow"),
        "n2": (0, 2, T, "Видит ошибку", "red"),
        "n3": (2, 3, T, "Проверяет логин и пароль, отдаёт ФИО, группу, фото"),
        "d2": (1, 4, D, "Данные верны?", "yellow"),
        "n4": (0, 4, T, "Видит «неверный логин или пароль»", "red"),
        "n5": (1, 5, T, "Создаёт или обновляет аккаунт, ставит сессию (cookie)", "green"),
        "n6": (0, 6, T, "Видит главную: «Сегодня» и «Мои задачи»"), "e1": (0, 7, EN, ""),
        "n7": (1, 6, T, "Фоном запрашивает курсы СДО тем же паролем"),
        "n8": (2, 7, T, "Выдаёт список курсов студента"),
        "n9": (1, 8, T, "Сохраняет курсы, пароль не хранит"), "e2": (1, 9, EN, ""),
    }, [
        ("s", "r", "n1", "l", "", {}), ("n1", "r", "d1", "l", "", {}), ("d1", "t", "n2", "b", "Нет", dict(lpos=-0.5)),
        ("d1", "r", "n3", "l", "Да", dict(lpos=-0.6)), ("n3", "r", "d2", "l", "", {}),
        ("d2", "t", "n4", "b", "Нет", dict(lpos=-0.5)), ("d2", "r", "n5", "l", "Да", dict(lpos=-0.6)),
        ("n5", "t", "n6", "l", "", {}), ("n5", "r", "n7", "l", "", {}), ("n7", "r", "n8", "l", "", {}),
        ("n8", "r", "n9", "l", "", {}), ("n9", "r", "e2", "l", "", {}), ("n6", "r", "e1", "l", "", {}),
    ]))
    out.append(swimlane_page("Процесс: покупка в магазине", "Процесс: покупка в магазине за биты", ["Студент", "Портал", "Администратор"], {
        "s": (0, 0, ST, ""), "n1": (0, 1, T, "Выбирает товар и нажимает «Купить»"),
        "n2": (1, 2, T, "Под блокировкой проверяет остаток, лимит «в одни руки» и баланс бит"),
        "d1": (1, 3, D, "Всё в порядке?", "yellow"),
        "n3": (0, 3, T, "Видит причину отказа", "red"),
        "n4": (1, 4, T, "Списывает биты и остаток, создаёт заказ «Оформлен»", "green"),
        "n5": (2, 5, T, "Собирает заказ, ставит «Готов к выдаче»"),
        "n6": (0, 7, T, "Приходит за товаром"), "n7": (2, 8, T, "Выдаёт товар, ставит «Выдан»"), "e1": (2, 9, EN, ""),
        "n8": (0, 5, T, "Отменяет заказ, пока он «Оформлен»", "red"),
        "n9": (1, 6, T, "Возвращает биты и остаток товара", None, -28), "e2": (1, 6, EN, "", None, 58),
    }, [
        ("s", "r", "n1", "l", "", {}), ("n1", "r", "n2", "l", "", {}), ("n2", "r", "d1", "l", "", {}),
        ("d1", "t", "n3", "b", "Нет", dict(lpos=-0.5)), ("d1", "r", "n4", "l", "Да", dict(lpos=-0.6)),
        ("n4", "r", "n5", "l", "", dict(fa=0.7)), ("n4", "r", "n8", "l", "или", dict(fa=0.3, lpos=-0.5)),
        ("n5", "r", "n6", "l", "", dict(m=0.92)), ("n8", "r", "n9", "l", "", {}),
        ("n6", "r", "n7", "l", "", {}), ("n7", "r", "e1", "l", "", {}), ("n9", "b", "e2", "t", "", {}),
    ]))
    out.append(swimlane_page("Процесс: турнир трайбов", "Процесс: турнир трайбов", ["Администратор", "Портал", "Студент"], {
        "s": (0, 0, ST, ""), "n1": (0, 1, T, "Создаёт турнир: даты, 2–8 трайбов, группы, призы"),
        "n2": (0, 2, T, "Запускает турнир"),
        "n3": (1, 3, T, "Делит студентов случайно и поровну, новичков отправляет в самый маленький трайб"),
        "n4": (2, 4, T, "Видит свой трайб, зарабатывает биты"),
        "n5": (0, 5, T, "Начисляет трайбам бонусы или штрафы"),
        "n6": (1, 6, T, "Считает очки: биты участников плюс бонусы администратора"),
        "n7": (0, 7, T, "Завершает турнир"),
        "n8": (1, 8, T, "Фиксирует места, выдаёт биты участникам трайбов 1–3", "green"),
        "n9": (2, 9, T, "Получает биты и тратит их в магазине"), "e": (2, 10, EN, ""),
    }, [
        ("s", "r", "n1", "l", "", {}), ("n1", "r", "n2", "l", "", {}), ("n2", "r", "n3", "l", "", {}), ("n3", "r", "n4", "l", "", {}),
        ("n4", "r", "n5", "l", "", {}), ("n5", "r", "n6", "l", "", {}), ("n6", "r", "n7", "l", "", {}), ("n7", "r", "n8", "l", "", {}),
        ("n8", "r", "n9", "l", "", {}), ("n9", "r", "e", "l", "", {}),
    ]))
    return out


# ---- Sequence diagrams ------------------------------------------------------------------------------------

def sequence_page(name, title, parts, items):
    """items: ('m', a, b, text) | ('r', a, b, text) dashed reply | ('s', a, text) self call |
    ('alt'|'opt', guard) opens a frame | ('else', guard) | ('end',) | ('sep', text)."""
    p = Page(name)
    p.text("title", 0, 0, 1100, 34, title, size=22, color=INK, bold=True)
    pitch, box_w, top = 220, 170, 60
    cx = {n: 90 + i * pitch for i, n in enumerate(parts)}
    for n in parts:
        p.shape(f"p_{n}", "lifeline", cx[n] - box_w / 2, top, box_w, 40, n, color="blue")
    y, stack, k = top + 70, [], 0
    lo, hi = cx[parts[0]] - 90, cx[parts[-1]] + 90
    for it in items:
        k += 1
        t = it[0]
        if t in ("m", "r"):
            a, b, text = it[1], it[2], it[3]
            width = max(abs(cx[a] - cx[b]) - 20, 120)
            lines = max(1, math.ceil(len(text) * 7.2 / width))
            h = lines * 15
            p.text(f"t{k}", min(cx[a], cx[b]) + 10, y, width, h, text, size=11, align="center", color=INK)
            ya = y + h + 8
            p.edge(pts=[(cx[a], ya), (cx[b], ya)], dashed=(t == "r"), end="open" if t == "r" else "block")
            y = ya + 22
        elif t == "s":
            a, text = it[1], it[2]
            lines = max(1, math.ceil(len(text) * 7.2 / 330))
            p.text(f"t{k}", cx[a] + 50, y - 2, 340, lines * 15, text, size=11, color=INK)
            p.edge(pts=[(cx[a], y + 6), (cx[a] + 40, y + 6), (cx[a] + 40, y + 30), (cx[a], y + 30)], end="block")
            y += max(48, lines * 15 + 20)
        elif t in ("alt", "opt"):
            depth = len(stack)
            stack.append(dict(kind=t, y0=y, depth=depth, id=f"f{k}"))
            p.shape(f"g{k}", "tag", lo + depth * 14 + 2, y, 44, 20, t)
            p.text(f"gt{k}", lo + depth * 14 + 52, y + 1, hi - lo - 80, 18, it[1], size=11, color=INK, bold=True)
            y += 34
        elif t == "else":
            st = stack[-1]
            p.edge(pts=[(lo + st["depth"] * 14, y - 4), (hi - st["depth"] * 14, y - 4)], dashed=True, end="none")
            p.text(f"gt{k}", lo + st["depth"] * 14 + 8, y, hi - lo - 80, 18, it[1], size=11, color=INK, bold=True)
            y += 28
        elif t == "end":
            st = stack.pop()
            p.shape(st["id"], "frame", lo + st["depth"] * 14, st["y0"] - 4, hi - lo - 2 * st["depth"] * 14, y - st["y0"] + 4, "", color="white",
                    dashed=False)
            y += 14
        elif t == "sep":
            p.text(f"sep{k}", lo, y, hi - lo, 20, it[1], size=12, align="center", color=MUTED, bold=True)
            p.edge(pts=[(lo, y + 24), (hi, y + 24)], dashed=True, end="none")
            y += 40
    for n in parts:
        p.edge(pts=[(cx[n], top + 40), (cx[n], y + 10)], dashed=True, end="none")
    # frames were added after their content; move them behind by re-ordering shapes
    frames = {s: v for s, v in p.shapes.items() if v["kind"] == "frame"}
    rest = {s: v for s, v in p.shapes.items() if v["kind"] != "frame"}
    p.shapes = {**frames, **rest}
    return p


def sequence_pages():
    out = []
    out.append(sequence_page("Последовательность: вход через ЭИОС", "Последовательность: вход через ЭИОС",
                             ["Студент", "Браузер", "API портала", "ЭИОС КГУ", "БД", "СДО (Moodle)"], [
        ("m", "Студент", "Браузер", "Логин, пароль, согласие на обработку ПД"),
        ("m", "Браузер", "API портала", "POST /auth/eios-login"),
        ("alt", "[нет согласия или пустые поля]"),
        ("r", "API портала", "Браузер", "400: отметьте согласие"),
        ("else", "[слишком много неудачных попыток]"),
        ("r", "API портала", "Браузер", "429: подождите"),
        ("else", "[проверка в ЭИОС]"),
        ("m", "API портала", "ЭИОС КГУ", "authenticate(логин, пароль)"),
        ("alt", "[неверные данные]"),
        ("r", "ЭИОС КГУ", "API портала", "нет такого пользователя"),
        ("r", "API портала", "Браузер", "401, счётчик неудач растёт"),
        ("else", "[VPN заблокирован или ЭИОС недоступен]"),
        ("r", "API портала", "Браузер", "403 или 503 с понятным текстом"),
        ("else", "[успех]"),
        ("r", "ЭИОС КГУ", "API портала", "ФИО, группа, id, фото"),
        ("m", "API портала", "БД", "создать или обновить пользователя, записать согласие ПД"),
        ("r", "БД", "API портала", "готово"),
        ("r", "API портала", "Браузер", "200 и httpOnly-cookie с токеном сессии"),
        ("r", "Браузер", "Студент", "Главная: «Сегодня» и «Мои задачи»"),
        ("end",),
        ("end",),
        ("opt", "[задан SDO_BASE_URL: фоном после ответа]"),
        ("m", "API портала", "СДО (Moodle)", "login/token.php (тот же пароль)"),
        ("r", "СДО (Moodle)", "API портала", "токен"),
        ("m", "API портала", "СДО (Moodle)", "core_enrol_get_users_courses"),
        ("r", "СДО (Moodle)", "API портала", "список курсов"),
        ("m", "API портала", "БД", "сохранить курсы (пароль и токен не хранятся)"),
        ("end",),
    ]))
    out.append(sequence_page("Последовательность: бронь 108", "Последовательность: бронь коворкинга 108",
                             ["Руководитель", "Браузер", "API портала", "БД", "Администратор"], [
        ("m", "Руководитель", "Браузер", "Выбирает зону или ноутбуки, время, цель"),
        ("m", "Браузер", "API портала", "POST /bookings"),
        ("s", "API портала", "роль, окно 08:00–21:00, до 90 дней, лимиты руководителя (6 часов, 10 броней)"),
        ("alt", "[правила нарушены]"),
        ("r", "API портала", "Браузер", "400 или 409 с причиной"),
        ("else", "[правила соблюдены]"),
        ("s", "API портала", "берёт блокировку (процесс и pg_advisory_xact_lock)"),
        ("m", "API портала", "БД", "неотменённые брони, пересекающиеся по времени"),
        ("r", "БД", "API портала", "список броней"),
        ("alt", "[зона занята: «всё помещение» конфликтует с верхом и низом; ноутбуков больше 5]"),
        ("r", "API портала", "Браузер", "409 «Занято: кем и когда»"),
        ("else", "[свободно]"),
        ("m", "API портала", "БД", "INSERT бронь"),
        ("r", "БД", "API портала", "готово"),
        ("r", "API портала", "Браузер", "201: бронь подтверждена сразу"),
        ("r", "Браузер", "Руководитель", "Бронь в списке и в календаре"),
        ("end",),
        ("end",),
        ("sep", "Отмена брони"),
        ("m", "Администратор", "API портала", "POST /bookings/{id}/cancel (причина)"),
        ("alt", "[бронь уже закончилась]"),
        ("r", "API портала", "Администратор", "400: отменить нельзя"),
        ("else", "[ещё идёт или впереди]"),
        ("m", "API портала", "БД", "cancelled_at, cancelled_by, причина"),
        ("r", "API портала", "Администратор", "бронь отменена, слот свободен"),
        ("end",),
    ]))
    out.append(sequence_page("Последовательность: покупка в магазине", "Последовательность: покупка и выдача товара",
                             ["Студент", "Браузер", "API портала", "БД", "Администратор"], [
        ("m", "Студент", "Браузер", "Нажимает «Купить»"),
        ("m", "Браузер", "API портала", "POST /shop/items/{id}/buy"),
        ("s", "API портала", "берёт блокировку магазина: баланс и остаток не должны гоняться"),
        ("m", "API портала", "БД", "товар, остаток, заказы студента, баланс бит"),
        ("r", "БД", "API портала", "данные"),
        ("alt", "[товар закончился, превышен лимит «в одни руки» или не хватает бит]"),
        ("r", "API портала", "Браузер", "409 с причиной"),
        ("else", "[всё в порядке]"),
        ("m", "API портала", "БД", "INSERT заказ (new), списать остаток"),
        ("r", "API портала", "Браузер", "заказ оформлен, баланс уменьшился"),
        ("end",),
        ("opt", "[студент отменяет, пока заказ в статусе new]"),
        ("m", "Браузер", "API портала", "POST /shop/orders/{id}/cancel"),
        ("m", "API портала", "БД", "статус cancelled, вернуть остаток"),
        ("r", "API портала", "Браузер", "биты вернулись на баланс"),
        ("end",),
        ("sep", "Выдача"),
        ("m", "Администратор", "API портала", "PATCH /shop/orders/{id}: ready"),
        ("m", "API портала", "БД", "статус ready, кто обработал"),
        ("m", "Администратор", "API портала", "PATCH /shop/orders/{id}: issued"),
        ("alt", "[заказ уже закрыт: выдан или отменён]"),
        ("r", "API портала", "Администратор", "400: заказ уже закрыт"),
        ("else", "[заказ открыт]"),
        ("m", "API портала", "БД", "статус issued"),
        ("end",),
    ]))
    out.append(sequence_page("Последовательность: запись на мероприятие", "Последовательность: запись, присутствие и опрос",
                             ["Студент", "Организатор", "API портала", "БД"], [
        ("m", "Студент", "API портала", "POST /events/{id}/register (участник или волонтёр)"),
        ("alt", "[мероприятие началось, запись закрыта или студента убрали из списка]"),
        ("r", "API портала", "Студент", "400 или 403 с причиной"),
        ("else", "[можно записаться]"),
        ("s", "API портала", "проверяет лимит мест нужной роли"),
        ("alt", "[мест нет]"),
        ("r", "API портала", "Студент", "409: лимит исчерпан"),
        ("else", "[место есть]"),
        ("m", "API портала", "БД", "INSERT запись (source = self)"),
        ("r", "API портала", "Студент", "запись подтверждена"),
        ("end",),
        ("end",),
        ("sep", "После мероприятия"),
        ("m", "Организатор", "API портала", "PUT /events/{id}/attendance (кто пришёл)"),
        ("m", "API портала", "БД", "attended = true или false"),
        ("s", "API портала", "биты и сводка ПГАС считаются по отметкам"),
        ("m", "Студент", "API портала", "POST /events/{id}/feedback (оценка 1–5, текст)"),
        ("alt", "[не участвовал, мероприятие не закончилось или прошло больше 30 дней]"),
        ("r", "API портала", "Студент", "400: оценить нельзя"),
        ("else", "[можно оценить]"),
        ("m", "API портала", "БД", "сохранить или обновить отзыв"),
        ("r", "API портала", "Студент", "спасибо"),
        ("end",),
        ("m", "Организатор", "API портала", "GET /events/{id}"),
        ("r", "API портала", "Организатор", "отзывы без имён"),
    ]))
    return out


# ---- Pages list -------------------------------------------------------------------------------------------

def usecase_pages():
    out = []
    out.append(usecase_page("Use case: гость и студент", "Варианты использования: гость и студент",
                            [("guest", "Гость", None), ("student", "Студент", "guest")], [
        ("guest", [("g1", "Смотреть расписание группы, преподавателя, аудитории"), ("g2", "Смотреть карту корпуса и аудитории"),
                   ("g3", "Читать FAQ и объявления"), ("g4", "Смотреть преподавателей"), ("g5", "Спросить помощника ВИТШика"),
                   ("g6", "Читать политику персональных данных"), ("g7", "Войти через ЭИОС"), ("g8", "Подтянуть курсы СДО")]),
        ("student", [("s1", "Смотреть общий календарь"), ("s2", "Открыть курс СДО из пары"), ("s3", "Видеть «Сегодня» и «Мои задачи»"),
                     ("s4", "Вести домашние задания группы"), ("s5", "Получить объяснительную или заявление на пересдачу"),
                     ("s6", "Указать ВК, Max и группу в профиле"), ("s7", "Задать вопрос на форуме"),
                     ("s8", "Ответить и проголосовать на форуме"), ("s9", "Отметить решение (автор вопроса)"), ("s10", "Выйти из портала")]),
    ], externals=[("eios", "ЭИОС КГУ", "g7"), ("sdo", "СДО (Moodle)", "g8")],
        rels=[("g7", "g8", "«include»"), ("s2", "s1", "«extend»")]))
    out.append(usecase_page("Use case: объединения и задачи", "Варианты использования: объединения и задачи",
                            [("student", "Студент", None), ("member", "Участник объединения", "student"),
                             ("leader", "Руководитель объединения", "member")], [
        ("student", [("a1", "Смотреть каталог объединений и контакты руководителей"), ("a2", "Подать заявку, отозвать её, выйти"),
                     ("a3", "Вести личные задачи с цветом и сроком")]),
        ("member", [("m1", "Видеть доску задач и двигать свои карточки"), ("m2", "Комментировать задачу"),
                    ("m3", "Прикладывать к задаче файл или ссылку"), ("m4", "Читать объявления объединения"),
                    ("m5", "Видеть собрания объединения в календаре")]),
        ("leader", [("l1", "Одобрить или отклонить заявку"), ("l2", "Исключить участника и вернуть его"),
                    ("l3", "Видеть контакты участников"), ("l4", "Править описание и контакты объединения"),
                    ("l5", "Поставить задачу всем или выбранным"), ("l6", "Принять работу или вернуть на доработку"),
                    ("l7", "Архивировать завершённые задачи"), ("l8", "Опубликовать объявление с файлами"),
                    ("l9", "Назначить собрание"), ("l10", "Записать итоги и отметить присутствующих")]),
    ], rels=[("l10", "l9", "«extend»")]))
    out.append(usecase_page("Use case: мероприятия, ПГАС, бронь", "Варианты использования: мероприятия, ПГАС и бронь",
                            [("student", "Студент", None), ("leader", "Руководитель объединения", "student"),
                             ("admin", "Администратор", "leader")], [
        ("student", [("e1", "Смотреть мероприятия объединений и института"), ("e2", "Записаться участником или волонтёром, отменить запись"),
                     ("e3", "Оставить отзыв после мероприятия"), ("e6", "Скачать документы мероприятия"),
                     ("e4", "Смотреть сводку ПГАС за семестр"), ("e7", "Выгрузить сводку в Excel и Word"),
                     ("e5", "Добавить мероприятие вручную со сканом")]),
        ("leader", [("o1", "Создать мероприятие объединения"), ("o2", "Записать людей пофамильно, убрать из списка"),
                    ("o3", "Отметить присутствие"), ("o4", "Выгрузить список участников в Excel"),
                    ("o5", "Прикрепить PDF-документы к мероприятию"), ("o6", "Забронировать часть помещения 108"),
                    ("o7", "Забронировать ноутбуки (до 5)"), ("o8", "Отменить свою бронь")]),
        ("admin", [("x1", "Создать мероприятие института"), ("x2", "Записать на мероприятие целую группу"),
                   ("x3", "Отменить любую бронь с причиной"), ("x4", "Выгрузить участие всех студентов"),
                   ("x5", "Бронировать без лимитов руководителя")]),
    ], rels=[("e7", "e4", "«extend»")]))
    out.append(usecase_page("Use case: биты, трайбы, магазин", "Варианты использования: биты, трайбы и магазин",
                            [("student", "Студент", None), ("admin", "Администратор", "student")], [
        ("student", [("b1", "Видеть биты, уровень и значки"), ("b2", "Видеть свой трайб и таблицу мест"),
                     ("b3", "Купить товар за биты"), ("b4", "Отменить заказ, пока он «Оформлен»"),
                     ("b5", "Смотреть историю своих заказов")]),
        ("admin", [("c1", "Создать и запустить турнир"), ("c2", "Начислить трайбу очки или штраф"),
                   ("c3", "Перевести студента в другой трайб"), ("c4", "Завершить турнир и выдать призы"),
                   ("c5", "Добавлять и менять товары, остатки, фото"), ("c6", "Менять статус заказов и писать комментарий"),
                   ("c7", "Начислить или списать биты вручную")]),
    ], rels=[("b4", "b3", "«extend»")]))
    out.append(usecase_page("Use case: администрирование", "Варианты использования: модерация и администрирование",
                            [("mod", "Модератор", None), ("admin", "Администратор", "mod"), ("main", "Главный администратор", "admin")], [
        ("mod", [("d1", "Закрепить вопрос на форуме"), ("d2", "Удалить чужой вопрос или ответ"),
                 ("d3", "Отметить решение в любом вопросе")]),
        ("admin", [("f1", "Смотреть список пользователей"), ("f2", "Заблокировать пользователя"), ("f3", "Назначить модератора"),
                   ("f4", "Создать объединение и назначить руководителя"),
                   ("f5", "Править FAQ, объявления, преподавателей, дисциплины"), ("f6", "Удалить пользователя")]),
        ("main", [("h1", "Выдать и снять права администратора"), ("h2", "Войти как локальный администратор из .env")]),
    ]))
    return out


def all_pages():
    return usecase_pages() + state_pages() + swimlane_pages() + sequence_pages()


# ---- Optional PNG preview ---------------------------------------------------------------------------------

def preview(pages, outdir):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)

    def wrap(text, width):
        lines = []
        for para in text.split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = (cur + " " + word).strip()
                if font.getlength(trial) <= width or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = word
            lines.append(cur)
        return lines

    for n, p in enumerate(pages):
        W = int(max(s["x"] + s["w"] for s in p.shapes.values())) + 60
        H = int(max(s["y"] + s["h"] for s in p.shapes.values())) + 80
        im = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(im)
        for s in p.shapes.values():
            x, y, w, h, k = s["x"], s["y"], s["w"], s["h"], s["kind"]
            fill, stroke = COLORS.get(s["color"], COLORS["white"])
            if k == "text":
                for i, ln in enumerate(wrap(s["text"], w)):
                    tw = font.getlength(ln)
                    tx = x + (w - tw) / 2 if s["align"] == "center" else (x + w - tw if s["align"] == "right" else x)
                    d.text((tx, y + i * 15), ln, fill=s["tcolor"], font=bold if s["bold"] else font)
                continue
            if k in ("start", "end"):
                d.ellipse([x, y, x + w, y + h], fill="#1b2330")
                continue
            if k == "actor":
                cxm = x + w / 2
                d.ellipse([cxm - 8, y, cxm + 8, y + 16], outline="#374151", width=2)
                d.line([cxm, y + 16, cxm, y + 38], fill="#374151", width=2)
                d.line([x, y + 24, x + w, y + 24], fill="#374151", width=2)
                d.line([cxm, y + 38, x, y + h], fill="#374151", width=2)
                d.line([cxm, y + 38, x + w, y + h], fill="#374151", width=2)
                continue
            if k == "diamond":
                d.polygon([(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)], fill=fill, outline=stroke)
            elif k == "ellipse":
                d.ellipse([x, y, x + w, y + h], fill=fill, outline=stroke)
            elif k in ("round", "state"):
                d.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=fill, outline=stroke)
            elif k == "lane":
                d.rectangle([x, y, x + w, y + h], fill=s["lane_fill"], outline=stroke)
                d.rectangle([x, y, x + 44, y + h], fill=fill, outline=stroke)
                d.text((x + 6, y + h / 2 - 6), s["text"][:8], fill=INK, font=bold)
                continue
            elif k == "frame":
                d.rectangle([x, y, x + w, y + h], outline=stroke, fill=None)
                d.text((x + 8, y + 4), s["text"], fill=INK, font=bold)
                continue
            else:
                d.rectangle([x, y, x + w, y + h], fill=fill, outline=stroke)
            lines = wrap(s["text"], w - 14)
            ty = y + (h - len(lines) * 15) / 2
            for i, ln in enumerate(lines):
                d.text((x + (w - font.getlength(ln)) / 2, ty + i * 15), ln, fill=INK, font=font)
        for e in p.edges:
            pts = p.edge_points(e)
            d.line(pts, fill="#c0392b" if e["dashed"] else "#374151", width=2)
            (x0, y0), (x1, y1) = pts[-2], pts[-1]
            ang = math.atan2(y1 - y0, x1 - x0)
            if e["end"] != "none":
                d.polygon([(x1, y1), (x1 - 11 * math.cos(ang - 0.4), y1 - 11 * math.sin(ang - 0.4)),
                           (x1 - 11 * math.cos(ang + 0.4), y1 - 11 * math.sin(ang + 0.4))], fill=None if e["end"] == "tri" else "#374151", outline="#374151")
            if e["label"]:
                # label near the middle of the longest segment
                best = max(range(len(pts) - 1), key=lambda i: abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1]))
                (ax, ay), (bx, by) = pts[best], pts[best + 1]
                t = 0.5 + e["lpos"] / 2 if len(pts) == 2 else 0.5
                lx, ly = ax + (bx - ax) * t, ay + (by - ay) * t
                tw = font.getlength(e["label"])
                d.rectangle([lx - tw / 2 - 2, ly - 8, lx + tw / 2 + 2, ly + 8], fill="white")
                d.text((lx - tw / 2, ly - 7), e["label"], fill=MUTED, font=font)
        im.save(f"{outdir}/{n + 1:02d}.png")


def main():
    pages = all_pages()
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write(to_xml(pages))
    if len(sys.argv) > 2:
        preview(pages, sys.argv[2])
    print(len(pages), "pages")


if __name__ == "__main__":
    main()
