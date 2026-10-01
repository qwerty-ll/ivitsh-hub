import React, { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Clock, MapPin, Handshake, Users, HandHeart, LogIn, Pencil, Trash2, FileSpreadsheet, Loader2, Star,
  UserPlus, UsersRound, X, CheckCircle2,
} from 'lucide-react';
import Attachments from '../components/Attachments';
import ContactLinks from '../components/ContactLinks';
import EventForm from '../components/EventForm';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { adminApi, associationsApi, eventsApi } from '../services/api';
import { ROLE_LABEL, SOURCE_LABEL, eventWhen, isFull, isOver, organizerOf, seatsText } from '../utils/events';
import Avatar from '../components/Avatar';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

/** One click to register as a participant or a volunteer, or to cancel */
const Registration = ({ e, onChange }) => {
  const { isLoggedIn } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const act = (fn, done) => async () => {
    setBusy(true);
    try {
      onChange(await fn());
      if (done) toast.show(done, 'success');
    } catch (err) {
      toast.show(err.message || 'Не получилось', 'error');
    } finally {
      setBusy(false);
    }
  };

  if (!isLoggedIn) {
    return (
      <>
        <p className="assoc-muted">Записаться можно после входа через ЭИОС.</p>
        <Link to="/profile" className="btn btn-primary"><LogIn size={16} {...ICON} />Войти через ЭИОС</Link>
      </>
    );
  }
  if (isOver(e)) {
    return e.my_role ? (
      <p className="event-status"><CheckCircle2 size={18} {...ICON} />
        {e.my_attended === false ? 'Организаторы отметили, что вас не было.' : `Вы участвовали: ${ROLE_LABEL[e.my_role].toLowerCase()}.`}
      </p>
    ) : <p className="assoc-muted">Мероприятие прошло.</p>;
  }
  // Once it has started the list is fixed: no signing up, leaving or switching roles
  if (e.started) {
    return e.my_role
      ? <p className="event-status"><CheckCircle2 size={18} {...ICON} />Идёт. Вы: {ROLE_LABEL[e.my_role].toLowerCase()}</p>
      : <p className="assoc-muted">Мероприятие уже идёт — запись закрыта.</p>;
  }
  if (e.i_was_removed) {
    return <p className="assoc-muted">Организаторы убрали вас из списка. Записаться снова можно только по их приглашению.</p>;
  }
  const volunteersWanted = e.volunteer_limit !== null;
  if (e.my_role && e.my_source !== 'self') {
    return (
      <>
        <p className="event-status"><CheckCircle2 size={18} {...ICON} />Организаторы записали вас: {ROLE_LABEL[e.my_role].toLowerCase()}</p>
        <p className="assoc-muted">Роль меняют организаторы. Если не сможете прийти — напишите им.</p>
      </>
    );
  }
  if (e.my_role) {
    const other = e.my_role === 'participant' ? 'volunteer' : 'participant';
    return (
      <>
        <p className="event-status"><CheckCircle2 size={18} {...ICON} />Вы записаны: {ROLE_LABEL[e.my_role].toLowerCase()}</p>
        <p className="assoc-muted">Сменить роль или отменить запись можно до начала мероприятия.</p>
        <div className="assoc-leader-actions">
          {e.registration_open && (other === 'participant' || volunteersWanted) && !isFull(e, other) && (
            <button type="button" className="btn btn-secondary" disabled={busy}
              onClick={act(() => eventsApi.register(e.id, other), `Теперь вы ${ROLE_LABEL[other].toLowerCase()}`)}>
              {other === 'volunteer' ? 'Стать волонтёром' : 'Стать участником'}
            </button>
          )}
          <button type="button" className="btn btn-ghost cal-danger" disabled={busy}
            onClick={() => window.confirm('Отменить запись?') && act(() => eventsApi.unregister(e.id), 'Запись отменена')()}>
            Отменить запись
          </button>
        </div>
      </>
    );
  }
  if (!e.registration_open) return <p className="assoc-muted">Запись закрыта: участников записывают организаторы.</p>;
  return (
    <div className="assoc-leader-actions">
      <button type="button" className="btn btn-primary" disabled={busy || isFull(e, 'participant')}
        onClick={act(() => eventsApi.register(e.id, 'participant'), 'Вы записаны — мероприятие появилось в календаре')}>
        {busy && <Loader2 size={16} className="spin-icon" {...ICON} />}
        {isFull(e, 'participant') ? 'Мест нет' : 'Записаться'}
      </button>
      {volunteersWanted && (
        <button type="button" className="btn btn-secondary" disabled={busy || isFull(e, 'volunteer')}
          onClick={act(() => eventsApi.register(e.id, 'volunteer'), 'Вы записаны волонтёром')}>
          <HandHeart size={16} {...ICON} />{isFull(e, 'volunteer') ? 'Волонтёров хватает' : 'Волонтёром'}
        </button>
      )}
    </div>
  );
};

