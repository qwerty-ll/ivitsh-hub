import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import Modal from './Modal';
import { meetingsApi } from '../services/api';
import { dayKey, joinDateTime, splitDateTime } from '../utils/calendar';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

const blank = (associationId) => ({
  association: associationId ? String(associationId) : '',
  title: 'Собрание',
  date: dayKey(new Date()),
  start: '18:00',
  end: '19:00',
  place: '',
  agenda: '',
  summary: '',
});

/**
 * Setting or editing a meeting. `associations` are the ones the user leads ({ id, name });
 * with one of them or with `meeting` given, the choice is not shown.
 */
const NONE = [];

const MeetingForm = ({ open, onClose, onSaved, associations = NONE, meeting = null }) => {
  const [form, setForm] = useState(blank());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setError('');
    if (meeting) {
      const s = splitDateTime(meeting.starts_at);
      const e = splitDateTime(meeting.ends_at);
      setForm({
        association: String(meeting.association.id), title: meeting.title, date: s.date, start: s.time, end: e.time,
        place: meeting.place, agenda: meeting.agenda, summary: meeting.summary,
      });
    } else {
      setForm(blank(associations.length === 1 ? associations[0].id : ''));
    }
  }, [open, meeting, associations]);

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));
  const past = meeting && new Date(meeting.starts_at) < new Date();

  const submit = async (e) => {
    e.preventDefault();
    if (!form.association) { setError('Выберите объединение'); return; }
    if (!form.date || !form.start || !form.end) { setError('Укажите дату и время'); return; }
    if (form.end <= form.start) { setError('Собрание должно заканчиваться позже, чем начинается'); return; }
    setSaving(true);
    setError('');
    const data = {
      title: form.title.trim() || 'Собрание',
      starts_at: joinDateTime(form.date, form.start),
      ends_at: joinDateTime(form.date, form.end),
      place: form.place.trim(),
      agenda: form.agenda.trim(),
      summary: form.summary.trim(),
    };
    try {
      const saved = meeting ? await meetingsApi.edit(meeting.id, data) : await meetingsApi.create(form.association, data);
      onSaved(saved);
    } catch (err) {
      setError(err.message || 'Не удалось сохранить собрание');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={meeting ? 'Собрание' : 'Назначить собрание'} titleId="meeting-form-title" className="task-form-modal">
      <form className="task-form" onSubmit={submit} noValidate>
        {!meeting && associations.length > 1 && (
          <div className="field">
            <label className="field-label" htmlFor="meeting-association">Объединение</label>
            <select id="meeting-association" className="select" value={form.association} onChange={set('association')}>
              <option value="">Выберите…</option>
              {associations.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
        )}
        <div className="field">
          <label className="field-label" htmlFor="meeting-title">Название</label>
          <input id="meeting-title" className="input" maxLength={200} value={form.title} onChange={set('title')} />
        </div>
        <div className="meeting-when">
          <div className="field">
            <label className="field-label" htmlFor="meeting-date">Дата</label>
            <input id="meeting-date" className="input" type="date" value={form.date} onChange={set('date')} />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="meeting-start">Начало</label>
            <input id="meeting-start" className="input" type="time" value={form.start} onChange={set('start')} />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="meeting-end">Конец</label>
            <input id="meeting-end" className="input" type="time" value={form.end} onChange={set('end')} />
          </div>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="meeting-place">Место</label>
          <input id="meeting-place" className="input" maxLength={200} value={form.place} onChange={set('place')}
            placeholder="Например: Б-108 или ссылка на звонок" />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="meeting-agenda">О чём <span className="task-optional">(необязательно)</span></label>
          <textarea id="meeting-agenda" className="textarea" rows={3} maxLength={5000} value={form.agenda} onChange={set('agenda')} />
        </div>
        {past && (
          <div className="field">
            <label className="field-label" htmlFor="meeting-summary">Итоги встречи</label>
            <textarea id="meeting-summary" className="textarea" rows={3} maxLength={5000} value={form.summary} onChange={set('summary')}
              placeholder="Что решили, кто за что отвечает" />
          </div>
        )}
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="cm-form-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Отменить</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving && <Loader2 size={16} className="spin-icon" {...ICON} />}{meeting ? 'Сохранить' : 'Назначить'}
          </button>
        </div>
      </form>
    </Modal>
  );
};

export default MeetingForm;
