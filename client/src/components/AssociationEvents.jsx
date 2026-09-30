import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';
import EventCard from './EventCard';
import { eventsApi } from '../services/api';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

/** Upcoming events organized by the association; leaders create new ones from here. */
const AssociationEvents = ({ associationId, canManage }) => {
  const [events, setEvents] = useState(null);
  useEffect(() => {
    eventsApi.list('upcoming', associationId).then(r => setEvents(r || [])).catch(() => setEvents([]));
  }, [associationId]);

  if (events === null || (!canManage && events.length === 0)) return null;
  return (
    <section className="card assoc-card-block" aria-labelledby="assoc-events">
      <div className="assoc-manage-head">
        <h2 id="assoc-events">Мероприятия</h2>
        {canManage && (
          <Link to={`/events?new=1&association=${associationId}`} className="btn btn-secondary btn-sm"><Plus size={16} {...ICON} />Создать</Link>
        )}
      </div>
      {events.length === 0
        ? <p className="assoc-muted">Создайте мероприятие — участники объединения запишутся в один клик, а после него получат документы.</p>
        : <ul className="event-grid event-grid-compact">{events.map(e => <EventCard key={e.id} e={e} />)}</ul>}
    </section>
  );
};

export default AssociationEvents;
