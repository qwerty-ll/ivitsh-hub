import React from 'react';
import { Link } from 'react-router-dom';
import { Clock, MapPin, Users, HandHeart, CheckCircle2 } from 'lucide-react';
import { ROLE_LABEL, eventWhen, isFull, organizerOf, seatsText } from '../utils/events';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

/** An event in a list: when, where, who organizes, seats taken, and my registration */
const EventCard = ({ e }) => (
  <li>
    <Link to={`/events/${e.id}`} className={`card event-card ${e.scope === 'institute' ? 'is-institute' : ''}`}>
      <span className="event-card-top">
        <span className={`badge ${e.scope === 'institute' ? 'badge-accent' : ''}`}>{e.scope === 'institute' ? 'Институт' : 'Объединение'}</span>
        {e.my_role && <span className="badge badge-success"><CheckCircle2 size={14} {...ICON} />{ROLE_LABEL[e.my_role]}</span>}
        {!e.my_role && isFull(e, 'participant') && <span className="badge badge-warning">Мест нет</span>}
      </span>
      <span className="event-card-title">{e.title}</span>
      <span className="event-card-meta">
        <span><Clock size={14} {...ICON} />{eventWhen(e)}</span>
        {e.place && <span><MapPin size={14} {...ICON} />{e.place}</span>}
      </span>
      <span className="event-card-foot">
        <span className="event-card-org">{organizerOf(e)}</span>
        <span className="event-card-seats tabular">
          <span title="Участники"><Users size={14} {...ICON} />{seatsText(e.participants, e.participant_limit)}</span>
          {e.volunteer_limit !== null && <span title="Волонтёры"><HandHeart size={14} {...ICON} />{seatsText(e.volunteers, e.volunteer_limit)}</span>}
        </span>
      </span>
    </Link>
  </li>
);

export default EventCard;
