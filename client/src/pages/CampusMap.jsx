import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { MapPin, ExternalLink, Plus, Minus, RotateCcw, Search, X, Monitor, Laptop, Users, Cpu, Clock } from 'lucide-react';
import SectionIcon from '../components/SectionIcon';
import FloorPlan, { roomSubtitle, roomTitle } from '../components/FloorPlan';
import { FLOORS, FLOOR_PLANS, KIND_STYLE, floorOf, isPickable, roomShape, boundsOf, VIEW } from '../data/floorPlans';
import { roomsApi } from '../services/api';
import { mskNow, toMinutes } from '../utils/time';
import { openChat } from '../utils/chat';
import { plural } from '../utils/plural';

const ICON = { strokeWidth: 1.75 };
const ZOOMS = [1, 1.5, 2, 3];

// Ready-made filters
const PRESETS = [
  { key: 'computers', label: 'С компьютерами', test: (f) => f && f.pcs + f.laptops > 0 },
  { key: 'os:Linux', label: 'Linux', test: (f) => f?.os === 'Linux' && f.pcs + f.laptops > 0 },
  { key: 'os:Windows', label: 'Windows', test: (f) => f?.os === 'Windows' && f.pcs + f.laptops > 0 },
  { key: 'eq:проектор', label: 'Проектор', test: (f) => f?.equipment.includes('проектор') },
  { key: 'type:лекционная', label: 'Лекционные', test: (f) => f?.type === 'лекционная' },
  { key: 'coworking', label: 'Коворкинги', test: (f, room) => room.kind === 'коворкинг' },
];

const DIRECTION = 'Дирекция ИВИТШ. Работает с понедельника по пятницу с 9:00 до 17:00, перерыв с 12:00 до 13:00.';

// The filter described by the address: ?os=Linux, ?eq=проектор, ?type=лекционная, ?filter=computers
const filterFromParams = (params) => {
  for (const name of ['os', 'eq', 'type']) {
    const value = params.get(name);
    if (value) {
      const preset = PRESETS.find((p) => p.key === `${name}:${value}`);
      return { key: `${name}:${value}`, label: preset?.label || value };
    }
  }
  const preset = PRESETS.find((p) => p.key === params.get('filter'));
  return preset ? { key: preset.key, label: preset.label } : null;
};

const testOf = (filter) => {
  if (!filter) return null;
  const preset = PRESETS.find((p) => p.key === filter.key);
  if (preset) return preset.test;
  const [kind, value] = [filter.key.slice(0, filter.key.indexOf(':')), filter.key.slice(filter.key.indexOf(':') + 1)];
  if (kind === 'os') return (f) => f?.os === value && f.pcs + f.laptops > 0;
  if (kind === 'eq') return (f) => !!f?.equipment.includes(value);
  if (kind === 'type') return (f) => f?.type === value;
  return null;
};

const paramsOfFilter = (filter) => {
  if (!filter) return {};
  const at = filter.key.indexOf(':');
  if (at < 0) return { filter: filter.key };
  return { [filter.key.slice(0, at)]: filter.key.slice(at + 1) };
};

// What was typed: a room, a place or an OS
const resolve = (raw) => {
  const text = raw.trim();
  const low = text.toLowerCase().replace(/ё/g, 'е');
  if (!text) return { error: 'Введите номер аудитории, например 305.' };
  if (/улей|улья/.test(low)) return { room: 'ит-улей' };
  if (/коворк|ковер|64\s*бит/.test(low)) return { room: 'коворкинг' };
  if (/8\s*бит|игров/.test(low)) return { room: '108' };
  if (/дирекц|деканат/.test(low)) return { room: '209' };
  const m = low.match(/(\d)(\d{2})/);
  if (m) {
    const letter = text.match(/([А-ЯЁA-Z])\s*-?\s*\d/i)?.[1]?.toUpperCase();
    if (letter && letter !== 'Б') return { error: `Схемы есть только для корпуса Б, а ${text} — в другом корпусе.` };
    const id = m[1] + m[2];
    if (roomShape(id) && isPickable(roomShape(id))) return { room: id };
    if (FLOORS.includes(Number(m[1]))) return { error: `Аудитории Б-${id} нет на схеме ${m[1]} этажа. Номера на этаже видны на схеме ниже.`, floor: Number(m[1]) };
    return { error: 'В корпусе Б аудитории с 101 по 409 — проверьте номер.' };
  }
  if (/линукс|linux|убунт/.test(low)) return { filter: { key: 'os:Linux', label: 'Linux' } };
  if (/виндо|windows|винд/.test(low)) return { filter: { key: 'os:Windows', label: 'Windows' } };
  return { error: `Не нашёл «${text}». Введите номер аудитории, например 305, или «Linux», «коворкинг».` };
};

