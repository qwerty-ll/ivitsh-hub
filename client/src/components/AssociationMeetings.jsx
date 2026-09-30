import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarPlus, ChevronDown, MapPin, Users } from 'lucide-react';
import MeetingDialog, { meetingWhen } from './MeetingDialog';
import MeetingForm from './MeetingForm';
import { useToast } from '../context/ToastContext';
import { meetingsApi } from '../services/api';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

const Row = ({ m, onOpen }) => (
  <li>
    <button type="button" className="meeting-row" onClick={() => onOpen(m.id)}>
      <span className="meeting-row-title">{m.title}</span>
      <span className="assoc-person-meta">
        <span className="tabular">{meetingWhen(m)}</span>
        {m.place && <span><MapPin size={14} {...ICON} />{m.place}</span>}
        {m.attended_count !== null && <span><Users size={14} {...ICON} />были: {m.attended_count}</span>}
      </span>
      {m.summary && <span className="meeting-row-summary">{m.summary}</span>}
    </button>
  </li>
);

/** Meetings of an association: upcoming ones for members, setting them and the past ones' attendance for leaders. */
const AssociationMeetings = ({ associationId, associationName, canManage }) => {
  const toast = useToast();
  const [upcoming, setUpcoming] = useState(null);
  const [past, setPast] = useState(null);
  const [showPast, setShowPast] = useState(false);
  const [openId, setOpenId] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const self = useMemo(() => [{ id: associationId, name: associationName }], [associationId, associationName]);

  const load = useCallback(() => {
    meetingsApi.list(associationId).then(r => setUpcoming(r || [])).catch(() => setUpcoming([]));
    if (showPast) meetingsApi.list(associationId, true).then(r => setPast(r || [])).catch(() => setPast([]));
  }, [associationId, showPast]);
  useEffect(load, [load]);

  if (upcoming === null) return null;

  return (
    <section className="card assoc-card-block" aria-labelledby="assoc-meetings">
      <div className="assoc-manage-head">
        <h2 id="assoc-meetings">Собрания</h2>
        {canManage && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setFormOpen(true)}>
            <CalendarPlus size={16} {...ICON} />Назначить
          </button>
        )}
      </div>
      {upcoming.length === 0 ? (
        <p className="assoc-muted">
          {canManage ? 'Назначьте собрание — время и место появятся в календаре у всех участников.' : 'Ближайших собраний нет.'}
        </p>
      ) : (
        <ul className="list meeting-list">{upcoming.map(m => <Row key={m.id} m={m} onOpen={setOpenId} />)}</ul>
      )}

      <button type="button" className="btn btn-ghost btn-sm meeting-past-toggle" aria-expanded={showPast} onClick={() => setShowPast(v => !v)}>
        {showPast ? 'Скрыть прошедшие' : 'Прошедшие собрания'}
        <ChevronDown size={16} className="dash-chevron" {...ICON} />
      </button>
      {showPast && past !== null && (past.length === 0
        ? <p className="assoc-muted">Прошедших собраний нет.</p>
        : <ul className="list meeting-list">{past.map(m => <Row key={m.id} m={m} onOpen={setOpenId} />)}</ul>)}

      <MeetingDialog meetingId={openId} onClose={() => setOpenId(null)} onChanged={load} />
      <MeetingForm
        open={formOpen}
        associations={self}
        onClose={() => setFormOpen(false)}
        onSaved={() => { setFormOpen(false); toast.show('Собрание назначено — участники увидят его в календаре', 'success'); load(); }}
      />
    </section>
  );
};

export default AssociationMeetings;
