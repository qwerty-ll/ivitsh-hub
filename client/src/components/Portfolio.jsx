import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileSpreadsheet, FileText, Plus, Pencil, Trash2, Loader2 } from 'lucide-react';
import Modal from './Modal';
import Attachments from './Attachments';
import { useToast } from '../context/ToastContext';
import { achievementsApi, attachmentsApi } from '../services/api';
import { semesters } from '../utils/events';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const EMPTY = { title: '', organizer: '', day: '', role: 'Участник', description: '' };

const AchievementForm = ({ entry, open, onClose, onSaved }) => {
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!open) return;
    setError('');
    setForm(entry ? { title: entry.title, organizer: entry.organizer, day: entry.day, role: entry.role, description: entry.description } : EMPTY);
  }, [open, entry]);
  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title.trim() || !form.day) { setError('Укажите название и дату'); return; }
    setSaving(true);
    setError('');
    try {
      const data = { ...form, title: form.title.trim() };
      onSaved(entry ? await achievementsApi.edit(entry.id, data) : await achievementsApi.create(data), !entry);
    } catch (err) {
      setError(err.message || 'Не удалось сохранить');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={entry ? 'Изменить запись' : 'Мероприятие не с портала'} titleId="ach-form-title" className="task-form-modal">
      {!entry && <p className="task-optional hw-form-note">Если мероприятия не было на портале, внесите его сами. Скан распоряжения или грамоты можно прикрепить сразу после сохранения или позже.</p>}
      <form className="task-form" onSubmit={submit} noValidate>
        <div className="field">
          <label className="field-label" htmlFor="ach-title">Мероприятие</label>
          <input id="ach-title" className="input" maxLength={300} autoFocus value={form.title} onChange={set('title')}
            placeholder="Например: Региональная олимпиада по программированию" />
        </div>
        <div className="meeting-when event-when">
          <div className="field">
            <label className="field-label" htmlFor="ach-day">Дата</label>
            <input id="ach-day" className="input" type="date" value={form.day} onChange={set('day')} />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="ach-role">Роль или результат</label>
            <input id="ach-role" className="input" list="ach-roles" maxLength={100} value={form.role} onChange={set('role')} />
            <datalist id="ach-roles">
              {['Участник', 'Волонтёр', 'Организатор', 'Призёр', 'Победитель'].map(r => <option key={r} value={r} />)}
            </datalist>
          </div>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="ach-org">Организатор</label>
          <input id="ach-org" className="input" maxLength={300} value={form.organizer} onChange={set('organizer')} placeholder="КГУ, департамент образования…" />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="ach-desc">Комментарий <span className="task-optional">(необязательно)</span></label>
          <textarea id="ach-desc" className="textarea" rows={2} maxLength={5000} value={form.description} onChange={set('description')} />
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="cm-form-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Отменить</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving && <Loader2 size={16} className="spin-icon" {...ICON} />}Сохранить
          </button>
        </div>
      </form>
    </Modal>
  );
};

