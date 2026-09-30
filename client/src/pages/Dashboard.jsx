import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import {
  ChevronRight, ChevronDown, Circle, CheckCircle2, ArrowRight, MessageCircle, LogIn, MapPin
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import ScheduleWidget from '../components/ScheduleWidget';
import { TodayCard, MyTasksCard } from '../components/DashboardToday';
import SectionIcon from '../components/SectionIcon';
import { SECTIONS } from '../data/sections';
import { calendarApi, contentApi, eventsApi, tasksApi } from '../services/api';
import { openChat } from '../utils/chat';
import { markStep, readSteps, ONBOARDING_EVENT } from '../utils/onboarding';
import { subgroupOf, cleanLessonTitle } from '../utils/lessons';
import { dayKey, fitsSubgroup, readSubgroup, timeLabel } from '../utils/calendar';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

// The tab bar already has the calendar, tasks and associations; these are the other main sections (FAQ is in the menu)
const SHORTCUTS = ['events', 'forum', 'map', 'teachers'];

const pad2 = (n) => String(n).padStart(2, '0');
const localIso = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const plural = (n, [one, few, many]) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
};

const toMinutes = (hm = '') => {
  const [h, m] = hm.split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
};
const formatDuration = (mins) => (mins < 60
  ? `${mins} мин`
  : `${Math.floor(mins / 60)} ч${mins % 60 ? ` ${mins % 60} мин` : ''}`);

/**
 * Today's lessons for the hero: how many, the one in progress or the next one, and — once today
 * is over or free — the first lesson of the next study day. Null while the schedule is unknown.
 * Each of those is a time slot: { start, end, parts }, where parts are the lessons at that time
 * (one per subgroup when subgroups have different pairs).
 */
const summariseToday = (info) => {
  if (!info) return null;
  const now = new Date();
  const today = localIso(now);
  const nowMin = now.getHours() * 60 + now.getMinutes();

  // Lessons of one day grouped by start time, sorted
  const slotsOf = (day) => {
    const slots = new Map();
    info.lessons.filter(l => l.дата && l.дата.startsWith(day)).forEach(l => {
      const slot = slots.get(l.начало) || { start: l.начало, end: l.конец, parts: [] };
      const part = { title: cleanLessonTitle(l.дисциплина), room: l.аудитория || '', sub: subgroupOf(l) };
      if (!slot.parts.some(p => p.title === part.title && p.room === part.room && p.sub === part.sub)) slot.parts.push(part);
      slots.set(l.начало, slot);
    });
    return [...slots.values()]
      .map(slot => ({ ...slot, parts: slot.parts.sort((a, b) => a.sub - b.sub) }))
      .sort((a, b) => toMinutes(a.start) - toMinutes(b.start));
  };

  const lessons = slotsOf(today);
  const current = lessons.find(l => toMinutes(l.start) <= nowMin && nowMin < toMinutes(l.end));
  const next = lessons.find(l => toMinutes(l.start) > nowMin);

  let later = null;
  if (!current && !next) {
    const day = info.lessons.map(l => (l.дата || '').slice(0, 10)).filter(d => d > today).sort()[0];
    if (day) {
      const tomorrow = new Date(now);
      tomorrow.setDate(now.getDate() + 1);
      const dayLabel = day === localIso(tomorrow)
        ? 'Завтра'
        : new Date(`${day}T00:00:00`).toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' });
      later = { ...slotsOf(day)[0], dayLabel: dayLabel.charAt(0).toUpperCase() + dayLabel.slice(1) };
    }
  }

  return {
    group: info.group || '',
    count: lessons.length,
    current: current ? { ...current, left: toMinutes(current.end) - nowMin } : null,
    next: !current && next ? { ...next, in: toMinutes(next.start) - nowMin } : null,
    later,
    done: lessons.length > 0 && !current && !next,
  };
};

const RoomLink = ({ room }) => (/^Б-?\d{3}/i.test(room) ? (
  <Link to={`/map?room=${encodeURIComponent(room)}`} className="dash-hero-room">
    <MapPin size={15} {...ICON} />
    <span className="visually-hidden">Аудитория </span>{room}
  </Link>
) : (
  <span className="dash-hero-room"><MapPin size={15} {...ICON} />{room}</span>
));

const subLabel = (sub) => (sub ? `${sub} подгруппа` : 'Вся группа');

