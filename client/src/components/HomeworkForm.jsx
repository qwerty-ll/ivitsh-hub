import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import Modal from './Modal';
import { homeworkApi } from '../services/api';
import { fromLocalInput, toLocalInput } from '../utils/tasks';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

/** Adding or editing an entry in the group's homework: what is set, for which subject, by when. */
const NONE = [];

/** `preset` fills in the subject ("Записать ДЗ" from a lesson). */
const HomeworkForm = ({ open, onClose, onSaved, entry = null, preset = '', group = '', subjects = NONE }) => {
  const [form, setForm] = useState({ subject: '', text: '', due: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setError('');
    setForm(entry
      ? { subject: entry.subject, text: entry.text, due: toLocalInput(entry.due_at) }
      : { subject: preset, text: '', due: '' });
  }, [open, entry, preset]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.text.trim()) { setError('Напишите, что задано'); return; }
    setSaving(true);
    setError('');
    const data = { subject: form.subject.trim(), text: form.text.trim(), due_at: fromLocalInput(form.due) };
    try {
      onSaved(entry ? await homeworkApi.edit(entry.id, data) : await homeworkApi.create(data));
    } catch (err) {
      setError(err.message || 'Не удалось сохранить');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={entry ? 'Изменить запись' : 'ДЗ для группы'} titleId="homework-form-title" className="task-form-modal">
      {!entry && <p className="task-optional hw-form-note">Запись увидят все студенты группы {group} на портале.</p>}
      <form className="task-form" onSubmit={submit} noValidate>
        <div className="field">
          <label className="field-label" htmlFor="hw-subject">Предмет <span className="task-optional">(необязательно)</span></label>
          <input id="hw-subject" className="input" list="hw-subjects" maxLength={200} value={form.subject}
            onChange={e => setForm({ ...form, subject: e.target.value })} placeholder="Например: Базы данных" />
          <datalist id="hw-subjects">{subjects.map(s => <option key={s} value={s} />)}</datalist>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="hw-text">Что задано</label>
          <textarea id="hw-text" className="textarea" rows={4} maxLength={5000} autoFocus value={form.text}
            onChange={e => setForm({ ...form, text: e.target.value })} placeholder="Лабораторная 3, отчёт загрузить в СДО" />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="hw-due">Сдать до <span className="task-optional">(без срока — просто заметка)</span></label>
          <input id="hw-due" className="input" type="datetime-local" value={form.due} onChange={e => setForm({ ...form, due: e.target.value })} />
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="cm-form-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Отменить</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving && <Loader2 size={16} className="spin-icon" {...ICON} />}{entry ? 'Сохранить' : 'Добавить'}
          </button>
        </div>
      </form>
    </Modal>
  );
};

export default HomeworkForm;
