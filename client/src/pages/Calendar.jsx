import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ChevronLeft, ChevronRight, Plus, LogIn, MapPin, Clock, User, BookOpen, ExternalLink, Pencil, Trash2,
  AlertTriangle, CalendarSearch, NotebookPen, SquareKanban, Handshake, CheckCircle2,
} from 'lucide-react';
import SectionIcon from '../components/SectionIcon';
import Modal from '../components/Modal';
import MeetingDialog from '../components/MeetingDialog';
import MeetingForm from '../components/MeetingForm';
import HomeworkForm from '../components/HomeworkForm';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { associationsApi, calendarApi, homeworkApi } from '../services/api';
import {
  TYPES, addDays, dayKey, dayTitle, fitsSubgroup, hueOf, isDeadline, layoutDay, minutesOf, parseDay,
  rangeTitle, readSubgroup, saveSubgroup, timeLabel, weekStart,
} from '../utils/calendar';
import { dueInfo } from '../utils/tasks';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const WIDE_QUERY = '(min-width: 900px)';
const PX_PER_MIN = 0.9;
const TYPES_KEY = 'portal_cal_hidden';
const ROOM_ON_MAP = /^Б-?\d{3}/i;

const useWide = () => {
  const [wide, setWide] = useState(() => window.matchMedia(WIDE_QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(WIDE_QUERY);
    const onChange = () => setWide(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return wide;
};

// Hidden kinds are remembered (not shown ones), so a kind added later shows up by default
const readTypes = () => {
  try {
    const hidden = JSON.parse(localStorage.getItem(TYPES_KEY));
    if (Array.isArray(hidden)) return Object.keys(TYPES).filter(t => !hidden.includes(t));
  } catch { /* nothing saved */ }
  return Object.keys(TYPES);
};

const Place = ({ place, onNavigate }) => (ROOM_ON_MAP.test(place)
  ? <Link to={`/map?room=${encodeURIComponent(place)}`} onClick={onNavigate}>{place}</Link>
  : place);

const isDone = (item) => item.type === 'task' && (item.status === 'done' || item.status === 'review');

// One line under an entry's title: "лекция · Б-305" / "Робототехника · Б-108" / "до 18:00"
const subline = (item) => {
  if (item.type === 'lesson') return [item.kind, item.place].filter(Boolean).join(' · ');
  if (item.type === 'meeting') return [item.association?.name, item.place].filter(Boolean).join(' · ');
  if (item.type === 'event') return [item.status ? 'вы записаны' : '', item.place].filter(Boolean).join(' · ');
  if (item.type === 'task') return item.association ? item.association.name : 'Личная задача';
  return TYPES.homework.one;
};

// --- Week grid (computer) --------------------------------------------------------------------------

const Block = ({ entry, top, height, onOpen }) => {
  const { item, col, cols } = entry;
  const short = height < 44;
  const narrow = cols > 1;
  return (
    <button
      type="button"
      className={`cal-block hue-${hueOf(item)} ${item.replaced ? 'is-replaced' : ''} ${narrow ? 'is-narrow' : ''}`}
      title={narrow ? item.title : undefined}
      style={{ top, height, left: `calc(${(col / cols) * 100}% + 2px)`, width: `calc(${100 / cols}% - 4px)` }}
      onClick={() => onOpen(item)}
    >
      <span className="cal-block-time tabular">{timeLabel(item.starts_at)}{!short && !narrow && `–${timeLabel(item.ends_at)}`}</span>
      <span className="cal-block-title">{item.title}</span>
      {!short && <span className="cal-block-meta">{item.type === 'lesson' ? [item.place, item.replaced && 'замена'].filter(Boolean).join(' · ') : subline(item)}</span>}
      {item.subgroup > 0 && !short && <span className="cal-block-sub">п/г {item.subgroup}</span>}
    </button>
  );
};

const DeadlineChip = ({ item, onOpen }) => (
  <button type="button" className={`cal-deadline hue-${hueOf(item)} ${isDone(item) ? 'is-done' : ''}`} onClick={() => onOpen(item)}>
    <span className="tabular">{timeLabel(item.starts_at)}</span> {item.title}
  </button>
);

const WeekGrid = ({ days, items, onOpen }) => {
  const byDay = useMemo(() => {
    const map = Object.fromEntries(days.map(d => [dayKey(d), { timed: [], deadlines: [] }]));
    items.forEach((item) => {
      const slot = map[dayKey(new Date(item.starts_at))];
      if (slot) (isDeadline(item) ? slot.deadlines : slot.timed).push(item);
    });
    return map;
  }, [days, items]);

  const timed = items.filter(i => !isDeadline(i));
  const from = Math.min(8 * 60, ...timed.map(i => Math.floor(minutesOf(i.starts_at) / 60) * 60));
  const to = Math.max(18 * 60, ...timed.map(i => Math.ceil(Math.max(minutesOf(i.ends_at), minutesOf(i.starts_at) + 30) / 60) * 60));
  const hours = [];
  for (let m = from; m < to; m += 60) hours.push(m);
  const hasDeadlines = days.some(d => byDay[dayKey(d)].deadlines.length);

  const today = dayKey(new Date());
  const [nowMin, setNowMin] = useState(() => minutesOf(new Date().toISOString()));
  useEffect(() => {
    const timer = setInterval(() => setNowMin(minutesOf(new Date().toISOString())), 60000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="cal-week" style={{ '--cal-days': days.length }}>
      <div className="cal-week-head">
        <span />
        {days.map(d => (
          <span key={dayKey(d)} className={`cal-day-head ${dayKey(d) === today ? 'is-today' : ''}`}>
            <span className="cal-day-weekday">{d.toLocaleDateString('ru-RU', { weekday: 'short' })}</span>
            <span className="cal-day-date tabular">{d.getDate()}</span>
          </span>
        ))}
      </div>
      {hasDeadlines && (
        <div className="cal-week-deadlines">
          <span className="cal-gutter-label">Сроки</span>
          {days.map(d => (
            <div key={dayKey(d)} className="cal-deadline-cell">
              {byDay[dayKey(d)].deadlines.map(item => <DeadlineChip key={item.id} item={item} onOpen={onOpen} />)}
            </div>
          ))}
        </div>
      )}
      <div className="cal-week-body" style={{ height: (to - from) * PX_PER_MIN }}>
        <div className="cal-gutter">
          {hours.map(m => (
            <span key={m} className="cal-hour tabular" style={{ top: (m - from) * PX_PER_MIN }}>{`${m / 60}:00`}</span>
          ))}
        </div>
        {days.map((d) => {
          const key = dayKey(d);
          return (
            <div key={key} className={`cal-day-col ${key === today ? 'is-today' : ''}`}>
              {hours.map(m => <span key={m} className="cal-hour-line" style={{ top: (m - from) * PX_PER_MIN }} />)}
              {layoutDay(byDay[key].timed).map(entry => (
                <Block key={entry.item.id} entry={entry} onOpen={onOpen}
                  top={(entry.start - from) * PX_PER_MIN}
                  height={Math.max(22, (entry.end - entry.start) * PX_PER_MIN - 2)} />
              ))}
              {key === today && nowMin >= from && nowMin <= to && (
                <span className="cal-now" style={{ top: (nowMin - from) * PX_PER_MIN }} aria-hidden="true" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// --- Day list (phone) -------------------------------------------------------------------------------

const AgendaItem = ({ item, onOpen }) => {
  const deadline = isDeadline(item);
  const due = deadline && item.type === 'task' ? dueInfo(item.starts_at, item.status) : null;
  return (
    <li>
      <button type="button" className={`cal-agenda-item hue-${hueOf(item)} ${isDone(item) ? 'is-done' : ''}`} onClick={() => onOpen(item)}>
        <span className="cal-agenda-time tabular">
          {deadline ? <><span className="cal-agenda-until">до</span>{timeLabel(item.starts_at)}</> : <>{timeLabel(item.starts_at)}<span>{timeLabel(item.ends_at)}</span></>}
        </span>
        <span className="cal-agenda-text">
          <span className="cal-agenda-title">
            {item.title}
            {item.replaced && <span className="badge badge-warning">Замена</span>}
            {item.subgroup > 0 && <span className="badge">Подгруппа {item.subgroup}</span>}
            {isDone(item) && <CheckCircle2 size={16} className="cal-done-icon" {...ICON} />}
          </span>
          <span className="cal-agenda-meta">
            {deadline && <span className="cal-type">{TYPES[item.type].one}</span>}
            {subline(item) && !(deadline && item.type === 'homework') && <span>{subline(item)}</span>}
            {item.type === 'lesson' && item.teacher && <span>{item.teacher}</span>}
            {due?.tone === 'overdue' && <span className="task-due task-due-overdue">просрочено</span>}
          </span>
        </span>
      </button>
    </li>
  );
};

const DayList = ({ days, items, selected, onSelect, onOpen }) => {
  const counts = useMemo(() => {
    const map = {};
    items.forEach((i) => { const k = dayKey(new Date(i.starts_at)); map[k] = (map[k] || 0) + 1; });
    return map;
  }, [items]);
  const dayItems = items.filter(i => dayKey(new Date(i.starts_at)) === selected);
  const today = dayKey(new Date());
  return (
    <div className="cal-daylist">
      <div className="cal-strip" role="group" aria-label="День недели">
        {days.map((d) => {
          const key = dayKey(d);
          return (
            <button key={key} type="button" aria-pressed={key === selected}
              className={`cal-strip-day ${key === selected ? 'active' : ''} ${key === today ? 'is-today' : ''}`} onClick={() => onSelect(key)}>
              <span className="cal-day-weekday">{d.toLocaleDateString('ru-RU', { weekday: 'short' })}</span>
              <span className="cal-day-date tabular">{d.getDate()}</span>
              <span className={`cal-strip-dot ${counts[key] ? '' : 'is-empty'}`} aria-hidden="true" />
              <span className="visually-hidden">{counts[key] ? `, записей: ${counts[key]}` : ', пусто'}</span>
            </button>
          );
        })}
      </div>
      <h2 className="cal-daylist-title">{dayTitle(selected, { weekday: 'long' })}</h2>
      {dayItems.length ? (
        <ul className="list cal-agenda">
          {dayItems.map(item => <AgendaItem key={item.id} item={item} onOpen={onOpen} />)}
        </ul>
      ) : (
        <p className="cal-empty">Ничего не запланировано.</p>
      )}
    </div>
  );
};

// --- Details of a lesson or a homework entry ----------------------------------------------------------

const LessonDialog = ({ item, onClose, onHomework }) => (
  <Modal open={!!item} onClose={onClose} title={item?.title || ''} titleId="lesson-dialog-title" className="cal-dialog">
    {item && (
      <div className="cal-dialog-body">
        <ul className="cal-facts">
          <li><Clock size={16} {...ICON} />{dayTitle(dayKey(new Date(item.starts_at)), { weekday: 'long' })}, {timeLabel(item.starts_at)}–{timeLabel(item.ends_at)}</li>
          {item.place && <li><MapPin size={16} {...ICON} /><span>Аудитория <Place place={item.place} onNavigate={onClose} /></span></li>}
          {item.teacher && <li><User size={16} {...ICON} />{item.teacher}</li>}
        </ul>
        <p className="cal-badges">
          {item.kind && <span className="badge">{item.kind}</span>}
          {item.subgroup > 0 && <span className="badge">Подгруппа {item.subgroup}</span>}
          {item.replaced && <span className="badge badge-warning">Замена</span>}
        </p>
        <div className="cal-dialog-actions">
          {item.course ? (
            <a className="btn btn-primary btn-sm" href={item.course.url} target="_blank" rel="noopener noreferrer">
              <BookOpen size={16} {...ICON} />Курс в СДО<ExternalLink size={14} {...ICON} />
            </a>
          ) : null}
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => onHomework(item.title)}>
            <NotebookPen size={16} {...ICON} />Записать ДЗ
          </button>
        </div>
      </div>
    )}
  </Modal>
);

const HomeworkDialog = ({ entry, onClose, onEdit, onDelete }) => (
  <Modal open={!!entry} onClose={onClose} title={entry?.subject || 'Домашнее задание'} titleId="hw-dialog-title" className="cal-dialog">
    {entry && (
      <div className="cal-dialog-body">
        <ul className="cal-facts">
          {entry.due_at && <li><Clock size={16} {...ICON} />Сдать до: {dayTitle(dayKey(new Date(entry.due_at)), { weekday: 'long' })}, {timeLabel(entry.due_at)}</li>}
          {entry.author && <li><User size={16} {...ICON} />Записал(а): {entry.author}</li>}
        </ul>
        <p className="cal-text">{entry.text}</p>
        {entry.can_edit && (
          <div className="cal-dialog-actions">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onEdit(entry)}><Pencil size={16} {...ICON} />Изменить</button>
            <button type="button" className="btn btn-ghost btn-sm cal-danger" onClick={() => onDelete(entry)}><Trash2 size={16} {...ICON} />Удалить</button>
          </div>
        )}
      </div>
    )}
  </Modal>
);

// --- Group homework and SDO courses under the calendar -----------------------------------------------

const HomeworkList = ({ entries, group, onAdd, onOpen }) => (
  <section className="card cal-side-card hue-violet" aria-labelledby="hw-title">
    <div className="dash-card-head">
      <h2 id="hw-title">ДЗ группы {group}</h2>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => onAdd('')}><Plus size={16} {...ICON} />Добавить</button>
    </div>
    {entries.length === 0 ? (
      <p className="cal-empty">Пока пусто. Запишите задание — его увидит вся группа.</p>
    ) : (
      <ul className="list cal-hw-list">
        {entries.map((e) => {
          const due = dueInfo(e.due_at);
          return (
            <li key={e.id}>
              <button type="button" className="cal-hw-row" onClick={() => onOpen(e)}>
                <span className="cal-hw-subject">{e.subject || 'Заметка'}</span>
                <span className="cal-hw-text">{e.text}</span>
                {due && <span className={`task-due task-due-${due.tone || 'plain'}`}><Clock size={14} {...ICON} />{due.label}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    )}
  </section>
);

const CourseList = ({ courses }) => (
  <section className="card cal-side-card" aria-labelledby="courses-title">
    <div className="dash-card-head">
      <h2 id="courses-title">Курсы СДО</h2>
      {courses.length > 0 && <span className="dash-card-meta tabular">{courses.length}</span>}
    </div>
    {courses.length === 0 ? (
      <p className="cal-empty">Курсы подтягиваются из СДО КГУ при входе через ЭИОС (пароль тот же). Если их нет — выйдите и войдите снова.</p>
    ) : (
      <ul className="list cal-courses">
        {courses.map(c => (
          <li key={c.id}>
            <a href={c.url} target="_blank" rel="noopener noreferrer" className="cal-course">
              <BookOpen size={16} {...ICON} /><span>{c.name}</span><ExternalLink size={14} {...ICON} />
            </a>
          </li>
        ))}
      </ul>
    )}
  </section>
);

// --- Page ---------------------------------------------------------------------------------------------

const LESSONS_NOTE = {
  stale: 'ЭИОС сейчас не отвечает — показана последняя сохранённая копия расписания.',
  unavailable: 'ЭИОС сейчас недоступна, поэтому пар в календаре нет. Остальное показано.',
  no_group: 'Пары появятся, когда в профиле будет указана группа из ЭИОС.',
};

const AddMenu = ({ canHomework, leads, onHomework, onMeeting }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const navigate = useNavigate();
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', onKey); };
  }, [open]);
  const pick = (fn) => () => { setOpen(false); fn(); };
  return (
    <div className="cal-add" ref={ref}>
      <button type="button" className="btn btn-primary" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen(v => !v)}>
        <Plus size={16} {...ICON} />Добавить
      </button>
      {open && (
        <ul className="cal-add-menu">
          <li><button type="button" onClick={pick(() => navigate('/tasks?new=1'))}><SquareKanban size={16} {...ICON} />Задачу себе</button></li>
          {canHomework && <li><button type="button" onClick={pick(() => onHomework(''))}><NotebookPen size={16} {...ICON} />ДЗ для группы</button></li>}
          {leads.length > 0 && <li><button type="button" onClick={pick(onMeeting)}><Handshake size={16} {...ICON} />Собрание объединения</button></li>}
        </ul>
      )}
    </div>
  );
};

const Calendar = () => {
  const { user, isLoggedIn } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const wide = useWide();
  // ?day=YYYY-MM-DD (from the dashboard) opens that day
  const [params] = useSearchParams();
  const initialDay = /^\d{4}-\d{2}-\d{2}$/.test(params.get('day') || '') ? parseDay(params.get('day')) : new Date();

  const [monday, setMonday] = useState(() => weekStart(initialDay));
  const [selected, setSelected] = useState(() => dayKey(initialDay));
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [homework, setHomework] = useState([]);
  const [courses, setCourses] = useState([]);
  const [leads, setLeads] = useState([]);
  const [types, setTypes] = useState(readTypes);
  const [subgroup, setSubgroup] = useState(readSubgroup);

  const [lesson, setLesson] = useState(null);
  const [meetingId, setMeetingId] = useState(null);
  const [hwOpen, setHwOpen] = useState(null);
  const [hwForm, setHwForm] = useState(null); // { entry } or { preset }
  const [meetingFormOpen, setMeetingFormOpen] = useState(false);

  const load = useCallback(() => {
    if (!isLoggedIn) return;
    setError('');
    calendarApi.get(dayKey(monday), 7)
      .then(setData)
      .catch(e => { setError(e.message || 'Не удалось загрузить календарь'); setData({ items: [], lessons: 'ok' }); });
  }, [isLoggedIn, monday]);
  useEffect(load, [load]);

  const loadSide = useCallback(() => {
    if (!isLoggedIn) return;
    homeworkApi.list().then(r => setHomework(r || [])).catch(() => setHomework([]));
  }, [isLoggedIn]);
  useEffect(() => {
    if (!isLoggedIn) return;
    loadSide();
    calendarApi.courses().then(r => setCourses(r || [])).catch(() => setCourses([]));
    associationsApi.mine()
      .then(rows => setLeads((rows || []).filter(r => r.role === 'leader' && r.status === 'approved')
        .map(r => ({ id: r.association_id, name: r.association_name }))))
      .catch(() => setLeads([]));
  }, [isLoggedIn, loadSide]);

  const days = useMemo(() => {
    const week = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
    // Sunday only when something happens on it
    const sunday = dayKey(week[6]);
    const busySunday = (data?.items || []).some(i => dayKey(new Date(i.starts_at)) === sunday);
    return busySunday || !wide ? week : week.slice(0, 6);
  }, [monday, data, wide]);

  const allItems = data?.items || [];
  const subgroups = [...new Set(allItems.filter(i => i.type === 'lesson' && i.subgroup).map(i => i.subgroup))].sort();
  const items = allItems.filter(i => types.includes(i.type) && fitsSubgroup(i, subgroup));

  const goWeek = (delta) => {
    const next = addDays(monday, delta * 7);
    setMonday(next);
    setData(null);
    // Keep the same weekday selected on the phone
    const offset = (parseDay(selected).getDay() + 6) % 7;
    setSelected(dayKey(addDays(next, offset)));
  };
  const goToday = () => {
    const now = new Date();
    if (dayKey(weekStart(now)) !== dayKey(monday)) { setMonday(weekStart(now)); setData(null); }
    setSelected(dayKey(now));
  };

  const toggleType = (t) => setTypes((prev) => {
    const next = prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t];
    try { localStorage.setItem(TYPES_KEY, JSON.stringify(Object.keys(TYPES).filter(t => !next.includes(t)))); } catch { /* private mode */ }
    return next;
  });
  const pickSubgroup = (n) => { setSubgroup(n); saveSubgroup(n); };

  const open = (item) => {
    if (item.type === 'lesson') setLesson(item);
    else if (item.type === 'meeting') setMeetingId(item.ref_id);
    else if (item.type === 'task') navigate(`/tasks/${item.ref_id}`);
    else if (item.type === 'event') navigate(`/events/${item.ref_id}`);
    else setHwOpen(homework.find(h => h.id === item.ref_id) || { id: item.ref_id, subject: item.title, text: item.text, due_at: item.starts_at });
  };

  const afterHomework = () => { loadSide(); load(); };
  const deleteHomework = async (entry) => {
    if (!window.confirm('Удалить запись? Она пропадёт у всей группы.')) return;
    try {
      await homeworkApi.remove(entry.id);
      setHwOpen(null);
      toast.show('Запись удалена', 'success');
      afterHomework();
    } catch (e) {
      toast.show(e.message || 'Не удалось удалить', 'error');
    }
  };

  const subjects = useMemo(
    () => [...new Set(allItems.filter(i => i.type === 'lesson').map(i => i.title))].sort((a, b) => a.localeCompare(b, 'ru')),
    [allItems],
  );

  const header = (
    <header className="page-header tasks-header">
      <div className="page-heading">
        <SectionIcon section="calendar" size="lg" />
        <div>
          <h1>Календарь</h1>
          <p className="page-subtitle">
            {isLoggedIn ? 'Пары, собрания объединений, мероприятия, дедлайны задач и ДЗ группы в одном месте.' : 'Пары, собрания, мероприятия, дедлайны и ДЗ группы в одном месте.'}
          </p>
        </div>
      </div>
      {isLoggedIn && (
        <AddMenu canHomework={!!user?.group} leads={leads} onHomework={(preset) => setHwForm({ preset })} onMeeting={() => setMeetingFormOpen(true)} />
      )}
    </header>
  );

  if (!isLoggedIn) {
    return (
      <div className="container cal-page">
        {header}
        <div className="empty-state">
          <h2 className="cm-empty-title">Календарь виден после входа</h2>
          <p>Войдите через ЭИОС: здесь появятся пары вашей группы, ссылки на курсы СДО, собрания объединений и дедлайны.</p>
          <Link to="/profile" className="btn btn-primary"><LogIn size={16} {...ICON} />Войти через ЭИОС</Link>
          <Link to="/schedule" className="btn btn-ghost"><CalendarSearch size={16} {...ICON} />Расписание без входа</Link>
        </div>
      </div>
    );
  }

  const thisWeek = dayKey(weekStart(new Date())) === dayKey(monday);

  return (
    <div className="container cal-page">
      {header}

      <div className="cal-toolbar">
        <div className="cal-nav">
          <button type="button" className="btn btn-secondary btn-icon" onClick={() => goWeek(-1)} aria-label="Предыдущая неделя"><ChevronLeft size={18} {...ICON} /></button>
          <button type="button" className="btn btn-secondary" onClick={goToday} disabled={thisWeek && selected === dayKey(new Date())}>Сегодня</button>
          <button type="button" className="btn btn-secondary btn-icon" onClick={() => goWeek(1)} aria-label="Следующая неделя"><ChevronRight size={18} {...ICON} /></button>
          <h2 className="cal-range" aria-live="polite">{rangeTitle(monday, addDays(monday, 6))}</h2>
        </div>
        <div className="cal-filters" role="group" aria-label="Что показывать">
          {Object.entries(TYPES).map(([t, meta]) => (
            <button key={t} type="button" className={`chip cal-type-chip hue-${meta.hue}`} aria-pressed={types.includes(t)} onClick={() => toggleType(t)}>
              <span className="cal-type-dot" aria-hidden="true" />{meta.label}
            </button>
          ))}
        </div>
        {subgroups.length > 0 && (
          <div className="segmented cal-subgroup" role="group" aria-label="Моя подгруппа">
            <button type="button" className={`segmented-item ${subgroup === 0 ? 'active' : ''}`} aria-pressed={subgroup === 0} onClick={() => pickSubgroup(0)}>Все подгруппы</button>
            {subgroups.map(n => (
              <button key={n} type="button" className={`segmented-item ${subgroup === n ? 'active' : ''}`} aria-pressed={subgroup === n} onClick={() => pickSubgroup(n)}>{n} п/г</button>
            ))}
          </div>
        )}
      </div>

      {error && <p className="field-error" role="alert">{error}</p>}
      {data && LESSONS_NOTE[data.lessons] && types.includes('lesson') && (
        <p className="cal-note"><AlertTriangle size={16} {...ICON} />{LESSONS_NOTE[data.lessons]}
          {data.lessons === 'no_group' && <> <Link to="/profile">Открыть профиль</Link></>}
        </p>
      )}

      {data === null ? (
        <span className="skeleton cal-skeleton" aria-busy="true" />
      ) : wide ? (
        <WeekGrid days={days} items={items} onOpen={open} />
      ) : (
        <DayList days={days} items={items} selected={selected} onSelect={setSelected} onOpen={open} />
      )}

      <p className="cal-foot">
        <Link to="/schedule"><CalendarSearch size={16} {...ICON} />Расписание другой группы, преподавателя или аудитории</Link>
      </p>

      <div className="cal-side">
        {user?.group && <HomeworkList entries={homework} group={user.group} onAdd={(preset) => setHwForm({ preset })} onOpen={setHwOpen} />}
        <CourseList courses={courses} />
      </div>

      <LessonDialog item={lesson} onClose={() => setLesson(null)} onHomework={(subject) => { setLesson(null); setHwForm({ preset: subject }); }} />
      <MeetingDialog meetingId={meetingId} onClose={() => setMeetingId(null)} onChanged={load} />
      <HomeworkDialog entry={hwOpen} onClose={() => setHwOpen(null)} onDelete={deleteHomework}
        onEdit={(entry) => { setHwOpen(null); setHwForm({ entry }); }} />
      <HomeworkForm
        open={!!hwForm}
        entry={hwForm?.entry || null}
        preset={hwForm?.preset || ''}
        group={user?.group || ''}
        subjects={subjects}
        onClose={() => setHwForm(null)}
        onSaved={() => { setHwForm(null); toast.show('Сохранено — группа увидит запись', 'success'); afterHomework(); }}
      />
      <MeetingForm
        open={meetingFormOpen}
        associations={leads}
        onClose={() => setMeetingFormOpen(false)}
        onSaved={() => { setMeetingFormOpen(false); toast.show('Собрание назначено — участники увидят его в календаре', 'success'); load(); }}
      />
    </div>
  );
};

export default Calendar;