/** The ПГАС summary: events of the semester from the portal and ones added by hand, with Excel / Word export. */
const Portfolio = () => {
  const toast = useToast();
  const options = useMemo(() => semesters(), []);
  const [semester, setSemester] = useState(options[0]);
  const [data, setData] = useState(null);
  const [manual, setManual] = useState([]);
  const [form, setForm] = useState(null); // { entry } | {}

  const load = useCallback(() => {
    achievementsApi.portfolio(semester.start, semester.end).then(setData).catch(() => setData({ rows: [] }));
    achievementsApi.list().then(r => setManual(r || [])).catch(() => setManual([]));
  }, [semester]);
  useEffect(load, [load]);

  const byId = Object.fromEntries(manual.map(m => [m.id, m]));
  const remove = async (entry) => {
    if (!window.confirm(`Удалить «${entry.title}» вместе со сканом?`)) return;
    try {
      await achievementsApi.remove(entry.id);
      load();
    } catch (e) {
      toast.show(e.message || 'Не удалось удалить', 'error');
    }
  };

  return (
    <section className="pgas" aria-labelledby="pgas-title">
      <div className="pgas-head">
        <div>
          <h2 id="pgas-title">Сводка для ПГАС</h2>
          <p className="task-optional">Мероприятия, где вы участвовали, и внесённые вручную — со ссылками на распоряжения и грамоты.</p>
        </div>
        <div className="pgas-controls">
          <label className="visually-hidden" htmlFor="pgas-semester">Семестр</label>
          <select id="pgas-semester" className="select" value={semester.id} onChange={e => setSemester(options.find(o => o.id === e.target.value))}>
            {options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
          <a className="btn btn-secondary" href={achievementsApi.exportHref('xlsx', semester.start, semester.end)} download>
            <FileSpreadsheet size={16} {...ICON} />Excel
          </a>
          <a className="btn btn-secondary" href={achievementsApi.exportHref('docx', semester.start, semester.end)} download>
            <FileText size={16} {...ICON} />Word
          </a>
        </div>
      </div>

      {data === null ? <span className="skeleton" style={{ height: '8rem' }} /> : data.rows.length === 0 ? (
        <p className="cal-empty">За этот семестр мероприятий нет. Запишитесь на мероприятие или внесите то, что было не на портале.</p>
      ) : (
        <ol className="pgas-list">
          {data.rows.map((r) => {
            const entry = r.kind === 'manual' ? byId[r.id] : null;
            return (
              <li key={`${r.kind}-${r.id}`} className="card pgas-row">
                <div className="pgas-row-main">
                  <span className="pgas-date tabular">{new Date(`${r.day}T00:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                  {r.kind === 'event' ? <Link to={`/events/${r.id}`} className="pgas-title">{r.title}</Link> : <span className="pgas-title">{r.title}</span>}
                  <span className="assoc-person-meta">
                    <span>{r.organizer}</span><span>{r.level}</span><span className="badge">{r.role}</span>
                  </span>
                </div>
                {r.kind === 'event' ? (
                  r.documents.length > 0 && (
                    <ul className="attach-list">
                      {r.documents.map(d => (
                        <li key={d.id} className="attach-item">
                          <a className="attach-link" href={attachmentsApi.href(d.id)} download><FileText size={18} {...ICON} /><span className="attach-name">{d.title}</span></a>
                        </li>
                      ))}
                    </ul>
                  )
                ) : entry && (
                  <>
                    <Attachments owner="achievements" ownerId={entry.id} items={entry.attachments} canAdd links={false}
                      hint="Скан распоряжения, грамоты или сертификата: PDF или фото, до 10 МБ." onChange={load} />
                    <div className="pgas-row-actions">
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setForm({ entry })}><Pencil size={16} {...ICON} />Изменить</button>
                      <button type="button" className="btn btn-ghost btn-sm cal-danger" onClick={() => remove(entry)}><Trash2 size={16} {...ICON} />Удалить</button>
                    </div>
                  </>
                )}
              </li>
            );
          })}
        </ol>
      )}
      <button type="button" className="btn btn-secondary" onClick={() => setForm({})}><Plus size={16} {...ICON} />Внести мероприятие вручную</button>

      <AchievementForm
        open={!!form}
        entry={form?.entry || null}
        onClose={() => setForm(null)}
        onSaved={(saved, created) => {
          setForm(null);
          toast.show(created ? 'Сохранено. Прикрепите скан в карточке записи.' : 'Сохранено', 'success', 4000);
          // A date outside the chosen semester: switch to the one it belongs to
          const fits = options.find(o => saved.day >= o.start && saved.day <= o.end);
          if (fits && fits.id !== semester.id) setSemester(fits); else load();
        }}
      />
    </section>
  );
};

export default Portfolio;
