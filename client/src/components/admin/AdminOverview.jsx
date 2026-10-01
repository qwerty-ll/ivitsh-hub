import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { adminApi } from '../../services/api';
import { Toolbar, RefreshButton, ListSkeleton, LoadError } from './AdminUi';
import { plural } from '../../utils/plural';

const COURSE = (c) => (c ? `${c} курс` : 'Без курса');

// One queue row: how many, what, where to handle it
const Queue = ({ count, label, to, onClick }) => {
  const body = (
    <>
      <span className={`admin-queue-count tabular ${count ? 'is-waiting' : ''}`}>{count}</span>
      <span className="admin-queue-label">{label}</span>
      <ChevronRight size={16} strokeWidth={1.75} aria-hidden="true" className="admin-queue-arrow" />
    </>
  );
  return (
    <li>
      {to ? <Link to={to} className="admin-queue">{body}</Link>
        : <button type="button" className="admin-queue" onClick={onClick}>{body}</button>}
    </li>
  );
};

/** "Сводка" tab: the administration's work across sections in one place, with links to where it is done. */
const AdminOverview = ({ panelProps, onOpenTab }) => {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setError('');
    adminApi.getOverview().then(setData).catch(e => setError(e.message || 'Не удалось загрузить сводку'));
  }, []);
  useEffect(load, [load]);

  if (error) return <section {...panelProps}><LoadError message={error} onRetry={load} /></section>;
  if (!data) return <section {...panelProps}><ListSkeleton /></section>;
  const { waiting, today, students, tournament } = data;
  const share = students.total ? Math.round((students.active_semester / students.total) * 100) : 0;
  return (
    <section {...panelProps}>
      <Toolbar title="Сводка" description="Что ждёт решения во всех разделах и кто пользуется порталом.">
        <RefreshButton onClick={load} />
      </Toolbar>

      <div className="admin-overview">
        <div className="card admin-overview-card">
          <h3>Ждёт решения</h3>
          <ul className="admin-queues">
            <Queue count={waiting.orders_new} label={`${plural(waiting.orders_new, ['новый заказ', 'новых заказа', 'новых заказов'])} в магазине`} to="/shop?tab=admin" />
            <Queue count={waiting.orders_ready} label={`${plural(waiting.orders_ready, ['заказ готов', 'заказа готовы', 'заказов готовы'])} к выдаче — студенты ждут`} to="/shop?tab=admin" />
            <Queue count={waiting.forum_unanswered} label={`${plural(waiting.forum_unanswered, ['вопрос', 'вопроса', 'вопросов'])} на форуме без ответа`} to="/forum" />
            <Queue count={waiting.associations_without_leader} label={`${plural(waiting.associations_without_leader, ['объединение', 'объединения', 'объединений'])} без руководителя`} onClick={() => onOpenTab('associations')} />
            <Queue count={waiting.applications_pending} label={`${plural(waiting.applications_pending, ['заявка', 'заявки', 'заявок'])} в объединения ждут руководителей`} to="/associations" />
          </ul>
        </div>

        <div className="card admin-overview-card">
          <h3>Сегодня и дальше</h3>
          <ul className="admin-queues">
            <Queue count={today.bookings} label={`${plural(today.bookings, ['бронь', 'брони', 'броней'])} коворкинга 108 сегодня`} to="/booking" />
            <Queue count={today.events_upcoming} label={plural(today.events_upcoming, ['предстоящее мероприятие', 'предстоящих мероприятия', 'предстоящих мероприятий'])} to="/events?tab=managed" />
            <li>
              <Link to="/tribes" className="admin-queue">
                <span className="admin-queue-label">
                  {tournament ? <>Идёт турнир «{tournament.title}» — до {new Date(tournament.ends_on).toLocaleDateString('ru-RU')}</> : 'Турнир трайбов не идёт'}
                </span>
                <ChevronRight size={16} strokeWidth={1.75} aria-hidden="true" className="admin-queue-arrow" />
              </Link>
            </li>
          </ul>
        </div>

        <div className="card admin-overview-card admin-overview-wide">
          <h3>Студенты на портале</h3>
          <p className="admin-overview-lead">
            <span className="tabular">{students.active_semester}</span> из <span className="tabular">{students.total}</span> заходили
            в этом семестре ({share}%).
          </p>
          <table className="admin-table admin-courses">
            <caption className="visually-hidden">Активность по курсам</caption>
            <thead>
              <tr><th scope="col">Курс</th><th scope="col" className="admin-num">Вошли хоть раз</th><th scope="col" className="admin-num">Заходили в семестре</th><th scope="col">Доля</th></tr>
            </thead>
            <tbody>
              {students.by_course.map(c => {
                const pct = c.total ? Math.round((c.active / c.total) * 100) : 0;
                return (
                  <tr key={c.course ?? 'none'}>
                    <td>{COURSE(c.course)}</td>
                    <td className="admin-num tabular">{c.total}</td>
                    <td className="admin-num tabular">{c.active}</td>
                    <td>
                      <span className="admin-bar" aria-label={`${pct}%`}><span style={{ width: `${pct}%` }} /></span>
                      <span className="tabular admin-bar-pct">{pct}%</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};

export default AdminOverview;
