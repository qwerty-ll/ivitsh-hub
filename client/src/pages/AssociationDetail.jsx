import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft, Users, LogIn, Check, X, UserMinus, Clock, Info, RotateCw, Loader2, Plus
} from 'lucide-react';
import AssociationPosts from '../components/AssociationPosts';
import AssociationMeetings from '../components/AssociationMeetings';
import AssociationEvents from '../components/AssociationEvents';
import ContactLinks from '../components/ContactLinks';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { associationsApi } from '../services/api';
import { STATUS_BADGE, assocHue, monogram, plural } from '../utils/associations';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const formatDate = (iso) => (iso ? new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }) : '');

// One person in the leader's lists: name, group, their note and contacts, then the actions
const PersonRow = ({ person, children }) => (
  <li className="assoc-person">
    <div className="assoc-person-main">
      <span className="assoc-person-name">
        {person.full_name}
        {person.role === 'leader' && <span className="badge badge-accent">Руководитель</span>}
      </span>
      <span className="assoc-person-meta">
        {person.group_number && <span className="tabular">{person.group_number}</span>}
        {person.status === 'pending' && person.created_at && <span>заявка от {formatDate(person.created_at)}</span>}
      </span>
      {person.message && <p className="assoc-person-note">«{person.message}»</p>}
      <ContactLinks vk={person.vk_url} max={person.max_contact} name={person.full_name}
        empty={<span className="assoc-muted">Контакты не указаны</span>} />
    </div>
    {children && <div className="assoc-person-actions">{children}</div>}
  </li>
);

