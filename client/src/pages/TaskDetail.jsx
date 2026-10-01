import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CalendarClock, Pencil, Trash2, Send, UserPlus, X, Check, Undo2, Loader2 } from 'lucide-react';
import Attachments from '../components/Attachments';
import ContactLinks from '../components/ContactLinks';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { associationsApi, tasksApi } from '../services/api';
import { COLORS, STATUSES, STATUS_LABEL, dueInfo, fromLocalInput, toLocalInput } from '../utils/tasks';
import Avatar from '../components/Avatar';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const when = (iso) => (iso ? new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }) : '');

// "Сдано вовремя" / "Сдано с опозданием" against the deadline
const handedInNote = (a, dueAt) => {
  if (!a.completed_at) return null;
  const late = dueAt && new Date(a.completed_at) > new Date(dueAt);
  return { text: `${late ? 'Сдано с опозданием' : 'Сдано'} ${when(a.completed_at)}`, late };
};

const EditForm = ({ task, onSaved, onCancel }) => {
  const toast = useToast();
  const [form, setForm] = useState({
    title: task.title, description: task.description, due: toLocalInput(task.due_at), color: task.color || 'blue',
  });
  const [saving, setSaving] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await tasksApi.edit(task.id, {
        title: form.title, description: form.description, due_at: fromLocalInput(form.due),
        ...(task.association ? {} : { color: form.color }),
      });
      onSaved(updated);
    } catch (err) {
      toast.show(err.message || 'Не удалось сохранить', 'error');
    } finally {
      setSaving(false);
    }
  };
  return (
    <form className="card task-block task-form" onSubmit={save}>
      <div className="field">
        <label className="field-label" htmlFor="edit-title">Название</label>
        <input id="edit-title" className="input" maxLength={200} required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
      </div>
      <div className="field">
        <label className="field-label" htmlFor="edit-desc">Подробности</label>
        <textarea id="edit-desc" className="textarea" rows={4} maxLength={5000} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
      </div>
      <div className="field">
        <label className="field-label" htmlFor="edit-due">Дедлайн</label>
        <input id="edit-due" className="input" type="datetime-local" value={form.due} onChange={e => setForm({ ...form, due: e.target.value })} />
      </div>
      {!task.association && (
        <fieldset className="field task-colors">
          <legend className="field-label">Цвет</legend>
          <div className="task-swatches">
            {COLORS.map(c => (
              <label key={c.id} className={`task-swatch hue-${c.id}`} title={c.label}>
                <input type="radio" name="edit-color" value={c.id} checked={form.color === c.id} onChange={() => setForm({ ...form, color: c.id })} className="visually-hidden" />
                <span className="task-swatch-dot" aria-hidden="true" />
                <span className="visually-hidden">{c.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <div className="cm-form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Отменить</button>
        <button type="submit" className="btn btn-primary" disabled={saving}>{saving && <Loader2 size={16} className="spin-icon" {...ICON} />}Сохранить</button>
      </div>
    </form>
  );
};

const TaskDetail = () => {
  const { id } = useParams();
  const { isLoggedIn, user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [task, setTask] = useState(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [comment, setComment] = useState('');
  const [sending, setSending] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [candidates, setCandidates] = useState(null);
  const [picked, setPicked] = useState([]);

  const load = useCallback(() => {
    tasksApi.get(id).then(setTask).catch(e => setError(e.status === 404 ? 'Задача не найдена или недоступна вам.' : (e.message || 'Не удалось загрузить задачу')));
  }, [id]);
  useEffect(() => { if (isLoggedIn) load(); }, [load, isLoggedIn]);

  if (!isLoggedIn) {
    return (
      <div className="container tasks-page">
        <div className="empty-state">
          <h1 className="cm-empty-title">Задачи видны после входа</h1>
          <Link to="/profile" className="btn btn-primary">Войти через ЭИОС</Link>
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="container tasks-page">
        <Link to="/tasks" className="assoc-back"><ArrowLeft size={16} {...ICON} />Все задачи</Link>
        <div className="empty-state" role="alert"><h1 className="cm-empty-title">{error}</h1></div>
      </div>
    );
  }
  if (!task) {
    return (
      <div className="container tasks-page" aria-busy="true">
        <span className="skeleton" style={{ width: '50%', height: '2.25rem' }} />
        <span className="skeleton" style={{ width: '100%', height: '10rem', marginTop: 'var(--space-6)' }} />
      </div>
    );
  }

  const due = dueInfo(task.due_at, task.my_status || (task.assignees.every(a => a.status === 'done') ? 'done' : 'todo'));
  const isAssociation = !!task.association;
  const leaderView = task.can_manage && isAssociation;

  const setStatus = async (status, userId = null) => {
    try {
      await tasksApi.setStatus(task.id, status, userId);
      if (!userId && status === 'review') toast.show('Отправлено на проверку', 'success');
      load();
    } catch (e) {
      toast.show(e.message || 'Не удалось изменить статус', 'error');
    }
  };

  const remove = async () => {
    if (!window.confirm(`Удалить задачу «${task.title}»${isAssociation ? ' у всех исполнителей' : ''}? Комментарии и файлы удалятся тоже.`)) return;
    try {
      await tasksApi.remove(task.id);
      toast.show('Задача удалена', 'success');
      navigate(leaderView ? '/tasks?tab=managed' : '/tasks');
    } catch (e) {
      toast.show(e.message || 'Не удалось удалить', 'error');
    }
  };

  const sendComment = async (e) => {
    e.preventDefault();
    if (!comment.trim()) return;
    setSending(true);
    try {
      await tasksApi.comment(task.id, comment.trim());
      setComment('');
      load();
    } catch (err) {
      toast.show(err.message || 'Не удалось отправить', 'error');
    } finally {
      setSending(false);
    }
  };

  const openAdd = async () => {
    setAddOpen(true);
    setPicked([]);
    try {
      const assoc = await associationsApi.get(task.association.id);
      const have = new Set(task.assignees.map(a => a.user_id));
      setCandidates((assoc.members || []).filter(m => !have.has(m.user_id)));
    } catch {
      setCandidates([]);
    }
  };

  const addPeople = async () => {
    try {
      const updated = await tasksApi.edit(task.id, {
        title: task.title, description: task.description, due_at: task.due_at, add_assignee_ids: picked,
      });
      setTask(updated);
      setAddOpen(false);
      toast.show('Исполнители добавлены', 'success');
    } catch (e) {
      toast.show(e.message || 'Не удалось добавить', 'error');
    }
  };

  return (
    <div className="container tasks-page">
      <Link to={leaderView ? '/tasks?tab=managed' : '/tasks'} className="assoc-back"><ArrowLeft size={16} {...ICON} />Все задачи</Link>

      <header className={`task-head ${isAssociation ? '' : `hue-${task.color || 'blue'} task-head-personal`}`}>
        <div className="task-head-text">
          <h1>{task.title}</h1>
          <p className="task-card-meta">
            {isAssociation
              ? <Link to={`/associations/${task.association.id}`} className="task-chip task-chip-link">{task.association.name}</Link>
              : <span className="task-chip">Личная задача</span>}
            {due && <span className={`task-due task-due-${due.tone || 'plain'}`}><CalendarClock size={14} {...ICON} />{due.label}</span>}
            {isAssociation && task.created_by && <span className="task-optional">Поставил(а): {task.created_by}</span>}
          </p>
        </div>
        {task.can_manage && !editing && (
          <div className="task-head-actions">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}><Pencil size={16} {...ICON} />Изменить</button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={remove}><Trash2 size={16} {...ICON} />Удалить</button>
          </div>
        )}
      </header>

      <div className="assoc-layout">
        <div className="assoc-main">
          {editing ? (
            <EditForm task={task} onCancel={() => setEditing(false)} onSaved={(t) => { setTask(t); setEditing(false); toast.show('Сохранено', 'success'); }} />
          ) : (
            <section className="card task-block" aria-labelledby="task-about">
              <h2 id="task-about">Что нужно сделать</h2>
              {task.description ? <p className="assoc-description">{task.description}</p> : <p className="assoc-muted">Без подробностей.</p>}
            </section>
          )}

          {task.my_status && (
            <section className="card task-block" aria-labelledby="task-my-status">
              <h2 id="task-my-status">{isAssociation ? 'Мой статус' : 'Статус'}</h2>
              <div className="segmented task-status-seg" role="group" aria-label="Статус">
                {STATUSES.map(s => {
                  const locked = s.id === 'done' && isAssociation && !task.can_manage;
                  return (
                    <button key={s.id} type="button" disabled={locked && task.my_status !== 'done'}
                      className={`segmented-item ${task.my_status === s.id ? 'active' : ''}`}
                      aria-pressed={task.my_status === s.id} onClick={() => setStatus(s.id)}
                      title={locked ? '«Готово» ставит руководитель после проверки' : undefined}>
                      {s.label}
                    </button>
                  );
                })}
              </div>
              {isAssociation && !task.can_manage && (
                <p className="assoc-muted task-status-hint">
                  {task.my_status === 'review' ? 'Руководитель проверит работу и отметит «Готово» или вернёт на доработку.'
                    : task.my_status === 'done' ? 'Руководитель принял работу.'
                      : 'Когда закончите, прикрепите результат ниже и нажмите «На проверке».'}
                </p>
              )}
            </section>
          )}

          <section className="card task-block" aria-labelledby="task-files">
            <h2 id="task-files">Файлы и ссылки</h2>
            <Attachments owner="tasks" ownerId={task.id} items={task.attachments} canAdd onChange={load} />
          </section>

          {isAssociation && (
            <section className="card task-block" aria-labelledby="task-comments">
              <h2 id="task-comments">Обсуждение</h2>
              {task.comments.length === 0 && <p className="assoc-muted">Вопросы по задаче — здесь. Их видят исполнители и руководитель.</p>}
              <ul className="task-comments">
                {task.comments.map(c => (
                  <li key={c.id} className={`task-comment ${c.author_id === user?.id ? 'is-mine' : ''}`}>
                    <p className="task-comment-head">
                      <span className="task-comment-author with-avatar">
                        <Avatar name={c.author_name} url={c.author_photo_url} size="xs" />{c.author_name}
                      </span>
                      <span className="task-optional">{when(c.created_at)}</span>
                      {c.can_delete && (
                        <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="Удалить комментарий" title="Удалить"
                          onClick={async () => { if (window.confirm('Удалить комментарий?')) { await tasksApi.deleteComment(c.id).catch(() => {}); load(); } }}>
                          <Trash2 size={14} {...ICON} />
                        </button>
                      )}
                    </p>
                    <p className="task-comment-text">{c.text}</p>
                  </li>
                ))}
              </ul>
              <form className="task-comment-form" onSubmit={sendComment}>
                <label className="visually-hidden" htmlFor="task-comment">Комментарий</label>
                <textarea id="task-comment" className="textarea" rows={2} maxLength={2000} value={comment} placeholder="Написать комментарий"
                  onChange={e => setComment(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) sendComment(e); }} />
                <button type="submit" className="btn btn-primary" disabled={sending || !comment.trim()}><Send size={16} {...ICON} />Отправить</button>
              </form>
            </section>
          )}
        </div>

        {leaderView && (
          <aside className="assoc-aside">
            <section className="card task-block" aria-labelledby="task-assignees">
              <h2 id="task-assignees">Исполнители · {task.assignees.length}</h2>
              <ul className="task-assignees">
                {task.assignees.map(a => {
                  const note = handedInNote(a, task.due_at);
                  return (
                    <li key={a.user_id} className="task-assignee">
                      <div className="task-assignee-head">
                        <span className="assoc-person-name"><Avatar name={a.full_name} url={a.photo_url} />{a.full_name}</span>
                        <span className={`badge task-status-badge task-status-${a.status}`}>{STATUS_LABEL[a.status]}</span>
                      </div>
                      <span className="assoc-person-meta">
                        {a.group_number && <span className="tabular">{a.group_number}</span>}
                        {note && <span className={note.late ? 'task-late' : ''}>{note.text}</span>}
                      </span>
                      {a.status === 'review' && (
                        <div className="task-review-actions">
                          <button type="button" className="btn btn-primary btn-sm" onClick={() => setStatus('done', a.user_id)}><Check size={16} {...ICON} />Принять</button>
                          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setStatus('in_progress', a.user_id)}><Undo2 size={16} {...ICON} />На доработку</button>
                        </div>
                      )}
                      <ContactLinks vk={a.vk_url} max={a.max_contact} name={a.full_name} />
                      {task.assignees.length > 1 && (
                        <button type="button" className="btn btn-ghost btn-sm task-assignee-remove"
                          onClick={async () => {
                            if (!window.confirm(`Снять ${a.full_name} с задачи?`)) return;
                            try { await tasksApi.removeAssignee(task.id, a.user_id); load(); } catch (e) { toast.show(e.message, 'error'); }
                          }}>
                          <X size={14} {...ICON} />Снять с задачи
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
              {addOpen ? (
                <div className="task-add-people">
                  {candidates === null ? <p className="assoc-muted">Загружаем…</p>
                    : candidates.length === 0 ? <p className="assoc-muted">Все участники уже в задаче.</p>
                      : (
                        <ul className="task-people">
                          {candidates.map(m => (
                            <li key={m.user_id}>
                              <label className="task-person">
                                <input type="checkbox" checked={picked.includes(m.user_id)}
                                  onChange={() => setPicked(p => (p.includes(m.user_id) ? p.filter(x => x !== m.user_id) : [...p, m.user_id]))} />
                                <span>{m.full_name}</span>
                              </label>
                            </li>
                          ))}
                        </ul>
                      )}
                  <div className="task-review-actions">
                    <button type="button" className="btn btn-primary btn-sm" disabled={!picked.length} onClick={addPeople}>Добавить</button>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAddOpen(false)}>Отменить</button>
                  </div>
                </div>
              ) : (
                <button type="button" className="btn btn-ghost btn-sm" onClick={openAdd}><UserPlus size={16} {...ICON} />Добавить исполнителей</button>
              )}
            </section>
          </aside>
        )}
      </div>
    </div>
  );
};

export default TaskDetail;
