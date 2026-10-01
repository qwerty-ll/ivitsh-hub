import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Clock, MapPin, Pencil, Trash2, Loader2, Handshake } from 'lucide-react';
import Modal from './Modal';
import MeetingForm from './MeetingForm';
import { useToast } from '../context/ToastContext';
import { meetingsApi } from '../services/api';
import { dayTitle, dayKey, timeLabel } from '../utils/calendar';
import Avatar from './Avatar';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

export const meetingWhen = (m) => `${dayTitle(dayKey(new Date(m.starts_at)), { weekday: 'long' })}, ${timeLabel(m.starts_at)}–${timeLabel(m.ends_at)}`;

/** Leaders tick who came, once the meeting has started */
const Attendance = ({ meeting, onSaved }) => {
  const toast = useToast();
  const [present, setPresent] = useState(() => new Set(meeting.attendance.filter(a => a.present).map(a => a.user_id)));
  const [saving, setSaving] = useState(false);
  const toggle = (id) => setPresent(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const save = async () => {
    setSaving(true);
    try {
      onSaved(await meetingsApi.attendance(meeting.id, [...present]));
      toast.show('Присутствие сохранено', 'success');
    } catch (e) {
      toast.show(e.message || 'Не удалось сохранить', 'error');
    } finally {
      setSaving(false);
    }
  };
  if (!meeting.attendance.length) return <p className="task-optional">В объединении пока нет участников.</p>;
  return (
    <div className="meeting-attendance">
      <ul className="task-people">
        {meeting.attendance.map(a => (
          <li key={a.user_id}>
            <label className="task-person">
              <input type="checkbox" checked={present.has(a.user_id)} onChange={() => toggle(a.user_id)} />
              <span className="with-avatar"><Avatar name={a.full_name} url={a.photo_url} size="xs" />{a.full_name}</span>
              {a.group_number && <span className="task-optional tabular">{a.group_number}</span>}
            </label>
          </li>
        ))}
      </ul>
      <button type="button" className="btn btn-secondary btn-sm" onClick={save} disabled={saving}>
        {saving && <Loader2 size={16} className="spin-icon" {...ICON} />}Сохранить: были {present.size} из {meeting.attendance.length}
      </button>
    </div>
  );
};

/** A meeting's card: when, where, what about; for leaders editing, deleting and attendance. */
const MeetingDialog = ({ meetingId, onClose, onChanged }) => {
  const toast = useToast();
  const [meeting, setMeeting] = useState(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    setMeeting(null);
    setError('');
    if (meetingId) meetingsApi.get(meetingId).then(setMeeting).catch(e => setError(e.message || 'Собрание не найдено'));
  }, [meetingId]);

  const changed = useCallback((m) => { setMeeting(m); onChanged?.(); }, [onChanged]);

  const remove = async () => {
    if (!window.confirm('Отменить собрание? Оно пропадёт из календаря участников.')) return;
    try {
      await meetingsApi.remove(meeting.id);
      toast.show('Собрание отменено', 'success');
      onChanged?.();
      onClose();
    } catch (e) {
      toast.show(e.message || 'Не удалось отменить', 'error');
    }
  };

  const started = meeting && new Date(meeting.starts_at) <= new Date();

  return (
    <>
      <Modal open={!!meetingId && !editing} onClose={onClose} title={meeting?.title || 'Собрание'} titleId="meeting-dialog-title" className="cal-dialog">
        {error && <p className="field-error" role="alert">{error}</p>}
        {!meeting && !error && <span className="skeleton" style={{ height: '6rem' }} />}
        {meeting && (
          <div className="cal-dialog-body">
            <ul className="cal-facts">
              <li><Clock size={16} {...ICON} />{meetingWhen(meeting)}</li>
              {meeting.place && <li><MapPin size={16} {...ICON} />{meeting.place}</li>}
              <li className="hue-olive"><Handshake size={16} {...ICON} />
                <Link to={`/associations/${meeting.association.id}`} onClick={onClose}>{meeting.association.name}</Link>
              </li>
            </ul>
            {meeting.agenda && <p className="cal-text">{meeting.agenda}</p>}
            {meeting.summary && (
              <section>
                <h3 className="cal-subhead">Итоги встречи</h3>
                <p className="cal-text">{meeting.summary}</p>
              </section>
            )}
            {meeting.can_manage && started && (
              <section>
                <h3 className="cal-subhead">Кто был</h3>
                <Attendance key={meeting.id} meeting={meeting} onSaved={changed} />
              </section>
            )}
            {meeting.can_manage && (
              <div className="cal-dialog-actions">
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
                  <Pencil size={16} {...ICON} />{started && !meeting.summary ? 'Записать итоги' : 'Изменить'}
                </button>
                <button type="button" className="btn btn-ghost btn-sm cal-danger" onClick={remove}>
                  <Trash2 size={16} {...ICON} />Отменить собрание
                </button>
              </div>
            )}
          </div>
        )}
      </Modal>
      <MeetingForm
        open={editing}
        meeting={meeting}
        onClose={() => setEditing(false)}
        onSaved={(m) => { setEditing(false); changed(m); toast.show('Собрание сохранено', 'success'); }}
      />
    </>
  );
};

export default MeetingDialog;