/** The short survey after the event: 1–5 and a comment */
const Feedback = ({ e, onChange }) => {
  const toast = useToast();
  const [rating, setRating] = useState(e.my_feedback?.rating || 0);
  const [text, setText] = useState(e.my_feedback?.text || '');
  const [saving, setSaving] = useState(false);
  const submit = async (ev) => {
    ev.preventDefault();
    if (!rating) return;
    setSaving(true);
    try {
      onChange(await eventsApi.feedback(e.id, rating, text));
      toast.show('Спасибо за отзыв!', 'success');
    } catch (err) {
      toast.show(err.message || 'Не удалось отправить', 'error');
    } finally {
      setSaving(false);
    }
  };
  return (
    <section className="card assoc-card-block" id="feedback" aria-labelledby="feedback-title">
      <h2 id="feedback-title">{e.my_feedback ? 'Ваша оценка' : 'Оцените мероприятие'}</h2>
      <form className="task-form" onSubmit={submit}>
        <fieldset className="event-stars">
          <legend className="visually-hidden">Оценка от 1 до 5</legend>
          {[1, 2, 3, 4, 5].map(n => (
            <label key={n} className={`event-star ${n <= rating ? 'is-on' : ''}`}>
              <input type="radio" name="rating" value={n} checked={rating === n} onChange={() => setRating(n)} className="visually-hidden" />
              <Star size={28} {...ICON} /><span className="visually-hidden">{n}</span>
            </label>
          ))}
        </fieldset>
        <label className="visually-hidden" htmlFor="feedback-text">Отзыв</label>
        <textarea id="feedback-text" className="textarea" rows={3} maxLength={2000} value={text} onChange={ev => setText(ev.target.value)}
          placeholder="Что понравилось, что улучшить (необязательно). Организаторы видят отзывы без имён." />
        <button type="submit" className="btn btn-primary" disabled={!rating || saving}>{e.my_feedback ? 'Обновить' : 'Отправить'}</button>
      </form>
    </section>
  );
};

