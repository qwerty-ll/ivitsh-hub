import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, CalendarClock, CheckCircle2, Plus } from 'lucide-react';
import { TYPES, dayKey, dayTitle, hueOf, isDeadline, timeLabel } from '../utils/calendar';
import { dueInfo } from '../utils/tasks';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

const where = (item) => {
  if (item.type === 'lesson') return [item.place, item.subgroup ? `${item.subgroup} п/г` : ''].filter(Boolean).join(' · ');
  if (item.type === 'meeting') return [item.association?.name, item.place].filter(Boolean).join(' · ');
  if (item.type === 'booking') return [item.association?.name, item.text].filter(Boolean).join(' · ');
  if (item.type === 'event') return [TYPES.event.one, item.place].filter(Boolean).join(' · ');
  if (item.type === 'task') return item.association ? item.association.name : 'Личная задача';
  return TYPES.homework.one;
};

/**
 * "Сегодня": today's pairs, meetings and deadlines from the calendar; once today is over (or free),
 * the next day that has something. `items` are the calendar entries of the coming week.
 */
export const TodayCard = ({ items, status }) => {
  const navigate = useNavigate();
  const now = new Date();
  const today = dayKey(now);
  const todays = items.filter(i => dayKey(new Date(i.starts_at)) === today);
  const left = todays.filter(i => new Date(i.ends_at || i.starts_at) > now);
  const nextDay = left.length ? null : items.map(i => dayKey(new Date(i.starts_at))).filter(k => k > today).sort()[0];
  const shownKey = nextDay || today;
  const shown = nextDay ? items.filter(i => dayKey(new Date(i.starts_at)) === nextDay) : todays;
  const title = nextDay ? dayTitle(nextDay) : 'Сегодня';

  const open = (item) => {
    if (item.type === 'task') navigate(`/tasks/${item.ref_id}`);
    else if (item.type === 'event') navigate(`/events/${item.ref_id}`);
    else if (item.type === 'booking') navigate(`/booking?day=${shownKey}`);
    else navigate(`/calendar?day=${shownKey}`);
  };

  return (
    <section className="card dash-card dash-today" aria-labelledby="today-title">
      <div className="dash-card-head">
        <h2 id="today-title">{title}</h2>
        <Link to="/calendar" className="dash-card-link">Календарь<ArrowRight size={16} {...ICON} /></Link>
      </div>
      {nextDay && todays.length > 0 && <p className="dash-today-note">На сегодня всё — дальше:</p>}
      {status === 'unavailable' && <p className="dash-today-note">ЭИОС сейчас не отвечает, пар здесь нет.</p>}
      {shown.length === 0 ? (
        <p className="dash-today-empty">На ближайшую неделю ничего не запланировано.</p>
      ) : (
        <ul className="list dash-today-list">
          {shown.map((item) => {
            const deadline = isDeadline(item);
            const past = !nextDay && new Date(item.ends_at || item.starts_at) <= now;
            const current = !deadline && new Date(item.starts_at) <= now && now < new Date(item.ends_at);
            return (
              <li key={item.id}>
                <button type="button" onClick={() => open(item)}
                  className={`dash-today-row hue-${hueOf(item)} ${past ? 'is-past' : ''} ${current ? 'is-now' : ''}`}>
                  <span className="dash-today-time tabular">
                    {deadline ? `до ${timeLabel(item.starts_at)}` : timeLabel(item.starts_at)}
                  </span>
                  <span className="dash-today-text">
                    <span className="dash-today-title">
                      {item.title}
                      {current && <span className="badge badge-warm">Идёт</span>}
                      {item.replaced && <span className="badge badge-warning">Замена</span>}
                    </span>
                    <span className="dash-today-meta">
                      {deadline && <span className="cal-type">{TYPES[item.type].one}</span>}
                      {where(item)}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};

const OPEN = ['todo', 'in_progress'];
const SHOWN = 5;

/** "Мои задачи": open task cards, nearest deadline first. */
export const MyTasksCard = ({ cards }) => {
  const open = (cards || []).filter(c => OPEN.includes(c.my_status));
  const review = (cards || []).filter(c => c.my_status === 'review').length;
  return (
    <section className="card dash-card dash-mytasks" aria-labelledby="mytasks-title">
      <div className="dash-card-head">
        <h2 id="mytasks-title">Мои задачи</h2>
        <Link to="/tasks" className="dash-card-link">Все<ArrowRight size={16} {...ICON} /></Link>
      </div>
      {cards === null ? (
        <span className="skeleton" style={{ height: '4rem' }} />
      ) : open.length === 0 ? (
        <div className="dash-today-empty">
          <p><CheckCircle2 size={16} {...ICON} /> Открытых задач нет{review ? `, на проверке: ${review}` : ''}.</p>
          <Link to="/tasks?new=1" className="btn btn-ghost btn-sm"><Plus size={16} {...ICON} />Задача себе</Link>
        </div>
      ) : (
        <ul className="list dash-rows">
          {open.slice(0, SHOWN).map((c) => {
            const due = dueInfo(c.due_at, c.my_status);
            return (
              <li key={c.id}>
                <Link to={`/tasks/${c.id}`} className={`dash-row-btn dash-task-row ${!c.association ? `hue-${c.color || 'blue'} is-personal` : ''}`}>
                  <span className="dash-task-text">
                    <span className="dash-task-title">{c.title}</span>
                    <span className="dash-task-meta">
                      {c.association ? c.association.name : 'Личная'}
                      {c.my_status === 'in_progress' && ' · в работе'}
                    </span>
                  </span>
                  {due && <span className={`task-due task-due-${due.tone || 'plain'}`}><CalendarClock size={14} {...ICON} />{due.label}</span>}
                </Link>
              </li>
            );
          })}
          {open.length > SHOWN && (
            <li><Link to="/tasks" className="dash-row-btn dash-more">Ещё {open.length - SHOWN}</Link></li>
          )}
        </ul>
      )}
    </section>
  );
};
