import React, { useCallback, useEffect, useState } from 'react';
import { Megaphone, Trash2, Loader2, Users } from 'lucide-react';
import Attachments from './Attachments';
import { useToast } from '../context/ToastContext';
import { postsApi } from '../services/api';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const EMPTY = { title: '', text: '', toAll: true, recipients: [] };
const when = (iso) => (iso ? new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }) : '');

/**
 * Announcements of an association: members see the ones meant for them, leaders write new ones
 * (to everyone or to chosen members) and attach files and links to them.
 */
const AssociationPosts = ({ associationId, canManage, members }) => {
  const toast = useToast();
  const [posts, setPosts] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [writing, setWriting] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    postsApi.list(associationId).then(res => setPosts(res || [])).catch(() => setPosts([]));
  }, [associationId]);
  useEffect(load, [load]);

  const publish = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      await postsApi.create(associationId, {
        title: form.title.trim(), text: form.text.trim(), to_all: form.toAll, recipient_ids: form.toAll ? [] : form.recipients,
      });
      setForm(EMPTY);
      setWriting(false);
      toast.show('Объявление опубликовано. Файлы можно прикрепить к нему ниже.', 'success', 4000);
      load();
    } catch (err) {
      toast.show(err.message || 'Не удалось опубликовать', 'error');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (post) => {
    if (!window.confirm(`Удалить объявление «${post.title}» вместе с файлами?`)) return;
    try {
      await postsApi.remove(post.id);
      load();
    } catch (err) {
      toast.show(err.message || 'Не удалось удалить', 'error');
    }
  };

  if (posts === null) return null;
  if (!canManage && posts.length === 0) return null;
  const people = (members || []).filter(m => m.role === 'member');

  return (
    <section className="card assoc-card-block" aria-labelledby="assoc-posts">
      <div className="assoc-manage-head">
        <h2 id="assoc-posts">Объявления</h2>
        {canManage && !writing && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setWriting(true)}><Megaphone size={16} {...ICON} />Написать</button>
        )}
      </div>

      {writing && (
        <form className="assoc-form post-form" onSubmit={publish}>
          <div className="field">
            <label className="field-label" htmlFor="post-title">Заголовок</label>
            <input id="post-title" className="input" maxLength={200} required autoFocus value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Например: ссылка на чат объединения" />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="post-text">Текст</label>
            <textarea id="post-text" className="textarea" rows={4} maxLength={5000} value={form.text}
              onChange={e => setForm({ ...form, text: e.target.value })} />
          </div>
          <fieldset className="field">
            <legend className="field-label">Кому</legend>
            <div className="segmented" role="group" aria-label="Кому">
              <button type="button" className={`segmented-item ${form.toAll ? 'active' : ''}`} aria-pressed={form.toAll} onClick={() => setForm({ ...form, toAll: true })}>Всем участникам</button>
              <button type="button" className={`segmented-item ${!form.toAll ? 'active' : ''}`} aria-pressed={!form.toAll} onClick={() => setForm({ ...form, toAll: false })}>Выбрать</button>
            </div>
            {!form.toAll && (people.length === 0 ? <p className="assoc-muted">Участников пока нет.</p> : (
              <ul className="task-people">
                {people.map(m => (
                  <li key={m.user_id}>
                    <label className="task-person">
                      <input type="checkbox" checked={form.recipients.includes(m.user_id)}
                        onChange={() => setForm(f => ({ ...f, recipients: f.recipients.includes(m.user_id) ? f.recipients.filter(x => x !== m.user_id) : [...f.recipients, m.user_id] }))} />
                      <span>{m.full_name}</span>
                    </label>
                  </li>
                ))}
              </ul>
            ))}
          </fieldset>
          <div className="cm-form-actions">
            <button type="button" className="btn btn-ghost" onClick={() => { setWriting(false); setForm(EMPTY); }}>Отменить</button>
            <button type="submit" className="btn btn-primary" disabled={saving || (!form.toAll && !form.recipients.length)}>
              {saving && <Loader2 size={16} className="spin-icon" {...ICON} />}Опубликовать
            </button>
          </div>
        </form>
      )}

      {posts.length === 0 ? (
        !writing && <p className="assoc-muted">Объявлений пока нет. Здесь удобно держать ссылку на чат, распоряжения и материалы.</p>
      ) : (
        <ul className="posts">
          {posts.map(p => (
            <li key={p.id} className="post">
              <div className="post-head">
                <h3>{p.title}</h3>
                {p.can_manage && (
                  <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => remove(p)} aria-label={`Удалить объявление ${p.title}`} title="Удалить">
                    <Trash2 size={16} {...ICON} />
                  </button>
                )}
              </div>
              <p className="assoc-person-meta">
                <span>{when(p.created_at)}</span>
                {p.author && <span>{p.author.split(' ').slice(0, 2).join(' ')}</span>}
                {!p.to_all && (
                  <span className="post-private">
                    <Users size={14} {...ICON} />
                    {p.can_manage ? `Только: ${p.recipients.map(r => r.full_name.split(' ').slice(0, 2).join(' ')).join(', ')}` : 'Лично вам'}
                  </span>
                )}
              </p>
              {p.text && <p className="assoc-description post-text">{p.text}</p>}
              {(p.attachments.length > 0 || p.can_manage) && (
                <Attachments owner="associations/posts" ownerId={p.id} items={p.attachments} canAdd={p.can_manage} onChange={load} />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

export default AssociationPosts;
