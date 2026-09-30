import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Save, X, UserPlus, Eye, EyeOff, ExternalLink, Search } from 'lucide-react';
import { useToast } from '../../context/ToastContext';
import { adminApi } from '../../services/api';
import { Field, Toolbar, RefreshButton, ListSkeleton, LoadError, RowActions, ICON } from './AdminUi';

const EMPTY_FORM = { name: '', leader_hint: '', contacts: '', description: '', is_active: true };

// Finds a signed-in user by name, login or group and assigns them as a leader
const LeaderPicker = ({ association, onAssign, onClose }) => {
  const [q, setQ] = useState('');
  const [found, setFound] = useState([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const query = q.trim();
    if (query.length < 2) { setFound([]); return undefined; }
    setSearching(true);
    const timer = setTimeout(() => {
      adminApi.searchUsers(query)
        .then(res => setFound(Array.isArray(res) ? res : []))
        .catch(() => setFound([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [q]);

  const leaderIds = new Set(association.leaders.map(l => l.id));
  return (
    <div className="admin-assoc-picker">
      <div className="cm-search">
        <label htmlFor={`leader-search-${association.id}`} className="visually-hidden">Найти руководителя</label>
        <Search size={16} strokeWidth={1.75} aria-hidden="true" className="cm-search-icon" />
        <input id={`leader-search-${association.id}`} className="input" type="search" autoFocus autoComplete="off"
          placeholder="ФИО, логин или группа" value={q} onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Escape') onClose(); }} />
      </div>
      {q.trim().length >= 2 && (
        <ul className="admin-assoc-results" aria-live="polite">
          {searching && found.length === 0 ? <li className="admin-cell-muted">Ищу…</li>
            : found.length === 0 ? <li className="admin-cell-muted">Никого не нашли. Человек должен хотя бы раз войти на портал.</li>
              : found.filter(u => !leaderIds.has(u.id)).map(u => (
                <li key={u.id}>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => onAssign(u)}>
                    <UserPlus {...ICON} />{u.full_name}{u.group_number ? `, ${u.group_number}` : ''}
                  </button>
                </li>
              ))}
        </ul>
      )}
      <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Закрыть</button>
    </div>
  );
};

/** "Объединения" tab: create and edit associations, assign and remove leaders. */
const AdminAssociations = ({ panelProps, onCount }) => {
  const toast = useToast();
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [pickerFor, setPickerFor] = useState(null);

  const load = useCallback(() => {
    setError('');
    adminApi.getAssociations()
      .then(res => { const list = Array.isArray(res) ? res : []; setItems(list); onCount?.(list.length); })
      .catch(e => { setError(e.message || 'Не удалось загрузить объединения'); setItems([]); });
  }, [onCount]);
  useEffect(load, [load]);

  // Replaces one row with the server's answer
  const replace = (updated) => setItems(prev => prev.map(a => (a.id === updated.id ? updated : a)));

  const run = async (fn, message) => {
    try {
      const res = await fn();
      if (message) toast.show(message, 'success');
      return res;
    } catch (e) {
      toast.show(e.message || 'Не получилось', 'error');
      return null;
    }
  };

  const resetForm = () => { setEditingId(null); setForm(EMPTY_FORM); };

  const submit = async (e) => {
    e.preventDefault();
    const data = { ...form, name: form.name.trim() };
    if (editingId) {
      const updated = await run(() => adminApi.updateAssociation(editingId, data), 'Объединение сохранено');
      if (updated) { replace(updated); resetForm(); }
    } else {
      const created = await run(() => adminApi.createAssociation(data), 'Объединение добавлено');
      if (created) { load(); resetForm(); }
    }
  };

  const startEdit = (a) => {
    setEditingId(a.id);
    setForm({ name: a.name, leader_hint: a.leader_hint || '', contacts: a.contacts || '', description: a.description || '', is_active: a.is_active });
    window.requestAnimationFrame(() => document.getElementById('admin-assoc-name')?.focus());
  };

  const toggleActive = async (a) => {
    const updated = await run(
      () => adminApi.updateAssociation(a.id, { name: a.name, leader_hint: a.leader_hint, contacts: a.contacts, description: a.description, is_active: !a.is_active }),
      a.is_active ? 'Объединение скрыто из каталога' : 'Объединение снова в каталоге',
    );
    if (updated) replace(updated);
  };

  const remove = async (a) => {
    if (!window.confirm(`Удалить «${a.name}» вместе со списком участников и заявками? Чтобы сохранить историю, лучше скрыть объединение.`)) return;
    if (await run(() => adminApi.deleteAssociation(a.id), 'Объединение удалено')) load();
  };

  const assign = async (a, u) => {
    const updated = await run(() => adminApi.addLeader(a.id, u.id), `${u.full_name} — руководитель «${a.name}»`);
    if (updated) { replace(updated); setPickerFor(null); }
  };

  const unassign = async (a, u) => {
    if (!window.confirm(`Снять ${u.full_name} с руководства «${a.name}»? Он(а) останется участником.`)) return;
    const updated = await run(() => adminApi.removeLeader(a.id, u.id), 'Руководитель снят');
    if (updated) replace(updated);
  };

  return (
    <section {...panelProps}>
      <Toolbar title="Объединения" description="Каталог объединений и их руководители. Руководитель сам принимает заявки и ведёт описание.">
        <RefreshButton onClick={load} />
      </Toolbar>

      <div className="card admin-editor">
        <div className="admin-editor-head">
          <h3>{editingId ? 'Редактировать объединение' : 'Добавить объединение'}</h3>
          <p>Руководителя назначьте в списке ниже, когда он(а) хотя бы раз войдёт на портал через ЭИОС.</p>
        </div>
        <form onSubmit={submit} className="admin-form">
          <div className="admin-grid">
            <Field id="admin-assoc-name" label="Название" required>
              <input id="admin-assoc-name" className="input" maxLength={100} required value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field id="admin-assoc-hint" label="Руководитель по списку" hint="ФИО из списка института: портал подскажет, когда этот человек войдёт">
              <input id="admin-assoc-hint" className="input" maxLength={200} value={form.leader_hint}
                aria-describedby="admin-assoc-hint-hint" placeholder="Фамилия Имя"
                onChange={e => setForm({ ...form, leader_hint: e.target.value })} />
            </Field>
            <Field id="admin-assoc-contacts" label="Где найти" className="admin-span-full">
              <input id="admin-assoc-contacts" className="input" maxLength={200} value={form.contacts}
                placeholder="Чат, группа ВК или место встреч" onChange={e => setForm({ ...form, contacts: e.target.value })} />
            </Field>
            <Field id="admin-assoc-description" label="Описание" className="admin-span-full">
              <textarea id="admin-assoc-description" className="textarea" rows={3} maxLength={3000} value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })} />
            </Field>
          </div>
          <div className="admin-form-actions">
            <button type="submit" className="btn btn-primary"><Save {...ICON} /> {editingId ? 'Сохранить изменения' : 'Добавить объединение'}</button>
            {editingId && <button type="button" className="btn btn-ghost" onClick={resetForm}>Отменить редактирование</button>}
          </div>
        </form>
      </div>

      <div className="admin-list">
        {items === null ? <ListSkeleton />
          : error ? <LoadError message={error} onRetry={load} />
            : items.length === 0 ? <p className="admin-empty">Объединений пока нет. Добавьте первое в форме выше.</p>
              : (
                <table className="admin-table">
                  <caption className="visually-hidden">Объединения</caption>
                  <thead>
                    <tr>
                      <th scope="col">Объединение</th>
                      <th scope="col">Руководители</th>
                      <th scope="col">Участники</th>
                      <th scope="col" className="admin-cell-actions"><span className="visually-hidden">Действия</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map(a => (
                      <tr key={a.id} className={a.is_active ? '' : 'admin-row-muted'}>
                        <td className="admin-cell-main">
                          <span className="admin-cell-title">
                            {a.name}
                            {!a.is_active && <span className="badge"> скрыто</span>}
                          </span>
                          {a.leader_hint && <p className="admin-cell-sub">По списку: {a.leader_hint}</p>}
                        </td>
                        <td className="admin-cell-wrap" data-label="Руководители">
                          <div className="admin-assoc-leaders">
                            {a.leaders.map(u => (
                              <span key={u.id} className="admin-assoc-chip">
                                {u.full_name}
                                <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => unassign(a, u)}
                                  aria-label={`Снять ${u.full_name} с руководства`} title="Снять с руководства">
                                  <X {...ICON} />
                                </button>
                              </span>
                            ))}
                            {a.hint_matches.map(u => (
                              <button key={u.id} type="button" className="btn btn-secondary btn-sm" onClick={() => assign(a, u)}
                                title="Этот человек уже входил на портал">
                                <UserPlus {...ICON} />Назначить: {u.full_name}{u.group_number ? `, ${u.group_number}` : ''}
                              </button>
                            ))}
                            {a.leaders.length === 0 && a.hint_matches.length === 0 && (
                              <span className="admin-cell-muted">{a.leader_hint ? 'Ещё не входил(а) на портал' : 'Не назначен'}</span>
                            )}
                            {pickerFor === a.id ? (
                              <LeaderPicker association={a} onAssign={u => assign(a, u)} onClose={() => setPickerFor(null)} />
                            ) : (
                              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPickerFor(a.id)}>
                                <UserPlus {...ICON} />Назначить руководителя
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="admin-cell-meta tabular" data-label="Участники">
                          {a.member_count}{a.pending_count > 0 && <span className="badge badge-warning"> заявок: {a.pending_count}</span>}
                        </td>
                        <td className="admin-cell-controls">
                          <div className="admin-actions">
                            <Link to={`/associations/${a.id}`} className="btn btn-ghost btn-icon btn-sm" title="Открыть страницу"
                              aria-label={`Открыть страницу: ${a.name}`}>
                              <ExternalLink {...ICON} />
                            </Link>
                            <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => toggleActive(a)}
                              title={a.is_active ? 'Скрыть из каталога' : 'Показать в каталоге'}
                              aria-label={`${a.is_active ? 'Скрыть из каталога' : 'Показать в каталоге'}: ${a.name}`}>
                              {a.is_active ? <EyeOff {...ICON} /> : <Eye {...ICON} />}
                            </button>
                            <RowActions label={a.name} onEdit={() => startEdit(a)} onDelete={() => remove(a)} />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
      </div>
    </section>
  );
};

export default AdminAssociations;