/**
 * The lesson in progress, the next one, or the first one of the next study day, as a white slip.
 * One warm chip carries the status and the time left: filled while the lesson is on, outlined before it.
 * When subgroups have different pairs at that time, each gets its own line with its room.
 */
const HeroLesson = ({ lesson, kind }) => {
  const chip = kind === 'now'
    ? `Идёт · ещё ${formatDuration(lesson.left)}`
    : kind === 'next'
      ? `Следующая · через ${formatDuration(lesson.in)}`
      : lesson.dayLabel;
  const [only] = lesson.parts;
  const split = lesson.parts.length > 1;
  return (
    <div className="dash-hero-lesson">
      {split ? (
        <ul className="dash-hero-parts">
          {lesson.parts.map(part => (
            <li key={`${part.sub}-${part.title}-${part.room}`} className="dash-hero-part">
              <span className="dash-hero-sub tabular">{subLabel(part.sub)}</span>
              <span className="dash-hero-part-title">{part.title}</span>
              {part.room && <RoomLink room={part.room} />}
            </li>
          ))}
        </ul>
      ) : (
        <span className="dash-hero-lesson-title">
          {only.sub > 0 && <span className="dash-hero-sub tabular">{subLabel(only.sub)}</span>}
          {only.title}
        </span>
      )}
      <span className="dash-hero-lesson-meta tabular">
        <span className={`dash-hero-chip ${kind === 'now' ? 'is-now' : ''}`}>{chip}</span>
        <span className="dash-hero-clock">{kind === 'now' ? `до ${lesson.end}` : `в ${lesson.start}`}</span>
        {!split && only.room && <RoomLink room={only.room} />}
      </span>
    </div>
  );
};

// "Философия" or "у 1 подгруппы — Python, у 2 подгруппы — Базы данных"
const partsText = (parts) => (parts.length > 1
  ? parts.map(p => `${p.sub ? `у ${p.sub} подгруппы` : 'у всей группы'} — ${p.title}`).join(', ')
  : parts[0].title);

// What a screen reader hears: only when the status changes, not on every minute of the countdown
const heroStatus = (t) => {
  if (!t) return '';
  if (t.current) return `Сейчас идёт ${partsText(t.current.parts)}, до ${t.current.end}`;
  if (t.next) return `Следующая пара — ${partsText(t.next.parts)} в ${t.next.start}`;
  if (t.later) return `Следующая пара — ${t.later.dayLabel.toLowerCase()}, ${partsText(t.later.parts)} в ${t.later.start}`;
  return t.done ? 'На сегодня пары закончились' : '';
};