const AssociationDetail = () => {
  const { id } = useParams();
  const { isLoggedIn } = useAuth();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [tab, setTab] = useState('applications');
  const [edit, setEdit] = useState(null); // { description, contacts } while the leader edits

  const load = () => {
    setError('');
    associationsApi.get(id)
      .then(res => setData(res))
      .catch(e => { setError(e.status === 404 ? 'Такого объединения нет или оно скрыто.' : (e.message || 'Не удалось загрузить')); });
  };
  useEffect(load, [id, isLoggedIn]);

  // Runs an action, then reloads the page data; the toast says what happened
  const act = async (fn, done) => {
    setBusy(true);
    try {
      await fn();
      if (done) toast.show(done, 'success');
      load();
      return true;
    } catch (e) {
      toast.show(e.message || 'Не получилось', 'error');
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <div className="container assoc-page">
        <Link to="/associations" className="assoc-back"><ArrowLeft size={16} {...ICON} />Все объединения</Link>
        <div className="empty-state" role="alert">
          <h1 className="cm-empty-title">{error}</h1>
          <button type="button" className="btn btn-secondary" onClick={load}><RotateCw size={16} {...ICON} />Повторить</button>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="container assoc-page" aria-busy="true">
        <span className="skeleton" style={{ width: '40%', height: '2.25rem' }} />
        <span className="skeleton" style={{ width: '100%', height: '10rem', marginTop: 'var(--space-6)' }} />
      </div>
    );
  }

  const badge = STATUS_BADGE(data.my_role, data.my_status);
  const isMember = data.my_status === 'approved';
  const isPending = data.my_status === 'pending';
  const isLeader = isMember && data.my_role === 'leader';

  return (
    <div className="container assoc-page">
      <Link to="/associations" className="assoc-back"><ArrowLeft size={16} {...ICON} />Все объединения</Link>

      <header className="assoc-head">
        <span className={`assoc-mono assoc-mono-lg hue-${assocHue(data.id)}`} aria-hidden="true">{monogram(data.name)}</span>
        <div className="assoc-head-text">
          <h1>{data.name}</h1>
          <p className="assoc-head-meta">
            <span className="assoc-count tabular">
              <Users size={16} {...ICON} />
              {data.member_count} {plural(data.member_count, ['участник', 'участника', 'участников'])}
            </span>
            {badge && <span className={`badge ${badge.tone}`}>{badge.label}</span>}
          </p>
        </div>
      </header>

      <div className="assoc-layout">
        <div className="assoc-main">
          <section className="card assoc-card-block" aria-labelledby="assoc-about">
            <h2 id="assoc-about">Об объединении</h2>
            {data.description
              ? <p className="assoc-description">{data.description}</p>
              : <p className="assoc-muted">Руководитель ещё не добавил описание.</p>}
            {data.contacts && <p className="assoc-contacts"><Info size={16} {...ICON} />{data.contacts}</p>}
          </section>

          {/* LEADER'S PANEL */}
          {data.can_manage && (
            <section className="card assoc-card-block" aria-labelledby="assoc-manage">
              <div className="assoc-manage-head">
                <h2 id="assoc-manage">Управление</h2>
                <div className="segmented" role="group" aria-label="Раздел управления">
                  {[
                    ['applications', `Заявки${data.applications.length ? ` · ${data.applications.length}` : ''}`],
                    ['members', `Участники · ${data.members.length}`],
                    ['about', 'Описание'],
                  ].map(([key, label]) => (
                    <button key={key} type="button" className={`segmented-item ${tab === key ? 'active' : ''}`}
                      aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>
                  ))}
                </div>
              </div>

              {tab === 'applications' && (data.applications.length === 0 ? (
                <p className="assoc-muted">Новых заявок нет.</p>
              ) : (
                <ul className="assoc-people">
                  {data.applications.map(p => (
                    <PersonRow key={p.user_id} person={p}>
                      <button type="button" className="btn btn-primary btn-sm" disabled={busy}
                        onClick={() => act(() => associationsApi.decide(data.id, p.user_id, true), `${p.full_name} принят(а)`)}>
                        <Check size={16} {...ICON} />Принять
                      </button>
                      <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                        onClick={() => act(() => associationsApi.decide(data.id, p.user_id, false), 'Заявка отклонена')}>
                        <X size={16} {...ICON} />Отклонить
                      </button>
                    </PersonRow>
                  ))}
                </ul>
              ))}

              {tab === 'members' && (
                <ul className="assoc-people">
                  {data.members.map(p => (
                    <PersonRow key={p.user_id} person={p}>
                      {p.role !== 'leader' && (
                        <button type="button" className="btn btn-ghost btn-sm" disabled={busy}
                          onClick={() => {
                            if (window.confirm(`Исключить ${p.full_name} из объединения? Незавершённые задачи и запись на будущие мероприятия объединения снимутся, а подать заявку снова без вашего разрешения будет нельзя.`)) {
                              act(() => associationsApi.removeMember(data.id, p.user_id), 'Участник исключён');
                            }
                          }}>
                          <UserMinus size={16} {...ICON} />Исключить
                        </button>
                      )}
                    </PersonRow>
                  ))}
                  {data.removed?.length > 0 && (
                    <li className="assoc-removed">
                      <h3 className="cal-subhead">Исключены</h3>
                      <p className="assoc-muted">Сами подать заявку снова не могут — только если вы их вернёте.</p>
                      <ul className="assoc-people">
                        {data.removed.map(p => (
                          <PersonRow key={p.user_id} person={p}>
                            <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                              onClick={() => act(() => associationsApi.restoreMember(data.id, p.user_id), `${p.full_name} снова в объединении`)}>
                              Вернуть
                            </button>
                          </PersonRow>
                        ))}
                      </ul>
                    </li>
                  )}
                </ul>
              )}

              {tab === 'about' && (
                <form
                  className="assoc-form"
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const values = edit || { description: data.description, contacts: data.contacts || '' };
                    if (await act(() => associationsApi.edit(data.id, values), 'Описание сохранено')) setEdit(null);
                  }}
                >
                  <div className="field">
                    <label className="field-label" htmlFor="assoc-desc">Описание</label>
                    <textarea id="assoc-desc" className="textarea" rows={6} maxLength={3000}
                      value={(edit || data).description}
                      onChange={e => setEdit({ ...(edit || { description: data.description, contacts: data.contacts || '' }), description: e.target.value })}
                      placeholder="Чем занимается объединение, когда встречаетесь, кого ждёте" />
                  </div>
                  <div className="field">
                    <label className="field-label" htmlFor="assoc-contacts">Где вас найти</label>
                    <input id="assoc-contacts" className="input" maxLength={200}
                      value={(edit || { contacts: data.contacts || '' }).contacts}
                      onChange={e => setEdit({ ...(edit || { description: data.description, contacts: data.contacts || '' }), contacts: e.target.value })}
                      placeholder="Чат, группа ВК или аудитория, например «Среда, 17:00, ауд. 108»" />
                    <p className="field-hint">Видно всем посетителям страницы.</p>
                  </div>
                  <div>
                    <button type="submit" className="btn btn-primary" disabled={busy || !edit}>
                      {busy && <Loader2 size={16} className="spin-icon" {...ICON} />}Сохранить
                    </button>
                  </div>
                </form>
              )}
            </section>
          )}

          {/* MEETINGS and ANNOUNCEMENTS: for members and leaders */}
          {(isMember || data.can_manage) && (
            <AssociationMeetings associationId={data.id} associationName={data.name} canManage={data.can_manage} />
          )}
          {(isMember || data.can_manage) && (
            <AssociationEvents associationId={data.id} canManage={data.can_manage} />
          )}
          {(isMember || data.can_manage) && (
            <AssociationPosts associationId={data.id} canManage={data.can_manage} members={data.members} />
          )}
        </div>

        <aside className="assoc-aside">
          {/* JOINING */}
          <section className="card assoc-card-block" aria-labelledby="assoc-join">
            <h2 id="assoc-join">{isLeader ? 'Вы руководите объединением' : isMember ? 'Вы в объединении' : 'Вступить'}</h2>
            {!isLoggedIn ? (
              <>
                <p className="assoc-muted">Заявки принимаются от студентов, вошедших через ЭИОС.</p>
                <Link to="/profile" className="btn btn-primary"><LogIn size={16} {...ICON} />Войти через ЭИОС</Link>
              </>
            ) : isLeader || data.can_manage ? (
              <>
                <p className="assoc-muted">Заявки и участники — в «Управлении», собрания — ниже на этой странице, задачи — в разделе «Задачи».</p>
                <div className="assoc-leader-actions">
                  <Link to={`/tasks?new=1&association=${data.id}`} className="btn btn-primary"><Plus size={16} {...ICON} />Поставить задачу</Link>
                  <Link to={`/tasks?tab=managed&association=${data.id}`} className="btn btn-secondary">Задачи объединения</Link>
                </div>
              </>
            ) : isMember ? (
              <>
                <p className="assoc-muted">Руководитель видит вас в списке участников и может написать по вашим контактам из профиля.</p>
                <button type="button" className="btn btn-ghost" disabled={busy}
                  onClick={() => window.confirm(`Выйти из объединения «${data.name}»? Незавершённые задачи объединения и запись на его будущие мероприятия снимутся.`)
                    && act(() => associationsApi.leave(data.id), 'Вы вышли из объединения')}>
                  Выйти из объединения
                </button>
              </>
            ) : isPending ? (
              <>
                <p className="assoc-status"><Clock size={16} {...ICON} />Заявка отправлена. Руководитель рассмотрит её и примет решение.</p>
                <button type="button" className="btn btn-secondary" disabled={busy}
                  onClick={() => act(() => associationsApi.leave(data.id), 'Заявка отозвана')}>
                  Отозвать заявку
                </button>
              </>
            ) : (
              <form
                className="assoc-form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (await act(() => associationsApi.apply(data.id, note.trim()), 'Заявка отправлена')) setNote('');
                }}
              >
                {data.my_status === 'rejected' && <p className="assoc-muted">Прошлую заявку отклонили — можно подать новую.</p>}
                {data.my_status === 'removed' && <p className="assoc-muted">Руководитель исключил вас из объединения. Вернуть может только он — напишите ему.</p>}
                <div className="field">
                  <label className="field-label" htmlFor="assoc-note">Пара слов о себе <span className="assoc-muted">(необязательно)</span></label>
                  <textarea id="assoc-note" className="textarea" rows={3} maxLength={300} value={note}
                    onChange={e => setNote(e.target.value)} placeholder="Например: умею монтировать видео" />
                </div>
                <button type="submit" className="btn btn-primary btn-block" disabled={busy || data.my_status === 'removed'}>Подать заявку</button>
                <p className="field-hint">
                  Руководитель увидит ваши ФИО, группу и контакты из <Link to="/profile">профиля</Link>.
                </p>
              </form>
            )}
          </section>

          {/* LEADERS */}
          <section className="card assoc-card-block" aria-labelledby="assoc-leaders">
            <h2 id="assoc-leaders">{data.leaders.length > 1 ? 'Руководители' : 'Руководитель'}</h2>
            {data.leaders.length === 0 ? (
              data.listed_leader ? (
                <ul className="assoc-leaders">
                  <li>
                    <span className="assoc-person-name">{data.listed_leader}</span>
                    <span className="assoc-muted">Ещё не на портале: контакты появятся, когда руководитель войдёт.</span>
                  </li>
                </ul>
              ) : <p className="assoc-muted">Руководитель скоро появится на портале.</p>
            ) : (
              <ul className="assoc-leaders">
                {data.leaders.map(l => (
                  <li key={l.user_id}>
                    <span className="assoc-person-name">{l.full_name}</span>
                    {isLoggedIn
                      ? <ContactLinks vk={l.vk_url} max={l.max_contact} name={l.full_name}
                          empty={<span className="assoc-muted">Контакты пока не указаны</span>} />
                      : <span className="assoc-muted">Контакты видны после входа</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
};

export default AssociationDetail;
