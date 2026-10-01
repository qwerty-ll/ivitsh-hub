import React, { useCallback, useEffect, useState } from 'react';
import { Trash2, Lock, LockOpen, Search, ChevronLeft, ChevronRight, Eraser } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { adminApi } from '../../services/api';
import { Toolbar, RefreshButton, ListSkeleton, LoadError, ICON } from './AdminUi';

const ROLE_LABELS = { student: 'Студент', moderator: 'Модератор', admin: 'Администратор' };
const PAGE = 50;
const JOURNAL_PAGE = 30;

const formatDay = (value) => (value ? new Date(value).toLocaleDateString('ru-RU') : '');
const formatMoment = (value) => (value
  ? new Date(value).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  : '');

// Who changed what: roles, blocks, deletions, leaders, bit grants
const Journal = () => {
  const [rows, setRows] = useState(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');

  const load = useCallback((offset = 0) => {
    setError('');
    adminApi.getActions(JOURNAL_PAGE, offset)
      .then(({ items, total: count }) => {
        setRows(prev => (offset === 0 ? items : [...(prev || []), ...items]));
        setTotal(count ?? items.length);
      })
      .catch(e => { setError(e.message || 'Не удалось загрузить журнал'); setRows(prev => prev || []); });
  }, []);
  useEffect(() => { load(0); }, [load]);

  if (error && !rows?.length) return <LoadError message={error} onRetry={() => load(0)} />;
  if (rows === null) return <ListSkeleton />;
  if (rows.length === 0) return <p className="admin-empty">Действий пока не было.</p>;
  return (
    <>
      <table className="admin-table">
        <caption className="visually-hidden">Журнал действий администраторов</caption>
        <thead>
          <tr>
            <th scope="col">Когда</th>
            <th scope="col">Кто</th>
            <th scope="col">Действие</th>
            <th scope="col">С кем</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(a => (
            <tr key={a.id}>
              <td className="admin-cell-meta tabular" data-label="Когда">{formatMoment(a.created_at)}</td>
              <td className="admin-cell-meta" data-label="Кто">{a.actor_name}</td>
              <td className="admin-cell-wrap" data-label="Действие">
                {a.action_text}{a.details ? `: ${a.details}` : ''}
              </td>
              <td className={`admin-cell-meta${a.target_name ? '' : ' admin-cell-muted'}`} data-label="С кем">
                {a.target_name || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length < total && (
        <button type="button" className="btn btn-secondary btn-sm admin-more" onClick={() => load(rows.length)}>
          Показать ещё ({total - rows.length})
        </button>
      )}
    </>
  );
};

/** "Пользователи" tab: everyone, page by page, with search, filters, roles, blocking and deletion. */
const AdminUsers = ({ panelProps, onCount }) => {
  const { user, isMainAdmin } = useAuth();
  const toast = useToast();
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [role, setRole] = useState('');
  const [state, setState] = useState('all');
  const [sort, setSort] = useState('new');
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [journalOpen, setJournalOpen] = useState(false);

  // Search waits for a pause in typing
  useEffect(() => {
    const timer = setTimeout(() => { setQuery(q.trim()); setOffset(0); }, 300);
    return () => clearTimeout(timer);
  }, [q]);

  const load = useCallback(() => {
    setError('');
    adminApi.getUsers({ q: query, role, state, sort, limit: PAGE, offset })
      .then(({ items, total: count }) => {
        setList(items);
        setTotal(count ?? items.length);
        if (!query && !role && state === 'all') onCount?.(count);
      })
      .catch(e => { setError(e.message || 'Не удалось загрузить пользователей'); setList([]); });
  }, [query, role, state, sort, offset, onCount]);
  useEffect(load, [load]);

  const replace = (updated) => setList(prev => prev.map(u => (u.id === updated.id ? { ...u, ...updated } : u)));
  const filter = (setter) => (e) => { setter(e.target.value); setOffset(0); };

  const changeRole = async (u, newRole) => {
    try {
      replace(await adminApi.updateUserRole(u.id, newRole));
      toast.show(`Роль: ${ROLE_LABELS[newRole]} — ${u.full_name}`, 'success');
    } catch (err) {
      toast.show(err.message || 'Ошибка изменения роли', 'warning');
    }
  };

  const toggleBlock = async (u) => {
    const blocked = !u.is_blocked;
    if (!window.confirm(`${blocked ? 'Заблокировать' : 'Разблокировать'} пользователя «${u.full_name}»?`)) return;
    try {
      replace(await adminApi.setUserBlocked(u.id, blocked));
      toast.show(`«${u.full_name}» ${blocked ? 'заблокирован' : 'разблокирован'}`, 'success');
    } catch (err) {
      toast.show(err.message || 'Не удалось изменить блокировку', 'warning');
    }
  };

  const remove = async (u, purge) => {
    const question = purge
      ? 'Стереть запись полностью? Вместе с ней исчезнут её заказы, вопросы и ответы на форуме, отметки присутствия. Это нельзя отменить.'
      : `Удалить «${u.full_name}»? ФИО, логин, группа, контакты, личные задачи и записи ПГАС будут стёрты, членство в объединениях и неполученные заказы — сняты. История (выданные заказы, брони, форум, посещаемость) останется под именем «Удалённый пользователь». Если студент снова войдёт через ЭИОС, создастся новый аккаунт — чтобы закрыть доступ, используйте блокировку.`;
    if (!window.confirm(question)) return;
    try {
      await adminApi.deleteUser(u.id, purge);
      toast.show(purge ? 'Запись стёрта полностью' : `«${u.full_name}» удалён`, 'success');
      load();
    } catch (err) {
      toast.show(err.message || 'Ошибка удаления пользователя', 'warning');
    }
  };

  const filtered = query || role || state !== 'all';
  const from = total ? offset + 1 : 0;
  const to = Math.min(offset + PAGE, total);

  return (
    <section {...panelProps}>
      <Toolbar
        title="Пользователи"
        description={isMainAdmin
          ? 'Все, кто хоть раз входил через ЭИОС. Назначайте Администраторов и Модераторов, блокируйте и удаляйте.'
          : 'Все, кто хоть раз входил через ЭИОС. Права Администратора выдаёт и снимает только Главный Администратор.'}
      >
        <RefreshButton onClick={load} />
      </Toolbar>

      <div className="admin-filters">
        <div className="cm-search admin-filters-search">
          <label htmlFor="admin-users-search" className="visually-hidden">Поиск пользователей</label>
          <Search size={16} strokeWidth={1.75} aria-hidden="true" className="cm-search-icon" />
          <input id="admin-users-search" className="input" type="search" autoComplete="off"
            placeholder="ФИО, логин или группа" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <label className="visually-hidden" htmlFor="admin-users-role">Роль</label>
        <select id="admin-users-role" className="select" value={role} onChange={filter(setRole)}>
          <option value="">Все роли</option>
          <option value="student">Студенты</option>
          <option value="moderator">Модераторы</option>
          <option value="admin">Администраторы</option>
        </select>
        <label className="visually-hidden" htmlFor="admin-users-state">Состояние</label>
        <select id="admin-users-state" className="select" value={state} onChange={filter(setState)}>
          <option value="all">Все действующие</option>
          <option value="active">Активные</option>
          <option value="blocked">Заблокированные</option>
          <option value="deleted">Удалённые</option>
        </select>
        <label className="visually-hidden" htmlFor="admin-users-sort">Порядок</label>
        <select id="admin-users-sort" className="select" value={sort} onChange={filter(setSort)}>
          <option value="new">Сначала новые</option>
          <option value="name">По ФИО</option>
          <option value="group">По группе</option>
          <option value="seen">По последнему входу</option>
        </select>
      </div>

      <div className="admin-list">
        {error ? (
          <LoadError message={error} onRetry={load} />
        ) : list === null ? (
          <ListSkeleton />
        ) : list.length === 0 ? (
          <p className="admin-empty">{filtered ? 'Никого не нашли.' : 'Нет зарегистрированных пользователей.'}</p>
        ) : (
          <table className="admin-table">
            <caption className="visually-hidden">Пользователи портала</caption>
            <thead>
              <tr>
                <th scope="col">Пользователь</th>
                <th scope="col">Группа</th>
                <th scope="col">Был на портале</th>
                <th scope="col">Роль</th>
                <th scope="col" className="admin-cell-controls"><span className="visually-hidden">Действия</span></th>
              </tr>
            </thead>
            <tbody>
              {list.map(u => {
                const isSuperAdmin = u.auth_source === 'local';
                const isDeleted = u.auth_source === 'deleted';
                const isSelf = user && u.id === user.id;
                // Other administrators are managed by the main administrator only (the server checks it too)
                const otherAdmin = u.role === 'admin' && !isMainAdmin;
                const locked = isSuperAdmin || isSelf || otherAdmin || isDeleted;
                return (
                  <tr key={u.id} className={isDeleted ? 'admin-row-muted' : undefined}>
                    <td className="admin-cell-main">
                      <div className="admin-cell-head">
                        <span className="admin-cell-title">{u.full_name || u.username}</span>
                        {isSuperAdmin && <span className="badge badge-accent">Главный Админ</span>}
                        {u.is_blocked && !isDeleted && <span className="badge badge-danger">Заблокирован</span>}
                        {isSelf && <span className="badge">Это вы</span>}
                      </div>
                      {!isDeleted && <p className="admin-cell-sub">Логин: {u.username}</p>}
                    </td>
                    <td className={`admin-cell-meta${u.group_number ? '' : ' admin-cell-muted'}`} data-label="Группа">
                      {u.group_number || 'Не указана'}
                    </td>
                    <td className={`admin-cell-meta tabular${u.last_seen_at ? '' : ' admin-cell-muted'}`} data-label="Был на портале">
                      {u.last_seen_at ? formatDay(u.last_seen_at) : 'Нет данных'}
                    </td>
                    <td className="admin-cell-role" data-label="Роль">
                      {locked ? (
                        <span className="admin-role-fixed" title={otherAdmin ? 'Права администратора меняет только Главный Администратор' : 'Роль этого пользователя нельзя изменить'}>
                          <Lock {...ICON} />
                          {isSuperAdmin ? 'Администратор ИВИТШ' : isDeleted ? 'Удалён' : (ROLE_LABELS[u.role] || u.role)}
                          <span className="visually-hidden">, роль нельзя изменить</span>
                        </span>
                      ) : (
                        <select
                          className="select admin-role-select"
                          aria-label={`Роль пользователя ${u.full_name}`}
                          value={u.role}
                          onChange={(e) => changeRole(u, e.target.value)}
                        >
                          <option value="student">{ROLE_LABELS.student}</option>
                          <option value="moderator">{ROLE_LABELS.moderator}</option>
                          {isMainAdmin && <option value="admin">{ROLE_LABELS.admin}</option>}
                        </select>
                      )}
                    </td>
                    <td className="admin-cell-controls">
                      {isDeleted && !otherAdmin ? (
                        <div className="admin-controls">
                          <button type="button" className="btn btn-danger btn-sm" onClick={() => remove(u, true)}
                            title="Стереть запись вместе с историей">
                            <Eraser {...ICON} /> Стереть полностью
                          </button>
                        </div>
                      ) : !locked && (
                        <div className="admin-controls">
                          <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggleBlock(u)}
                            title={u.is_blocked ? 'Разблокировать пользователя' : 'Заблокировать пользователя'}>
                            {u.is_blocked ? <LockOpen {...ICON} /> : <Lock {...ICON} />}
                            {u.is_blocked ? 'Разблокировать' : 'Заблокировать'}
                          </button>
                          <button type="button" className="btn btn-danger btn-sm" onClick={() => remove(u, false)}
                            title="Удалить пользователя (история останется без имени)">
                            <Trash2 {...ICON} /> Удалить
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {total > 0 && (
        <nav className="admin-pager" aria-label="Страницы списка пользователей">
          <span className="tabular" aria-live="polite">{from}–{to} из {total.toLocaleString('ru-RU')}</span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            <ChevronLeft {...ICON} /> Назад
          </button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={to >= total}
            onClick={() => setOffset(offset + PAGE)}>
            Вперёд <ChevronRight {...ICON} />
          </button>
        </nav>
      )}

      <details className="admin-journal" onToggle={e => setJournalOpen(e.currentTarget.open)}>
        <summary>Журнал действий администраторов</summary>
        {journalOpen && (
          <div className="admin-list">
            <Journal />
          </div>
        )}
      </details>
    </section>
  );
};

export default AdminUsers;