// Now / next pair in a room from today's lessons, by Moscow time
const statusOf = (today) => {
  if (!today) return null;
  const now = mskNow();
  if (today.date !== now.date) return null;
  const lessons = today.lessons;
  const current = lessons.find((l) => toMinutes(l.start) <= now.minutes && now.minutes < toMinutes(l.end));
  if (current) return { busy: true, text: `Сейчас занята: ${current.discipline} (${current.kind}) до ${current.end}` };
  const next = lessons.find((l) => toMinutes(l.start) > now.minutes);
  if (next) return { busy: false, text: `Сейчас свободна, следующая пара в ${next.start}` };
  return { busy: false, text: lessons.length ? 'Сейчас свободна, на сегодня пар больше нет' : 'Сегодня пар по расписанию нет' };
};

const RoomToday = ({ number }) => {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    let alive = true;
    setState({ loading: true });
    roomsApi.getToday(number)
      .then((data) => alive && setState({ data }))
      .catch(() => alive && setState({ error: true }));
    return () => { alive = false; };
  }, [number]);

  if (state.loading) return <p className="room-today room-today-muted"><Clock size={16} {...ICON} aria-hidden="true" /> Смотрю расписание ЭИОС…</p>;
  if (state.error) return <p className="room-today room-today-muted"><Clock size={16} {...ICON} aria-hidden="true" /> Расписание ЭИОС сейчас недоступно.</p>;
  const status = statusOf(state.data);
  const now = mskNow().minutes;
  return (
    <div className="room-today-block">
      {status && (
        <p className={`room-today ${status.busy ? 'is-busy' : 'is-free'}`} role="status">
          <span className="room-today-dot" aria-hidden="true" />
          {status.text}
        </p>
      )}
      {state.data.lessons.length > 0 && (
        <ul className="room-lessons" aria-label="Пары сегодня">
          {state.data.lessons.map((l) => {
            const past = toMinutes(l.end) <= now;
            const live = toMinutes(l.start) <= now && now < toMinutes(l.end);
            return (
              <li key={`${l.start}-${l.discipline}-${l.groups.join()}`} className={`${past ? 'is-past' : ''} ${live ? 'is-live' : ''}`}>
                <span className="room-lesson-time tabular">{l.start}–{l.end}</span>
                <span className="room-lesson-what">
                  {l.discipline}, {l.kind}
                  {l.groups.length > 0 && <span className="room-lesson-groups"> · {l.groups.join(', ')}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

const RoomCard = ({ id, facts, spaces, onClose }) => {
  const shape = roomShape(id);
  const fact = facts?.[id];
  const space = spaces?.find((s) => s.room === id);
  const kind = fact?.type || shape?.kind;
  const tone = (KIND_STYLE[kind] || KIND_STYLE.office).tone;
  const floor = floorOf(id);
  const numbered = /^\d{3}$/.test(id);
  const equipment = fact?.equipment || space?.equipment || [];

  return (
    <section className="room-card" aria-labelledby="room-card-title">
      <header className="room-card-head">
        <div>
          <h3 id="room-card-title" className="room-card-title">
            {space && numbered ? `Б-${id} · ${space.name}` : space?.type === 'коворкинг' ? `Коворкинг «${space.name}»` : space ? space.name : roomTitle(shape)}
          </h3>
          <p className="room-card-kind">
            <span className={`room-kind-dot tone-${tone}`} aria-hidden="true" />
            {(space?.type || KIND_STYLE[kind]?.label || 'аудитория').replace(/^./, (c) => c.toUpperCase())} · {floor} этаж
          </p>
        </div>
        <button type="button" className="btn btn-ghost btn-icon room-card-close" onClick={onClose} aria-label="Закрыть карточку аудитории" title="Закрыть">
          <X size={18} {...ICON} />
        </button>
      </header>

      {id === '209' && <p className="room-card-note">{DIRECTION}</p>}

      {(fact || space) && (
        <dl className="room-stats">
          <div><dt><Users size={16} {...ICON} aria-hidden="true" /> Мест</dt><dd className="tabular">{(fact || space).seats}</dd></div>
          {fact && <div><dt><Monitor size={16} {...ICON} aria-hidden="true" /> ПК</dt><dd className="tabular">{fact.pcs || '—'}</dd></div>}
          {fact && <div><dt><Laptop size={16} {...ICON} aria-hidden="true" /> Ноутбуки</dt><dd className="tabular">{fact.laptops || '—'}</dd></div>}
          {fact && <div><dt><Cpu size={16} {...ICON} aria-hidden="true" /> ОС</dt><dd>{fact.os || '—'}</dd></div>}
        </dl>
      )}
      {fact && !fact.pcs && !fact.laptops && (
        <p className="room-card-note">
          Компьютеров для студентов нет{fact.teacher_pc ? `, есть ПК преподавателя на ${fact.os}` : ''}.
        </p>
      )}

      {numbered && fact && <RoomToday number={id} />}

      {equipment.length > 0 && (
        <div className="room-card-group">
          <h4>Оборудование</h4>
          <ul className="room-tags">
            {equipment.map((e) => <li key={e}>{e}</li>)}
          </ul>
        </div>
      )}

      {!fact && !space && id !== '209' && (
        <p className="room-card-note">О технике в этой аудитории в базе портала пока ничего нет.</p>
      )}
    </section>
  );
};

const CampusMap = () => {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [base, setBase] = useState(null);
  const [floor, setFloor] = useState(1);
  const [query, setQuery] = useState('');
  const [message, setMessage] = useState(null);
  const [zoom, setZoom] = useState(1);
  const tabRefs = useRef({});
  const scrollRef = useRef(null);
  const drag = useRef(null);

  useEffect(() => {
    let alive = true;
    roomsApi.getRooms().then((data) => alive && setBase(data)).catch(() => alive && setBase({ rooms: [], spaces: [], failed: true }));
    return () => { alive = false; };
  }, []);

  const facts = useMemo(() => Object.fromEntries((base?.rooms || []).map((r) => [r.number, r])), [base]);
  // The address is the state: /map?room=Б-301, /map?os=Linux — links from the chat and the schedule land here
  const rawRoom = searchParams.get('room') || '';
  const selected = useMemo(() => {
    if (!rawRoom) return null;
    const found = resolve(rawRoom);
    return found.room || null;
  }, [rawRoom]);
  const filter = useMemo(() => filterFromParams(searchParams), [searchParams]);

  const update = useCallback((next) => setSearchParams(next, { replace: true }), [setSearchParams]);
  const select = useCallback((id) => update({ ...paramsOfFilter(filter), ...(id ? { room: /^\d{3}$/.test(id) ? `Б-${id}` : id } : {}) }), [filter, update]);
  const applyFilter = useCallback((next) => update({ ...paramsOfFilter(next), ...(selected ? { room: rawRoom } : {}) }), [update, selected, rawRoom]);

  // A room in the address opens its floor; a bad one says so
  useEffect(() => {
    if (!rawRoom) return;
    const found = resolve(rawRoom);
    if (found.room) {
      setFloor(floorOf(found.room));
      setQuery(rawRoom);
      setMessage(null);
    } else {
      if (found.floor) setFloor(found.floor);
      setMessage({ error: found.error });
    }
  }, [rawRoom]);

  useEffect(() => {
    if (location.state?.selectedFloor) setFloor(Number(location.state.selectedFloor));
  }, [location.state]);

  const test = testOf(filter);
  const matchesOn = useCallback((f) => {
    if (!test) return null;
    return new Set(FLOOR_PLANS[f].rooms.filter((r) => isPickable(r) && test(facts[r.id], r)).map((r) => r.id));
  }, [test, facts]);
  const matches = matchesOn(floor);
  const counts = useMemo(() => (test ? Object.fromEntries(FLOORS.map((f) => [f, matchesOn(f).size])) : null), [test, matchesOn]);

  // A filter with nothing on this floor moves to the first floor that has something
  useEffect(() => {
    if (!counts || selected || counts[floor]) return;
    const first = FLOORS.find((f) => counts[f]);
    if (first) setFloor(first);
  }, [counts]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the picked room in sight when the plan is wider than the screen
  useEffect(() => {
    const box = scrollRef.current;
    const shape = selected && roomShape(selected);
    if (!box || !shape || floorOf(selected) !== floor || box.scrollWidth <= box.clientWidth) return;
    const b = boundsOf(shape);
    const x = (((b.x0 + b.x1) / 2 - VIEW.x) / VIEW.width) * box.scrollWidth - box.clientWidth / 2;
    box.scrollTo({ left: Math.max(0, x), behavior: 'smooth' });
  }, [selected, floor, zoom]);

  const zoomTo = (next) => {
    const box = scrollRef.current;
    const center = box ? (box.scrollLeft + box.clientWidth / 2) / box.scrollWidth : 0.5;
    const middle = box ? (box.scrollTop + box.clientHeight / 2) / box.scrollHeight : 0.5;
    setZoom(next);
    requestAnimationFrame(() => {
      if (!box) return;
      box.scrollLeft = center * box.scrollWidth - box.clientWidth / 2;
      box.scrollTop = middle * box.scrollHeight - box.clientHeight / 2;
    });
  };

  // Mouse drag pans a zoomed plan; touch scrolls natively. A drag is never a click on a room.
  const onPointerDown = (e) => {
    const box = scrollRef.current;
    if (e.pointerType !== 'mouse' || e.button !== 0 || !box || box.scrollWidth <= box.clientWidth) return;
    drag.current = { x: e.clientX, y: e.clientY, left: box.scrollLeft, top: box.scrollTop, moved: false };
  };
  const onPointerMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 5) return;
    d.moved = true;
    scrollRef.current.scrollLeft = d.left - dx;
    scrollRef.current.scrollTop = d.top - dy;
    scrollRef.current.classList.add('is-dragging');
  };
  const onPointerUp = () => {
    scrollRef.current?.classList.remove('is-dragging');
    setTimeout(() => { drag.current = null; }, 0);
  };
  const pickRoom = (id) => {
    if (drag.current?.moved) return;
    select(id === selected ? null : id);
    if (id !== selected) revealCard.current = true;
  };

  // On a phone the card is below the plan: bring it into view after a tap on a room
  const revealCard = useRef(false);
  const cardRef = useRef(null);
  useEffect(() => {
    if (!revealCard.current || !selected) return;
    revealCard.current = false;
    if (window.matchMedia('(max-width: 900px)').matches) cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [selected]);

  const onSubmit = (e) => {
    e.preventDefault();
    const found = resolve(query);
    if (found.room) {
      setMessage(null);
      select(found.room);
      setFloor(floorOf(found.room));
    } else if (found.filter) {
      setMessage(null);
      update(paramsOfFilter(found.filter));
    } else {
      if (found.floor) setFloor(found.floor);
      setMessage({ error: found.error });
    }
  };

  const onTabKeyDown = (e) => {
    const i = FLOORS.indexOf(floor);
    const next = { ArrowRight: FLOORS[(i + 1) % FLOORS.length], ArrowLeft: FLOORS[(i - 1 + FLOORS.length) % FLOORS.length], Home: FLOORS[0], End: FLOORS[FLOORS.length - 1] }[e.key];
    if (!next) return;
    e.preventDefault();
    setFloor(next);
    tabRefs.current[next]?.focus();
  };

  const floorRooms = FLOOR_PLANS[floor].rooms.filter(isPickable).sort((a, b) => a.id.localeCompare(b.id, 'ru', { numeric: true }));
  const shownRooms = matches ? [...floorRooms.filter((r) => matches.has(r.id)), ...floorRooms.filter((r) => !matches.has(r.id))] : floorRooms;
  const total = counts ? FLOORS.reduce((sum, f) => sum + counts[f], 0) : 0;
  const selectedHere = selected && floorOf(selected) === floor ? selected : null;

  return (
    <div className="container cm-page">
      <header className="page-header">
        <div className="page-heading">
          <SectionIcon section="map" size="lg" />
          <div>
            <h1>Карта кампуса</h1>
            <p className="page-subtitle">Корпус Б ИВИТШ КГУ: схемы этажей, компьютеры и техника в аудиториях.</p>
          </div>
        </div>
      </header>

      <a href="https://yandex.ru/maps/?text=Кострома,+ул.+Ивановская,+24а" target="_blank" rel="noopener noreferrer" className="map-route">
        <span className="tile hue-green" aria-hidden="true"><MapPin size={20} {...ICON} /></span>
        <span className="map-route-text">
          <span className="map-route-title">Как добраться до корпуса ИВИТШ</span>
          <span className="map-route-address">г. Кострома, ул. Ивановская, 24а (корпус Б ИВИТШ КГУ)</span>
        </span>
        <span className="map-route-action">
          <span className="map-route-action-label">Открыть в Яндекс Картах</span>
          <ExternalLink size={16} {...ICON} aria-hidden="true" />
          <span className="visually-hidden">(откроется в новой вкладке)</span>
        </span>
      </a>

      <section className="card map-panel" aria-labelledby="map-plans-heading">
        <div className="map-panel-head">
          <div>
            <h2 id="map-plans-heading">Схемы этажей корпуса Б</h2>
            <p className="map-panel-hint">Нажмите на аудиторию: покажу места, компьютеры, ОС, технику и свободна ли она сейчас.</p>
          </div>
          <div className="segmented map-floors" role="tablist" aria-label="Этаж">
            {FLOORS.map((f) => (
              <button
                key={f}
                ref={(el) => { tabRefs.current[f] = el; }}
                type="button"
                role="tab"
                id={`floor-tab-${f}`}
                className="segmented-item tabular"
                aria-selected={floor === f}
                aria-controls="floor-panel"
                tabIndex={floor === f ? 0 : -1}
                onClick={() => setFloor(f)}
                onKeyDown={onTabKeyDown}
              >
                {f} этаж
                {counts && <span className={`map-floor-count ${counts[f] ? '' : 'is-zero'}`} aria-label={`, подходит: ${counts[f]}`}>{counts[f]}</span>}
              </button>
            ))}
          </div>
        </div>

        <form className="map-finder" onSubmit={onSubmit} role="search" aria-label="Найти аудиторию">
          <label className="field-label" htmlFor="room-search">Найти аудиторию</label>
          <div className="map-finder-row">
            <div className="cm-search">
              <Search size={18} {...ICON} className="cm-search-icon" aria-hidden="true" />
              <input
                id="room-search"
                className="input"
                autoComplete="off"
                placeholder="Например, Б-305, коворкинг или Linux"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-describedby="room-result"
              />
            </div>
            <button type="submit" className="btn btn-primary">Показать</button>
          </div>
          <p id="room-result" className={`map-finder-result ${message?.error ? 'is-error' : ''}`} role="status">
            {message?.error}
          </p>
        </form>

        <div className="map-filters" role="group" aria-label="Подсветить аудитории">
          {PRESETS.map((p) => (
            <button
              key={p.key}
              type="button"
              className="chip"
              aria-pressed={filter?.key === p.key}
              onClick={() => applyFilter(filter?.key === p.key ? null : { key: p.key, label: p.label })}
            >
              {p.label}
            </button>
          ))}
          {filter && !PRESETS.some((p) => p.key === filter.key) && (
            <button type="button" className="chip" aria-pressed="true" onClick={() => applyFilter(null)}>
              {filter.label}
              <X size={14} {...ICON} aria-hidden="true" />
              <span className="visually-hidden">— снять подсветку</span>
            </button>
          )}
        </div>
        {filter && (
          <p className="map-filter-summary" role="status">
            {total
              ? <>«{filter.label}» — {total} {plural(total, ['аудитория', 'аудитории', 'аудиторий'])}: {FLOORS.filter((f) => counts[f]).map((f) => `${f} этаж — ${counts[f]}`).join(', ')}.</>
              : <>«{filter.label}» нет ни в одной аудитории.</>}
            {' '}
            <button type="button" className="map-link-button" onClick={() => applyFilter(null)}>Снять подсветку</button>
          </p>
        )}
        {base?.failed && <p className="map-filter-summary is-error">Не удалось загрузить сведения об аудиториях — схема работает, но без техники.</p>}

        <div id="floor-panel" role="tabpanel" aria-labelledby={`floor-tab-${floor}`} className="map-floor">
          <div className="map-stage">
            <div
              ref={scrollRef}
              className="map-scroll"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={onPointerUp}
              onPointerCancel={onPointerUp}
            >
              <div className="map-canvas" style={{ '--zoom': zoom }}>
                <FloorPlan floor={floor} facts={facts} selected={selectedHere} matches={matches} onSelect={pickRoom} />
              </div>
            </div>
            <div className="map-zoom" role="group" aria-label="Масштаб схемы">
              <button type="button" className="map-zoom-btn" onClick={() => zoomTo(ZOOMS[Math.max(0, ZOOMS.indexOf(zoom) - 1)])} disabled={zoom === ZOOMS[0]} aria-label="Отдалить" title="Отдалить">
                <Minus size={18} {...ICON} />
              </button>
              <span className="map-zoom-level tabular" aria-live="polite">{Math.round(zoom * 100)}%</span>
              <button type="button" className="map-zoom-btn" onClick={() => zoomTo(ZOOMS[Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom) + 1)])} disabled={zoom === ZOOMS[ZOOMS.length - 1]} aria-label="Приблизить" title="Приблизить">
                <Plus size={18} {...ICON} />
              </button>
              <button type="button" className="map-zoom-btn" onClick={() => zoomTo(1)} disabled={zoom === 1} aria-label="Сбросить масштаб" title="Сбросить масштаб">
                <RotateCcw size={18} {...ICON} />
              </button>
            </div>
          </div>

          <ul className="map-legend" aria-label="Цвета аудиторий">
            {['компьютерный класс', 'мультимедийный класс', 'лекционная', 'лаборатория', 'учебная', 'коворкинг', 'дирекция', 'office'].map((k) => (
              <li key={k}><span className={`room-kind-dot tone-${KIND_STYLE[k].tone}`} aria-hidden="true" />{KIND_STYLE[k].label}</li>
            ))}
          </ul>

          <div className="map-details" ref={cardRef}>
            {selectedHere ? (
              <RoomCard
                id={selectedHere}
                facts={facts}
                spaces={base?.spaces}
                onClose={() => select(null)}
              />
            ) : (
              <div className="map-howto">
                <h3>Как найти аудиторию</h3>
                <p>
                  Все аудитории <span className="tabular">101–409</span> — в корпусе Б (ул. Ивановская, 24а). Первая цифра номера — этаж:
                  {' '}<span className="tabular">200</span>-е на 2 этаже (там же дирекция Б-209), <span className="tabular">400</span>-е и коворкинг — на 4.
                </p>
                <p>Выберите аудиторию на схеме или в списке, чтобы увидеть компьютеры, технику и пары на сегодня.</p>
              </div>
            )}

            <div className="map-room-list">
              <h3>Аудитории {floor} этажа</h3>
              <ul>
                {shownRooms.map((room) => {
                  const fact = facts[room.id];
                  const space = base?.spaces?.find((sp) => sp.room === room.id);
                  const kind = fact?.type || room.kind;
                  const dim = matches && !matches.has(room.id);
                  const meta = fact
                    ? [`${fact.seats} ${plural(fact.seats, ['место', 'места', 'мест'])}`, fact.pcs || fact.laptops ? roomSubtitle(fact) : '', fact.pcs || fact.laptops ? fact.os : ''].filter(Boolean).join(' · ')
                    : space ? `${space.seats} ${plural(space.seats, ['место', 'места', 'мест'])}`
                      : room.id === '209' ? 'пн–пт, 9:00–17:00' : KIND_STYLE[kind]?.label;
                  return (
                    <li key={room.id}>
                      <button
                        type="button"
                        className={`map-room-row ${dim ? 'is-dim' : ''}`}
                        aria-pressed={room.id === selected}
                        onClick={() => { select(room.id === selected ? null : room.id); if (room.id !== selected) revealCard.current = true; }}
                      >
                        <span className={`room-kind-dot tone-${(KIND_STYLE[kind] || KIND_STYLE.office).tone}`} aria-hidden="true" />
                        <span className="map-room-name">{roomTitle(room)}{room.note ? ` · ${room.note}` : ''}</span>
                        <span className="map-room-meta">{meta}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              <p className="map-room-list-more">
                Про технику знает и ВИТШик: «сколько компов в 301?», «где Linux?».{' '}
                <button type="button" className="map-link-button" onClick={openChat}>Спросить ВИТШика</button>
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default CampusMap;
