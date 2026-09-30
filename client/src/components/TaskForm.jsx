import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Loader2 } from 'lucide-react';
import { associationsApi, tasksApi } from '../services/api';
import { COLORS, fromLocalInput } from '../utils/tasks';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const EASE = [0.2, 0, 0, 1];
const EMPTY = { title: '', description: '', due: '', owner: 'personal', color: 'blue', toAll: true, assignees: [] };

/**
 * "Новая задача": a personal task with a color, or — for a leader — a task of their association
 * for everyone in it or for chosen members. `presetAssociation` opens it on that association.
 */
const TaskForm = ({ open, onClose, onCreated, presetAssociation = null }) => {
  const [form, setForm] = useState(EMPTY);
  const [led, setLed] = useState([]);
  const [members, setMembers] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setForm({ ...EMPTY, owner: presetAssociation ? String(presetAssociation) : 'personal' });
    setError('');
    associationsApi.mine()
      .then(rows => setLed((rows || []).filter(r => r.role === 'leader' && r.status === 'approved')))
      .catch(() => setLed([]));
  }, [open, presetAssociation]);

  // The chosen association's members, for "выбрать участников"
  useEffect(() => {
    setMembers(null);
    if (!open || form.owner === 'personal') return;
    associationsApi.get(form.owner)
      .then(res => setMembers((res.members || []).filter(m => m.role === 'member')))
      .catch(() => setMembers([]));
  }, [open, form.owner]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const personal = form.owner === 'personal';
  const toggleAssignee = (id) => setForm(f => ({
    ...f, assignees: f.assignees.includes(id) ? f.assignees.filter(x => x !== id) : [...f.assignees, id],
  }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) { setError('Введите название задачи'); return; }
    if (!personal && !form.toAll && form.assignees.length === 0) { setError('Отметьте, кому поставить задачу'); return; }
    setSaving(true);
    setError('');
    try {
      const task = await tasksApi.create({
        title: form.title.trim(),
        description: form.description.trim(),
        due_at: fromLocalInput(form.due),
        ...(personal
          ? { color: form.color }
          : { association_id: Number(form.owner), to_all: form.toAll, assignee_ids: form.toAll ? [] : form.assignees }),
      });
      onCreated(task);
    } catch (err) {
      setError(err.message || 'Не удалось создать задачу');
    } finally {
      setSaving(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="modal-overlay" onClick={onClose}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2, ease: EASE }}>
          <motion.div className="modal task-form-modal" role="dialog" aria-modal="true" aria-labelledby="task-form-title"
            onClick={e => e.stopPropagation()}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} transition={{ duration: 0.24, ease: EASE }}>
            <button type="button" className="modal-close" onClick={onClose} aria-label="Закрыть окно"><X size={20} {...ICON} /></button>
            <h2 id="task-form-title">Новая задача</h2>

            <form className="task-form" onSubmit={submit} noValidate>
              {led.length > 0 && (
                <div className="field">
                  <label className="field-label" htmlFor="task-owner">Для кого</label>
                  <select id="task-owner" className="select" value={form.owner}
                    onChange={e => setForm({ ...form, owner: e.target.value, assignees: [] })}>
                    <option value="personal">Лично мне</option>
                    {led.map(a => <option key={a.association_id} value={a.association_id}>Объединение «{a.association_name}»</option>)}
                  </select>
                </div>
              )}

              <div className="field">
                <label className="field-label" htmlFor="task-title">Что сделать</label>
                <input id="task-title" className="input" maxLength={200} autoFocus value={form.title}
                  onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Например: смонтировать ролик" />
              </div>

              <div className="field">
                <label className="field-label" htmlFor="task-desc">Подробности <span className="task-optional">(необязательно)</span></label>
                <textarea id="task-desc" className="textarea" rows={3} maxLength={5000} value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })} />
              </div>

              <div className="field">
                <label className="field-label" htmlFor="task-due">Дедлайн <span className="task-optional">(необязательно)</span></label>
                <input id="task-due" className="input" type="datetime-local" value={form.due}
                  onChange={e => setForm({ ...form, due: e.target.value })} />
              </div>

              {personal ? (
                <fieldset className="field task-colors">
                  <legend className="field-label">Цвет</legend>
                  <div className="task-swatches">
                    {COLORS.map(c => (
                      <label key={c.id} className={`task-swatch hue-${c.id}`} title={c.label}>
                        <input type="radio" name="task-color" value={c.id} checked={form.color === c.id}
                          onChange={() => setForm({ ...form, color: c.id })} className="visually-hidden" />
                        <span className="task-swatch-dot" aria-hidden="true" />
                        <span className="visually-hidden">{c.label}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              ) : (
                <fieldset className="field">
                  <legend className="field-label">Исполнители</legend>
                  <div className="segmented" role="group" aria-label="Кому поставить">
                    <button type="button" className={`segmented-item ${form.toAll ? 'active' : ''}`} aria-pressed={form.toAll}
                      onClick={() => setForm({ ...form, toAll: true })}>Всему объединению</button>
                    <button type="button" className={`segmented-item ${!form.toAll ? 'active' : ''}`} aria-pressed={!form.toAll}
                      onClick={() => setForm({ ...form, toAll: false })}>Выбрать участников</button>
                  </div>
                  {members === null ? <p className="task-optional">Загружаем участников…</p>
                    : members.length === 0 ? <p className="task-optional">В объединении пока нет участников: примите заявки на странице объединения.</p>
                      : form.toAll ? <p className="task-optional">Задача появится у всех участников ({members.length}). Кто вступит позже, её не получит.</p>
                        : (
                          <ul className="task-people">
                            {members.map(m => (
                              <li key={m.user_id}>
                                <label className="task-person">
                                  <input type="checkbox" checked={form.assignees.includes(m.user_id)} onChange={() => toggleAssignee(m.user_id)} />
                                  <span>{m.full_name}</span>
                                  {m.group_number && <span className="task-optional tabular">{m.group_number}</span>}
                                </label>
                              </li>
                            ))}
                          </ul>
                        )}
                </fieldset>
              )}

              {error && <p className="field-error" role="alert">{error}</p>}
              <div className="cm-form-actions">
                <button type="button" className="btn btn-ghost" onClick={onClose}>Отменить</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving && <Loader2 size={16} className="spin-icon" {...ICON} />}Создать задачу
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default TaskForm;