const Dashboard = () => {
  const navigate = useNavigate();
  const { user, isLoggedIn } = useAuth();

  // --- Announcements from backend (the API client keeps an offline copy) ---
  const [announcements, setAnnouncements] = useState([]);
  const [expandedAdIds, setExpandedAdIds] = useState([]);

  useEffect(() => {
    contentApi.getAnnouncements().then(res => {
      if (Array.isArray(res)) {
        setAnnouncements(res.map(a => ({
          id: a.id,
          title: a.title,
          text: a.content,
          important: !!a.is_important,
          time: new Date(a.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
        })));
      }
    }).catch(e => console.warn('Failed to load DB announcements on Dashboard:', e));
  }, []);

  // --- Signed in: the coming week from the calendar (lessons, meetings, deadlines) and open tasks ---
  const [calendar, setCalendar] = useState(null);
  const [toRate, setToRate] = useState([]);
  const [myCards, setMyCards] = useState(null);
  useEffect(() => {
    if (!isLoggedIn) { setCalendar(null); setMyCards(null); return; }
    calendarApi.get(dayKey(new Date()), 8)
      .then(setCalendar)
      .catch(() => setCalendar({ items: [], lessons: 'unavailable' }));
    tasksApi.my().then(res => setMyCards(res || [])).catch(() => setMyCards([]));
    eventsApi.pendingFeedback().then(res => setToRate(res || [])).catch(() => setToRate([]));
  }, [isLoggedIn]);
  const subgroup = readSubgroup();
  const calendarItems = (calendar?.items || []).filter(i => fitsSubgroup(i, subgroup));
  // Without a group EIOS knows, the schedule widget (with its group / teacher chooser) stays
  const calendarLessons = isLoggedIn && calendar && calendar.lessons !== 'no_group';

  // --- Today's lessons: from the calendar, or reported by the schedule widget ---
  const [widgetLessons, setGroupLessons] = useState(null);
  const groupLessons = calendarLessons
    ? {
        group: calendar.group,
        // In the shape of EIOS rows, which the hero summary reads
        lessons: calendarItems.filter(i => i.type === 'lesson').map(i => ({
          дата: dayKey(new Date(i.starts_at)),
          начало: timeLabel(i.starts_at),
          конец: timeLabel(i.ends_at),
          дисциплина: i.title,
          аудитория: i.place,
          номерПодгруппы: i.subgroup,
        })),
      }
    : widgetLessons;
  const ownGroup = user?.group ? { id: user.groupId || null, name: user.group } : null;
  // Re-render every 30 s so "сейчас идёт / следующая" follows the clock
  const [, setClockTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setClockTick(t => t + 1), 30000);
    return () => clearInterval(timer);
  }, []);
  const todaySummary = summariseToday(groupLessons);

  // Onboarding tasks definition
  const initialTasks = [
    { id: 'profile-curator', text: 'Зайти в личный кабинет', route: '/profile' },
    { id: 'schedule', text: 'Посмотреть расписание', route: '/schedule' },
    { id: 'faq', text: 'Посмотреть частые вопросы', route: '/faq' },
    { id: 'teachers', text: 'Посмотреть преподавателей', route: '/teachers' },
    { id: 'map', text: 'Открыть карту кампуса', route: '/map' },
    { id: 'forum', text: 'Заглянуть на форум', route: '/forum' },
    // Only when there is something to read
    ...(announcements.length ? [{ id: 'ads', text: 'Прочитать объявления', isAdTrigger: true }] : []),
  ];

  const [completedTaskIds, setCompletedTaskIds] = useState(() => readSteps(user?.id));

  // Steps are also completed elsewhere (App marks visited sections); keep the card in sync
  useEffect(() => {
    const sync = () => setCompletedTaskIds(readSteps(user?.id));
    sync();
    window.addEventListener(ONBOARDING_EVENT, sync);
    return () => window.removeEventListener(ONBOARDING_EVENT, sync);
  }, [user?.id]);

  const markTaskDone = (taskId) => markStep(user?.id, taskId);

  // "/#schedule-section" (the shortcut of apps installed before /schedule existed) opens the page at today's pairs;
  // after the frame, so the scroll-to-top on navigation does not undo it
  const { hash } = useLocation();
  useEffect(() => {
    if (hash !== '#schedule-section') return undefined;
    const frame = requestAnimationFrame(() => document.getElementById('schedule-section')?.scrollIntoView());
    return () => cancelAnimationFrame(frame);
  }, [hash]);

  const handleTaskClick = (task) => {
    markTaskDone(task.id);
    if (task.route) {
      navigate(task.route);
    } else if (task.isAdTrigger) {
      document.getElementById('announcements-section')?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const toggleAdExpansion = (ad) => {
    markTaskDone('ads');
    setExpandedAdIds(prev =>
      prev.includes(ad.id) ? prev.filter(id => id !== ad.id) : [...prev, ad.id]
    );
  };

  const completedCount = initialTasks.filter(t => completedTaskIds.includes(t.id)).length;
  const progressPercent = Math.round((completedCount / initialTasks.length) * 100);
  const nextTask = initialTasks.find(t => !completedTaskIds.includes(t.id));
  const [showAllSteps, setShowAllSteps] = useState(false);

  // Greeting: a real "Фамилия Имя [Отчество]" becomes "Имя"; anything else
  // (e.g. "Администратор ИВИТШ КГУ", "Студент 24-isbo-085") keeps the generic greeting.
  const firstName = isLoggedIn
    ? (() => {
        const parts = (user.fullName || '').trim().split(/\s+/);
        const looksLikeFio = parts.length >= 2 && parts.length <= 3 && parts.every(w => /^[А-ЯЁ][а-яё]+(-[А-ЯЁ]?[а-яё]+)?$/.test(w));
        return looksLikeFio ? parts[1] : null;
      })()
    : null;

  const todayLabel = new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
  // The date opens the lead line instead of sitting above the heading as a kicker
  const dateLead = todayLabel.charAt(0).toUpperCase() + todayLabel.slice(1);
  // A group name like "24-ИСбо-1" must not break at its hyphens
  const whose = todaySummary?.group ? <>У группы <span className="dash-hero-group">{todaySummary.group}</span></> : 'У вас';

  return (
    <div className="container dash">
      {/* HERO: greeting, today's lessons, the next thing to do */}
      <section className="dash-hero" aria-labelledby="dash-hello">
        <div className="dash-hero-text">
          <h1 id="dash-hello">
            {firstName ? `Привет, ${firstName}!` : isLoggedIn ? 'Добро пожаловать!' : 'Добро пожаловать в ИВИТШ Хаб'}
          </h1>
          <div className="dash-hero-today">
            {!isLoggedIn ? (
              <p className="dash-hero-lead">{dateLead}. Войдите через ЭИОС, чтобы видеть пары своей группы.</p>
            ) : !todaySummary ? (
              <p className="dash-hero-lead">{dateLead}. Здесь расписание, объявления и помощник ВИТШик — всё в одном месте.</p>
            ) : (
              <>
                <p className="dash-hero-lead">
                  {dateLead}.{' '}
                  {todaySummary.count === 0
                    ? <>{whose} сегодня пар нет</>
                    : todaySummary.done
                      ? <>{whose} сегодня было <strong className="tabular">{todaySummary.count} {plural(todaySummary.count, ['пара', 'пары', 'пар'])}</strong>, занятия закончились</>
                      : <>{whose} сегодня <strong className="tabular">{todaySummary.count} {plural(todaySummary.count, ['пара', 'пары', 'пар'])}</strong></>}
                </p>
                {todaySummary.current && <HeroLesson lesson={todaySummary.current} kind="now" />}
                {todaySummary.next && <HeroLesson lesson={todaySummary.next} kind="next" />}
                {todaySummary.later && <HeroLesson lesson={todaySummary.later} kind="later" />}
              </>
            )}
            <p className="visually-hidden" aria-live="polite">{heroStatus(todaySummary)}</p>
          </div>
          <div className="dash-hero-actions">
            {!isLoggedIn && (
              <Link to="/profile" className="btn btn-primary">
                <LogIn size={16} {...ICON} />
                Войти через ЭИОС
              </Link>
            )}
            <button type="button" className={`btn ${isLoggedIn ? 'btn-primary' : 'btn-secondary'}`} onClick={openChat}>
              <MessageCircle size={16} {...ICON} />
              Спросить ВИТШика
            </button>
          </div>
        </div>
        <img src="/img/mascot-320.png" alt="" className="dash-hero-mascot" width="160" height="160" />
      </section>

      {/* SECTION SHORTCUTS */}
      <nav className="dash-shortcuts" aria-label="Разделы портала">
        <ul>
          {SHORTCUTS.map((id) => {
            const { label, path, hint } = SECTIONS[id];
            return (
              <li key={id}>
                <Link to={path} className="dash-shortcut" onClick={() => markTaskDone(id)}>
                  <SectionIcon section={id} quiet />
                  <span className="dash-shortcut-text">
                    <span className="dash-shortcut-label">{label}</span>
                    <span className="dash-shortcut-hint">{hint}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="dash-grid">
        {/* TODAY: the nearest pairs; the full schedule has its own page */}
        <section id="schedule-section" className="dash-main" aria-labelledby={isLoggedIn && calendarLessons ? 'today-title' : 'schedule-title'}>
          {!calendarLessons && (isLoggedIn ? calendar : true) && (
            <ScheduleWidget onGroupLessons={setGroupLessons} ownGroup={ownGroup} compact />
          )}
          {isLoggedIn && (calendar
            ? <TodayCard items={calendarItems.filter(i => calendarLessons || i.type !== 'lesson')} status={calendar.lessons} />
            : <span className="skeleton dash-today-skeleton" aria-busy="true" />)}
        </section>

        <div className="dash-aside">
          {isLoggedIn && <MyTasksCard cards={myCards} />}

          {/* The survey after an event the student took part in */}
          {toRate.length > 0 && (
            <section className="card dash-card hue-red dash-rate" aria-labelledby="rate-title">
              <div className="dash-card-head"><h2 id="rate-title">Оцените мероприятие</h2></div>
              <ul className="list dash-rows">
                {toRate.slice(0, 3).map(e => (
                  <li key={e.id}>
                    <Link to={`/events/${e.id}#feedback`} className="dash-row-btn">
                      <span className="dash-row-label">{e.title}</span>
                      <ChevronRight size={16} className="dash-row-arrow" {...ICON} />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* ANNOUNCEMENTS: hidden until there are any */}
          {announcements.length > 0 && (
          <section id="announcements-section" className="card dash-card" aria-labelledby="announcements-title">
            <div className="dash-card-head">
              <h2 id="announcements-title">Объявления</h2>
              {announcements.length > 0 && <span className="dash-card-meta tabular">{announcements.length}</span>}
            </div>

            <ul className="list dash-rows">
                {announcements.map((ad) => {
                  const isExpanded = expandedAdIds.includes(ad.id);
                  const bodyId = `announcement-${ad.id}`;
                  return (
                    <li key={ad.id} className={`dash-ann ${isExpanded ? 'is-open' : ''} ${ad.important ? 'is-important' : ''}`}>
                      <h3 className="dash-ann-heading">
                        <button
                          type="button"
                          className="dash-row-btn dash-ann-toggle"
                          aria-expanded={isExpanded}
                          aria-controls={bodyId}
                          onClick={() => toggleAdExpansion(ad)}
                        >
                          <span className="dash-ann-text">
                            <span className="dash-ann-title">{ad.title}</span>
                            <span className="dash-ann-meta">
                              {ad.important && <span className="badge badge-warm">Важно</span>}
                              <span className="tabular">{ad.time}</span>
                            </span>
                          </span>
                          <ChevronDown size={18} className="dash-chevron" {...ICON} />
                        </button>
                      </h3>

                      {isExpanded && (
                        <div id={bodyId} className="dash-ann-body">
                          <p>{ad.text}</p>
                        </div>
                      )}
                    </li>
                  );
                })}
            </ul>
          </section>
          )}

          {/* ONBOARDING (guests): progress and the one next step; the full list on demand */}
          {!isLoggedIn && (
          <section className="card dash-card dash-onboarding" aria-labelledby="onboarding-title">
            <div className="dash-card-head">
              <h2 id="onboarding-title">Знакомство с порталом</h2>
              <span className="dash-card-meta tabular">
                {completedCount} из {initialTasks.length}
                <span className="visually-hidden"> шагов выполнено</span>
              </span>
            </div>
            <div
              className="progress"
              role="progressbar"
              aria-labelledby="onboarding-title"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.min(progressPercent, 100)}
            >
              <div
                className="progress-value"
                style={{ transform: `scaleX(${Math.min(progressPercent, 100) / 100})` }}
              />
            </div>

            {nextTask ? (
              <button type="button" className="dash-onb-next" onClick={() => handleTaskClick(nextTask)}>
                <span className="dash-onb-next-text">
                  <span className="dash-onb-next-label">Следующий шаг</span>
                  <span className="dash-onb-next-title">{nextTask.text}</span>
                </span>
                <ArrowRight size={18} {...ICON} />
              </button>
            ) : (
              <p className="dash-onb-done">Все шаги пройдены — вы освоились на портале.</p>
            )}

            <button
              type="button"
              className="btn btn-ghost btn-sm dash-onb-toggle"
              aria-expanded={showAllSteps}
              aria-controls="onboarding-steps"
              onClick={() => setShowAllSteps(v => !v)}
            >
              {showAllSteps ? 'Скрыть шаги' : 'Все шаги'}
              <ChevronDown size={16} className="dash-chevron" {...ICON} />
            </button>

            {showAllSteps && (
              <ul id="onboarding-steps" className="list dash-rows dash-onb-list">
                {initialTasks.map((task) => {
                  const isCompleted = completedTaskIds.includes(task.id);
                  return (
                    <li key={task.id}>
                      <button
                        type="button"
                        className={`dash-row-btn dash-onb-row ${isCompleted ? 'is-done' : ''}`}
                        onClick={() => handleTaskClick(task)}
                      >
                        {isCompleted
                          ? <CheckCircle2 size={20} className="dash-onb-status" {...ICON} />
                          : <Circle size={20} className="dash-onb-status" {...ICON} />}
                        <span className="dash-row-label">
                          {task.text}
                          {isCompleted && <span className="visually-hidden"> — выполнено</span>}
                        </span>
                        <ChevronRight size={16} className="dash-row-arrow" {...ICON} />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
