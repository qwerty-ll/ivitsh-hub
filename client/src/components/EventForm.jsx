import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import Modal from './Modal';
import { useAuth } from '../context/AuthContext';
import { associationsApi, eventsApi } from '../services/api';
import { fromLocalInput, toLocalInput } from '../utils/tasks';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

const blank = (associationId) => ({
  title: '', description: '', place: '',
  scope: associationId ? 'association' : '', association: associationId ? String(associationId) : '',
  starts: '', ends: '', limit: '', volunteers: false, volunteerLimit: '5', open: true,
});

/**
 * Creating or editing an event. Leaders make events of their associations; administrators also
 * make institute events (optionally naming an organizing association).
 */
const EventForm = ({ open, onClose, onSaved, event = null, presetAssociation = null }) => {
  const { isAdmin } = useAuth();
  const [form, setForm] = useState(blank());
  const [associations, setAssociations] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setError('');
    if (event) {
      setForm({
        title: event.title, description: event.description, place: event.place,
        scope: event.scope, association: event.association ? String(event.association.id) : '',
        starts: toLocalInput(event.starts_at), ends: toLocalInput(event.ends_at),
        limit: event.participant_limit ? String(event.participant_limit) : '',
        volunteers: event.volunteer_limit !== null, volunteerLimit: String(event.volunteer_limit || 5),
        open: event.registration_open,
      });
    } else {
      const next = blank(presetAssociation);
      if (!presetAssociation && isAdmin) next.scope = 'institute';
      setForm(next);
    }
    // Administrators pick any association; a leader only the ones they lead
    const load = isAdmin
      ? associationsApi.list().then(rows => (rows || []).map(a => ({ id: a.id, name: a.name })))
      : associationsApi.mine().then(rows => (rows || []).filter(r => r.role === 'leader' && r.status === 'approved')
        .map(r => ({ id: r.association_id, name: r.association_name })));
    load.then((list) => {
      setAssociations(list);
      if (!event && !presetAssociation && !isAdmin && list.length) {
        setForm(f => ({ ...f, scope: 'association', association: String(list[0].id) }));
      }
    }).catch(() => setAssociations([]));
  }, [open, event, presetAssociation, isAdmin]);

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const lockedOwner = !!event && !isAdmin;

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) { setError('Введите название'); return; }
    if (!form.starts || !form.ends) { setError('Укажите начало и конец'); return; }
    if (new Date(form.ends) <= new Date(form.starts)) { setError('Мероприятие должно заканчиваться позже, чем начинается'); return; }
    if (form.scope === 'association' && !form.association) { setError('Выберите объединение'); return; }
    setSaving(true);
    setError('');
    const data = {
      title: form.title.trim(),
      description: form.description.trim(),
      place: form.place.trim(),
      scope: form.scope || 'association',
      association_id: form.association ? Number(form.association) : null,
      starts_at: fromLocalInput(form.starts),
      ends_at: fromLocalInput(form.ends),
      participant_limit: form.limit ? Number(form.limit) : null,
      volunteer_limit: form.volunteers ? Number(form.volunteerLimit) || 1 : null,
      registration_open: form.open,
    };
    try {
      onSaved(event ? await eventsApi.edit(event.id, data) : await eventsApi.create(data));
    } catch (err) {
      setError(err.message || 'Не удалось сохранить мероприятие');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={event ? 'Изменить мероприятие' : 'Новое мероприятие'} titleId="event-form-title" className="task-form-modal">
      <form className="task-form" onSubmit={submit} noValidate>
        {isAdmin && (
          <fieldset className="field">
            <legend className="field-label">Уровень</legend>
            <div className="segmented" role="group" aria-label="Уровень мероприятия">
              <button type="button" className={`segmented-item ${form.scope === 'institute' ? 'active' : ''}`} aria-pressed={form.scope === 'institute'}
                onClick={() => setForm(f => ({ ...f, scope: 'institute' }))}>Институт — видят все</button>
              <button type="button" className={`segmented-item ${form.scope === 'association' ? 'active' : ''}`} aria-pressed={form.scope === 'association'}
                onClick={() => setForm(f => ({ ...f, scope: 'association' }))}>Объединение — видят участники</button>
            </div>
          </fieldset>
        )}
        {(isAdmin || associations.length > 1) && !lockedOwner && (
          <div className="field">
            <label className="field-label" htmlFor="event-association">
              {form.scope === 'institute' ? <>Организатор <span className="task-optional">(необязательно)</span></> : 'Объединение'}
            </label>
            <select id="event-association" className="select" value={form.association} onChange={set('association')}>
              {form.scope === 'institute' ? <option value="">Администрация ИВИТШ</option> : <option value="">Выберите…</option>}
              {associations.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
        )}
        <div className="field">
          <label className="field-label" htmlFor="event-title">Название</label>
          <input id="event-title" className="input" maxLength={200} autoFocus value={form.title} onChange={set('title')}
            placeholder="Например: Посвящение в студенты" />
        </div>
        <div className="meeting-when event-when">
          <div className="field">
            <label className="field-label" htmlFor="event-starts">Начало</label>
            <input id="event-starts" className="input" type="datetime-local" value={form.starts}
              onChange={(e) => {
                const starts = e.target.value;
                // A fresh event lasts two hours unless told otherwise
                setForm(f => ({ ...f, starts, ends: f.ends || (starts ? toLocalInput(new Date(new Date(starts).getTime() + 2 * 3600e3).toISOString()) : '') }));
              }} />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="event-ends">Конец</label>
            <input id="event-ends" className="input" type="datetime-local" value={form.ends} onChange={set('ends')} />
          </div>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="event-place">Место</label>
          <input id="event-place" className="input" maxLength={200} value={form.place} onChange={set('place')} placeholder="Актовый зал, корпус Б" />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="event-desc">Описание <span className="task-optional">(необязательно)</span></label>
          <textarea id="event-desc" className="textarea" rows={4} maxLength={10000} value={form.description} onChange={set('description')} />
        </div>
        <div className="meeting-when event-when">
          <div className="field">
            <label className="field-label" htmlFor="event-limit">Мест для участников</label>
            <input id="event-limit" className="input" type="number" min={1} max={10000} inputMode="numeric" value={form.limit}
              onChange={set('limit')} placeholder="Без ограничений" />
          </div>
          <div className="field">
            <label className="task-person event-check">
              <input type="checkbox" checked={form.volunteers} onChange={set('volunteers')} />
              <span>Нужны волонтёры</span>
            </label>
            {form.volunteers && (
              <>
                <label className="visually-hidden" htmlFor="event-vlimit">Сколько волонтёров</label>
                <input id="event-vlimit" className="input" type="number" min={1} max={1000} inputMode="numeric"
                  value={form.volunteerLimit} onChange={set('volunteerLimit')} />
              </>
            )}
          </div>
        </div>
        <label className="task-person">
          <input type="checkbox" checked={form.open} onChange={set('open')} />
          <span>Студенты могут записаться сами</span>
        </label>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="cm-form-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Отменить</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving && <Loader2 size={16} className="spin-icon" {...ICON} />}{event ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </form>
    </Modal>
  );
};

export default EventForm;
