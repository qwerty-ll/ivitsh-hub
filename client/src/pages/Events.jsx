import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Star } from 'lucide-react';
import SectionIcon from '../components/SectionIcon';
import EventForm from '../components/EventForm';
import Portfolio from '../components/Portfolio';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { associationsApi, eventsApi } from '../services/api';
import EventCard from '../components/EventCard';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

const TABS = [
  { id: 'upcoming', label: 'Предстоящие' },
  { id: 'mine', label: 'Мои' },
  { id: 'past', label: 'Прошедшие' },
  { id: 'managed', label: 'Организую', manager: true },
  { id: 'pgas', label: 'ПГАС' },
];

const EMPTY_TEXT = {
  upcoming: 'Ближайших мероприятий нет. Здесь появятся события института и ваших объединений.',
  mine: 'Вы пока никуда не записались.',
  past: 'Прошедших мероприятий нет.',
  managed: 'Вы пока не создали ни одного мероприятия.',
};

const Events = () => {
  const { isLoggedIn, isAdmin } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(t => t.id === params.get('tab')) ? params.get('tab') : 'upcoming';
  const [events, setEvents] = useState(null);
  const [pending, setPending] = useState([]);
  const [leads, setLeads] = useState(false);
  const [formOpen, setFormOpen] = useState(params.get('new') === '1');

  const canCreate = isAdmin || leads;

  useEffect(() => {
    if (!isLoggedIn) return;
    associationsApi.mine().then(rows => setLeads((rows || []).some(r => r.role === 'leader' && r.status === 'approved'))).catch(() => {});
    eventsApi.pendingFeedback().then(r => setPending(r || [])).catch(() => setPending([]));
  }, [isLoggedIn]);

  const load = useCallback(() => {
    if (tab === 'pgas') return;
    setEvents(null);
    eventsApi.list(tab).then(r => setEvents(r || [])).catch(() => setEvents([]));
  }, [tab]);
  useEffect(load, [load]);

  const setTab = (id) => {
    const p = new URLSearchParams(params);
    if (id === 'upcoming') p.delete('tab'); else p.set('tab', id);
    setParams(p, { replace: true });
  };

  const tabs = TABS.filter(t => (t.manager ? canCreate : true) && (isLoggedIn || t.id === 'upcoming' || t.id === 'past'));

  return (
    <div className="container events-page">
      <header className="page-header tasks-header">
        <div className="page-heading">
          <SectionIcon section="events" size="lg" />
          <div>
            <h1>Мероприятия</h1>
            <p className="page-subtitle">События института и объединений: запись участником или волонтёром в один клик, документы и сводка для ПГАС.</p>
          </div>
        </div>
        {canCreate && (
          <button type="button" className="btn btn-primary" onClick={() => setFormOpen(true)}><Plus size={16} {...ICON} />Создать</button>
        )}
      </header>

      {pending.length > 0 && (
        <section className="card event-survey" aria-labelledby="survey-title">
          <Star size={20} {...ICON} />
          <div>
            <h2 id="survey-title">Как всё прошло?</h2>
            <p>Оцените {pending.length === 1 ? 'мероприятие' : 'мероприятия'}, где вы участвовали — это займёт минуту:</p>
            <ul>
              {pending.map(e => <li key={e.id}><Link to={`/events/${e.id}#feedback`}>{e.title}</Link></li>)}
            </ul>
          </div>
        </section>
      )}

      <div className="segmented events-tabs" role="group" aria-label="Какие мероприятия показать">
        {tabs.map(t => (
          <button key={t.id} type="button" className={`segmented-item ${tab === t.id ? 'active' : ''}`} aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'pgas' ? (
        <Portfolio />
      ) : events === null ? (
        <ul className="event-grid" aria-busy="true">{[0, 1, 2].map(i => <li key={i}><span className="skeleton" style={{ height: '9rem' }} /></li>)}</ul>
      ) : events.length === 0 ? (
        <div className="empty-state">
          <p>{EMPTY_TEXT[tab]}</p>
          {!isLoggedIn && tab === 'upcoming' && <p>Войдите через ЭИОС, чтобы видеть мероприятия своих объединений и записываться.</p>}
        </div>
      ) : (
        <ul className="event-grid">{events.map(e => <EventCard key={e.id} e={e} />)}</ul>
      )}

      <EventForm
        open={formOpen}
        presetAssociation={params.get('new') === '1' ? params.get('association') : null}
        onClose={() => {
          setFormOpen(false);
          if (params.get('new')) { const p = new URLSearchParams(params); p.delete('new'); p.delete('association'); setParams(p, { replace: true }); }
        }}
        onSaved={(e) => { setFormOpen(false); toast.show('Мероприятие создано', 'success'); navigate(`/events/${e.id}`); }}
      />
    </div>
  );
};

export default Events;