/** Organizers add people by name: a leader from the association's members, the administration anyone */
const AddPeople = ({ e, onChange }) => {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState('participant');
  const [q, setQ] = useState('');
  const [options, setOptions] = useState([]);
  const [chosen, setChosen] = useState([]);
  const [groups, setGroups] = useState('');
  const registered = new Set(e.registrations.map(r => r.user_id));

  useEffect(() => {
    if (!open || isAdmin || !e.association) return;
    associationsApi.get(e.association.id).then(a => setOptions((a.members || []).map(m => ({ id: m.user_id, full_name: m.full_name, group_number: m.group_number }))))
      .catch(() => setOptions([]));
  }, [open, isAdmin, e.association]);

  useEffect(() => {
    if (!open || !isAdmin) return undefined;
    if (q.trim().length < 2) { setOptions([]); return undefined; }
    const t = setTimeout(() => adminApi.searchUsers(q.trim()).then(r => setOptions(r || [])).catch(() => setOptions([])), 250);
    return () => clearTimeout(t);
  }, [q, open, isAdmin]);

  const add = async () => {
    try {
      onChange(await eventsApi.addPeople(e.id, chosen, role));
      toast.show(`Записано: ${chosen.length}`, 'success');
      setChosen([]);
    } catch (err) {
      toast.show(err.message || 'Не удалось записать', 'error');
    }
  };
  const addGroups = async () => {
    const list = groups.split(/[,;\n]/).map(g => g.trim()).filter(Boolean);
    if (!list.length) return;
    try {
      const res = await eventsApi.addGroups(e.id, list, role);
      toast.show(`Записано: ${res.added}${res.already ? `, уже были: ${res.already}` : ''}${res.unknown_groups.length ? `. Никто ещё не входил из: ${res.unknown_groups.join(', ')}` : ''}`, 'success', 6000);
      setGroups('');
      onChange(await eventsApi.get(e.id));
    } catch (err) {
      toast.show(err.message || 'Не удалось записать группы', 'error');
    }
  };

  if (!open) {
    return <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(true)}><UserPlus size={16} {...ICON} />Записать людей</button>;
  }
  const shown = options.filter(o => !registered.has(o.id));
  return (
    <div className="event-add">
      <div className="event-add-head">
        <div className="segmented" role="group" aria-label="Роль">
          <button type="button" className={`segmented-item ${role === 'participant' ? 'active' : ''}`} aria-pressed={role === 'participant'} onClick={() => setRole('participant')}>Участниками</button>
          {e.volunteer_limit !== null && (
            <button type="button" className={`segmented-item ${role === 'volunteer' ? 'active' : ''}`} aria-pressed={role === 'volunteer'} onClick={() => setRole('volunteer')}>Волонтёрами</button>
          )}
        </div>
        <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => setOpen(false)} aria-label="Закрыть"><X size={16} {...ICON} /></button>
      </div>
      {isAdmin && (
        <input className="input" placeholder="Фамилия, логин или группа" value={q} onChange={ev => setQ(ev.target.value)} aria-label="Найти студента" />
      )}
      {!isAdmin && <p className="task-optional">Руководитель записывает участников своего объединения по одному. Целую группу записывает администрация.</p>}
      {shown.length > 0 ? (
        <ul className="task-people">
          {shown.map(o => (
            <li key={o.id}>
              <label className="task-person">
                <input type="checkbox" checked={chosen.includes(o.id)}
                  onChange={() => setChosen(c => (c.includes(o.id) ? c.filter(x => x !== o.id) : [...c, o.id]))} />
                <span>{o.full_name}</span>
                {o.group_number && <span className="task-optional tabular">{o.group_number}</span>}
              </label>
            </li>
          ))}
        </ul>
      ) : <p className="task-optional">{isAdmin ? (q.trim().length < 2 ? 'Начните вводить фамилию.' : 'Никого не нашли.') : 'Все участники объединения уже записаны.'}</p>}
      <button type="button" className="btn btn-primary btn-sm" disabled={!chosen.length} onClick={add}>Записать ({chosen.length})</button>
      {isAdmin && (
        <div className="event-groups">
          <label className="field-label" htmlFor="event-groups">Записать академические группы целиком</label>
          <div className="event-groups-row">
            <input id="event-groups" className="input" placeholder="24-ИСбо-1, 24-ИСбо-2" value={groups} onChange={ev => setGroups(ev.target.value)} />
            <button type="button" className="btn btn-secondary btn-sm" disabled={!groups.trim()} onClick={addGroups}><UsersRound size={16} {...ICON} />Записать группы</button>
          </div>
          <p className="task-optional">Попадут все студенты этих групп, которые хоть раз входили на портал.</p>
        </div>
      )}
    </div>
  );
};

/** Organizers: the list, attendance after the start, removing people, the Excel export */
const Participants = ({ e, onChange }) => {
  const toast = useToast();
  const started = new Date(e.starts_at) <= new Date();
  const [present, setPresent] = useState(() => new Set(e.registrations.filter(r => r.attended).map(r => r.user_id)));
  useEffect(() => setPresent(new Set(e.registrations.filter(r => r.attended).map(r => r.user_id))), [e.registrations]);
  const marked = e.registrations.some(r => r.attended !== null);

  const saveAttendance = async () => {
    try {
      onChange(await eventsApi.attendance(e.id, [...present]));
      toast.show('Присутствие сохранено', 'success');
    } catch (err) {
      toast.show(err.message || 'Не удалось сохранить', 'error');
    }
  };
  const run = (fn, done) => async () => {
    try {
      onChange(await fn());
      if (done) toast.show(done, 'success');
    } catch (err) {
      toast.show(err.message || 'Не удалось', 'error');
    }
  };
  const remove = (r) => {
    if (!window.confirm(`Убрать ${r.full_name} из списка? Сам(а) записаться снова не сможет — только если вы вернёте.`)) return;
    run(() => eventsApi.removePerson(e.id, r.user_id))();
  };

  return (
    <section className="card assoc-card-block" aria-labelledby="regs-title">
      <div className="assoc-manage-head">
        <h2 id="regs-title">Записавшиеся <span className="dash-card-meta tabular">{e.registrations.length}</span></h2>
        {e.registrations.length > 0 && (
          <a className="btn btn-ghost btn-sm" href={eventsApi.exportHref(e.id)} download><FileSpreadsheet size={16} {...ICON} />Excel</a>
        )}
      </div>
      {started && e.registrations.length > 0 && <p className="task-optional">Отметьте, кто пришёл: отметки попадут в сводку ПГАС и статистику.</p>}
      {e.registrations.length === 0 ? <p className="assoc-muted">Пока никто не записался.</p> : (
        <ul className="list event-regs">
          {e.registrations.map(r => (
            <li key={r.user_id} className="event-reg">
              {started ? (
                <label className="task-person">
                  <input type="checkbox" checked={present.has(r.user_id)}
                    onChange={() => setPresent(p => { const n = new Set(p); if (n.has(r.user_id)) n.delete(r.user_id); else n.add(r.user_id); return n; })} />
                  <span className="with-avatar"><Avatar name={r.full_name} url={r.photo_url} size="xs" />{r.full_name}</span>
                </label>
              ) : <span className="event-reg-name with-avatar"><Avatar name={r.full_name} url={r.photo_url} size="xs" />{r.full_name}</span>}
              <span className="assoc-person-meta">
                {r.group_number && <span className="tabular">{r.group_number}</span>}
                <label className="visually-hidden" htmlFor={`role-${r.user_id}`}>Роль: {r.full_name}</label>
                <select id={`role-${r.user_id}`} className="select event-role-select" value={r.role}
                  onChange={ev => run(() => eventsApi.setRole(e.id, r.user_id, ev.target.value), 'Роль изменена')()}>
                  <option value="participant">{ROLE_LABEL.participant}</option>
                  <option value="volunteer" disabled={e.volunteer_limit === null}>{ROLE_LABEL.volunteer}</option>
                </select>
                <span>записал(а): {SOURCE_LABEL[r.source] || r.source}</span>
                {r.attended === false && <span className="badge badge-danger">не был(а)</span>}
              </span>
              <ContactLinks vk={r.vk_url} max={r.max_contact} name={r.full_name} />
              <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => remove(r)} aria-label={`Убрать ${r.full_name}`} title="Убрать из списка">
                <X size={16} {...ICON} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="assoc-leader-actions">
        {started && e.registrations.length > 0 && (
          <button type="button" className="btn btn-primary btn-sm" onClick={saveAttendance}>
            {marked ? 'Обновить' : 'Сохранить'} присутствие: {present.size} из {e.registrations.length}
          </button>
        )}
        <AddPeople e={e} onChange={onChange} />
      </div>
      {e.removed.length > 0 && (
        <div className="event-removed">
          <h3 className="cal-subhead">Убраны из списка</h3>
          <p className="task-optional">Сами записаться снова не могут. Верните их или разрешите записаться самостоятельно.</p>
          <ul className="list event-regs">
            {e.removed.map(p => (
              <li key={p.id} className="event-reg">
                <span className="event-reg-name">{p.full_name}</span>
                <span className="assoc-person-meta">{p.group_number && <span className="tabular">{p.group_number}</span>}</span>
                <span className="event-removed-actions">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={run(() => eventsApi.addPeople(e.id, [p.id]), `${p.full_name} снова в списке`)}>Вернуть</button>
                  {!isOver(e) && <button type="button" className="btn btn-ghost btn-sm" onClick={run(() => eventsApi.allowAgain(e.id, p.id), 'Теперь может записаться сам(а)')}>Разрешить записаться</button>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {e.feedback && e.feedback.count > 0 && (
        <div className="event-feedback-summary">
          <h3 className="cal-subhead">Отзывы: {e.feedback.average} из 5 ({e.feedback.count})</h3>
          <ul>
            {e.feedback.comments.map((c, i) => <li key={i}><span className="tabular">{'★'.repeat(c.rating)}</span> {c.text}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
};

const EventDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { hash } = useLocation();
  const toast = useToast();
  const [e, setE] = useState(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);

  const load = useCallback(() => {
    eventsApi.get(id).then(setE).catch(err => setError(err.message || 'Мероприятие не найдено'));
  }, [id]);
  useEffect(load, [load]);
  useEffect(() => {
    if (e && hash === '#feedback') document.getElementById('feedback')?.scrollIntoView({ behavior: 'smooth' });
  }, [e, hash]);

  const remove = async () => {
    if (!window.confirm('Удалить мероприятие вместе со списком и документами?')) return;
    try {
      await eventsApi.remove(e.id);
      toast.show('Мероприятие удалено', 'success');
      navigate('/events');
    } catch (err) {
      toast.show(err.message || 'Не удалось удалить', 'error');
    }
  };

  if (error) {
    return (
      <div className="container">
        <Link to="/events" className="assoc-back"><ArrowLeft size={16} {...ICON} />Все мероприятия</Link>
        <div className="empty-state"><p>{error}</p></div>
      </div>
    );
  }
  if (!e) return <div className="container"><span className="skeleton" style={{ height: '16rem' }} /></div>;

  const showDocs = e.can_manage || e.my_role;

  return (
    <div className="container event-page">
      <Link to="/events" className="assoc-back"><ArrowLeft size={16} {...ICON} />Все мероприятия</Link>
      <header className="event-hero hue-red">
        <p className="event-card-top">
          <span className={`badge ${e.scope === 'institute' ? 'badge-accent' : ''}`}>{e.scope === 'institute' ? 'Мероприятие института' : 'Мероприятие объединения'}</span>
          {!e.registration_open && <span className="badge">Запись закрыта</span>}
        </p>
        <h1>{e.title}</h1>
        <ul className="cal-facts">
          <li><Clock size={16} {...ICON} />{eventWhen(e)}</li>
          {e.place && <li><MapPin size={16} {...ICON} />{e.place}</li>}
          <li><Handshake size={16} {...ICON} />
            {e.association ? <Link to={`/associations/${e.association.id}`}>{organizerOf(e)}</Link> : organizerOf(e)}
          </li>
        </ul>
      </header>

      <div className="assoc-layout">
        <div className="assoc-main">
          {e.description && (
            <section className="card assoc-card-block"><p className="cal-text">{e.description}</p></section>
          )}
          {e.can_feedback && <Feedback key={e.my_feedback ? 'edit' : 'new'} e={e} onChange={setE} />}
          {showDocs && (e.attachments.length > 0 || e.can_manage) && (
            <section className="card assoc-card-block" aria-labelledby="docs-title">
              <h2 id="docs-title">Документы</h2>
              {e.can_manage && <p className="task-optional">Распоряжения, освобождения, благодарности — их скачают все записавшиеся.</p>}
              <Attachments owner="events" ownerId={e.id} items={e.attachments} canAdd={e.can_manage} onChange={load} />
            </section>
          )}
          {e.can_manage && <Participants e={e} onChange={setE} />}
        </div>

        <aside className="assoc-aside">
          <section className="card assoc-card-block" aria-labelledby="reg-title">
            <h2 id="reg-title">Запись</h2>
            <p className="event-seats tabular">
              <span><Users size={16} {...ICON} />Участники: {seatsText(e.participants, e.participant_limit)}</span>
              {e.volunteer_limit !== null && <span><HandHeart size={16} {...ICON} />Волонтёры: {seatsText(e.volunteers, e.volunteer_limit)}</span>}
            </p>
            <Registration e={e} onChange={setE} />
          </section>
          {e.can_manage && (
            <section className="card assoc-card-block">
              <h2>Управление</h2>
              <div className="assoc-leader-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setEditing(true)}><Pencil size={16} {...ICON} />Изменить</button>
                <button type="button" className="btn btn-ghost cal-danger" onClick={remove}><Trash2 size={16} {...ICON} />Удалить</button>
              </div>
            </section>
          )}
        </aside>
      </div>

      <EventForm open={editing} event={e} onClose={() => setEditing(false)}
        onSaved={(saved) => { setEditing(false); setE(saved); toast.show('Сохранено', 'success'); }} />
    </div>
  );
};

export default EventDetail;
