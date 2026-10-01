import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Crown, Timer, Users, Plus, Minus, Flag, Loader2, ChevronDown, LogIn, Trophy, Gift } from 'lucide-react';
import SectionIcon from '../components/SectionIcon';
import Modal from '../components/Modal';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { tribesApi } from '../services/api';
import { bits } from '../components/Progress';
import { plural } from '../utils/plural';
import Avatar from '../components/Avatar';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const DEFAULT_NAMES = ['Альфа', 'Бета', 'Гамма', 'Дельта', 'Эпсилон', 'Зета', 'Эта', 'Тета'];
const fmt = (d) => new Date(`${d}T00:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
const daysLeft = (end) => Math.max(0, Math.ceil((new Date(`${end}T23:59:59`) - new Date()) / 864e5));
/** One tribe in the standings: place, name in its color, points and the way to the leader */
const TribeRow = ({ tribe, leader, mine, open, onToggle }) => (
  <li className={`tribe-row hue-${tribe.color} ${mine ? 'is-mine' : ''}`}>
    <button type="button" className="tribe-row-main" aria-expanded={open} onClick={onToggle}>
      <span className={`tribe-place tabular ${tribe.rank <= 3 && tribe.points > 0 ? `is-top-${tribe.rank}` : ''}`}>{tribe.rank}</span>
      <span className="tribe-name-block">
        <span className="tribe-name">
          {tribe.name}
          {mine && <span className="badge badge-accent">Ваш трайб</span>}
        </span>
        <span className="tribe-meta">
          <span><Users size={14} {...ICON} />{tribe.members}</span>
          <span>в среднем {tribe.average}</span>
          {tribe.awards !== 0 && <span>бонусы {tribe.awards > 0 ? '+' : ''}{tribe.awards}</span>}
          {tribe.master && <span><Crown size={14} {...ICON} />{tribe.master}</span>}
        </span>
        <span className="progress tribe-bar" aria-hidden="true">
          <span className="progress-value" style={{ transform: `scaleX(${leader > 0 ? Math.max(0, tribe.points) / leader : 0})` }} />
        </span>
      </span>
      <span className="tribe-points tabular">{tribe.points}<span>{plural(Math.abs(tribe.points), ['очко', 'очка', 'очков'])}</span></span>
      <ChevronDown size={18} className="dash-chevron" {...ICON} />
    </button>
    {open && (
      <ol className="tribe-top">
        {tribe.top.length === 0 ? <li className="task-optional">Пока никто не набрал очков.</li> : tribe.top.map((p, i) => (
          <li key={`${p.full_name}-${i}`}>
            <span className="tabular tribe-top-n">{i + 1}</span>
            <span className="tribe-top-name with-avatar"><Avatar name={p.full_name} url={p.photo_url} size="xs" />{p.full_name}</span>
            {p.group_number && <span className="task-optional tabular">{p.group_number}</span>}
            <span className="tabular tribe-top-points">{p.points}</span>
          </li>
        ))}
      </ol>
    )}
  </li>
);

const TournamentForm = ({ open, onClose, onCreated }) => {
  const toast = useToast();
  const today = new Date().toISOString().slice(0, 10);
  const inMonth = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
  const [form, setForm] = useState({ title: '', starts_on: today, ends_on: inMonth, count: 4, names: DEFAULT_NAMES.slice(0, 4), groups: '', prize_1: 50, prize_2: 30, prize_3: 15, auto_join: true });
  const [saving, setSaving] = useState(false);
  const setCount = (n) => setForm(f => ({ ...f, count: n, names: Array.from({ length: n }, (_, i) => f.names[i] || DEFAULT_NAMES[i]) }));
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const t = await tribesApi.create({
        title: form.title.trim() || 'Турнир трайбов', starts_on: form.starts_on, ends_on: form.ends_on,
        tribe_names: form.names, groups: form.groups.split(/[,;\n]/).map(g => g.trim()).filter(Boolean),
        auto_join: form.auto_join, prize_1: Number(form.prize_1), prize_2: Number(form.prize_2), prize_3: Number(form.prize_3),
      });
      onCreated(t);
    } catch (err) {
      toast.show(err.message || 'Не удалось создать турнир', 'error');
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal open={open} onClose={onClose} title="Новый турнир трайбов" titleId="tournament-form-title" className="task-form-modal">
      <form className="task-form" onSubmit={submit}>
        <div className="field">
          <label className="field-label" htmlFor="t-title">Название</label>
          <input id="t-title" className="input" maxLength={200} value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Осенний турнир трайбов" />
        </div>
        <div className="meeting-when event-when">
          <div className="field"><label className="field-label" htmlFor="t-start">Начало</label>
            <input id="t-start" className="input" type="date" value={form.starts_on} onChange={e => setForm({ ...form, starts_on: e.target.value })} /></div>
          <div className="field"><label className="field-label" htmlFor="t-end">Конец</label>
            <input id="t-end" className="input" type="date" value={form.ends_on} onChange={e => setForm({ ...form, ends_on: e.target.value })} /></div>
        </div>
        <fieldset className="field">
          <legend className="field-label">Сколько трайбов</legend>
          <div className="segmented" role="group" aria-label="Сколько трайбов">
            {[2, 3, 4, 5, 6].map(n => (
              <button key={n} type="button" className={`segmented-item ${form.count === n ? 'active' : ''}`} aria-pressed={form.count === n} onClick={() => setCount(n)}>{n}</button>
            ))}
          </div>
        </fieldset>
        <div className="tribe-names">
          {form.names.map((n, i) => (
            <input key={i} className="input" maxLength={40} value={n} aria-label={`Название трайба ${i + 1}`}
              onChange={e => setForm(f => ({ ...f, names: f.names.map((x, j) => (j === i ? e.target.value : x)) }))} />
          ))}
        </div>
        <div className="field">
          <label className="field-label" htmlFor="t-groups">Группы <span className="task-optional">(пусто — все студенты)</span></label>
          <input id="t-groups" className="input" value={form.groups} onChange={e => setForm({ ...form, groups: e.target.value })} placeholder="24-ИСбо-1, 25-ИСбо-1" />
        </div>
        <fieldset className="field">
          <legend className="field-label">Призы в битах каждому участнику трайба за 1, 2 и 3 место</legend>
          <div className="meeting-when">
            {['prize_1', 'prize_2', 'prize_3'].map((k, i) => (
              <input key={k} className="input" type="number" min={0} max={10000} value={form[k]} aria-label={`${i + 1} место`}
                onChange={e => setForm({ ...form, [k]: e.target.value })} />
            ))}
          </div>
        </fieldset>
        <label className="task-person">
          <input type="checkbox" checked={form.auto_join} onChange={e => setForm({ ...form, auto_join: e.target.checked })} />
          <span>Новички во время турнира попадают в самый маленький трайб</span>
        </label>
        <p className="task-optional">Турнир создаётся черновиком. Студенты распределятся по трайбам случайно и поровну, когда вы нажмёте «Запустить».</p>
        <div className="cm-form-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Отменить</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving && <Loader2 size={16} className="spin-icon" {...ICON} />}Создать</button>
        </div>
      </form>
    </Modal>
  );
};

/** Administration: points for a tribe or a penalty */
const AwardForm = ({ tribes, onDone }) => {
  const toast = useToast();
  const [form, setForm] = useState({ tribe: tribes[0]?.id || '', points: 20, reason: '', sign: 1 });
  const submit = async (e) => {
    e.preventDefault();
    if (!form.reason.trim()) { toast.show('Напишите, за что', 'error'); return; }
    try {
      onDone(await tribesApi.award(form.tribe, form.sign * Math.abs(Number(form.points)), form.reason.trim()));
      toast.show(form.sign > 0 ? 'Очки начислены' : 'Штраф записан', 'success');
      setForm(f => ({ ...f, reason: '' }));
    } catch (err) {
      toast.show(err.message || 'Не получилось', 'error');
    }
  };
  return (
    <form className="tribe-award" onSubmit={submit}>
      <select className="select" value={form.tribe} onChange={e => setForm({ ...form, tribe: e.target.value })} aria-label="Трайб">
        {tribes.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
      </select>
      <div className="segmented" role="group" aria-label="Начислить или снять">
        <button type="button" className={`segmented-item ${form.sign > 0 ? 'active' : ''}`} aria-pressed={form.sign > 0} onClick={() => setForm({ ...form, sign: 1 })}><Plus size={16} {...ICON} />Бонус</button>
        <button type="button" className={`segmented-item ${form.sign < 0 ? 'active' : ''}`} aria-pressed={form.sign < 0} onClick={() => setForm({ ...form, sign: -1 })}><Minus size={16} {...ICON} />Штраф</button>
      </div>
      <input className="input tribe-award-points" type="number" min={1} max={10000} value={form.points} aria-label="Очков"
        onChange={e => setForm({ ...form, points: e.target.value })} />
      <input className="input" maxLength={200} value={form.reason} placeholder="За что: победа в хакатоне, челлендж недели…" aria-label="За что"
        onChange={e => setForm({ ...form, reason: e.target.value })} />
      <button type="submit" className="btn btn-primary">Записать</button>
    </form>
  );
};

const Tribes = () => {
  const { isLoggedIn, isAdmin } = useAuth();
  const toast = useToast();
  const [t, setT] = useState(undefined);
  const [past, setPast] = useState([]);
  const [open, setOpen] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!isLoggedIn) return;
    tribesApi.current().then(r => setT(r.tournament)).catch(() => setT(null));
    tribesApi.tournaments().then(r => setPast(r || [])).catch(() => setPast([]));
  }, [isLoggedIn]);
  useEffect(load, [load]);

  const act = async (fn, done, confirm) => {
    if (confirm && !window.confirm(confirm)) return;
    setBusy(true);
    try {
      const res = await fn();
      if (res && res.id) setT(res); else load();
      if (done) toast.show(done, 'success');
      tribesApi.tournaments().then(r => setPast(r || [])).catch(() => {});
    } catch (err) {
      toast.show(err.message || 'Не получилось', 'error');
    } finally {
      setBusy(false);
    }
  };

  const header = (
    <header className="page-header tasks-header">
      <div className="page-heading">
        <SectionIcon section="tribes" size="lg" />
        <div>
          <h1>Трайбы</h1>
          <p className="page-subtitle">Турнир команд: все студенты случайно и поровну делятся на трайбы, каждый приносит своему трайбу очки своей активностью.</p>
        </div>
      </div>
      {isAdmin && <button type="button" className="btn btn-primary" onClick={() => setFormOpen(true)}><Plus size={16} {...ICON} />Новый турнир</button>}
    </header>
  );

  if (!isLoggedIn) {
    return (
      <div className="container">{header}
        <div className="empty-state"><p>Турнир виден после входа.</p><Link to="/profile" className="btn btn-primary"><LogIn size={16} {...ICON} />Войти через ЭИОС</Link></div>
      </div>
    );
  }

  const drafts = past.filter(p => p.status === 'draft');
  const leader = t ? Math.max(1, ...t.tribes.map(x => x.points)) : 1;
  const myTribe = t?.tribes.find(x => x.id === t.my_tribe_id);

  return (
    <div className="container tribes-page">
      {header}

      {isAdmin && drafts.map(d => (
        <div key={d.id} className="card tribe-draft">
          <div>
            <strong>Черновик: {d.title}</strong>
            <p className="task-optional">{fmt(d.starts_on)} — {fmt(d.ends_on)} · трайбов: {d.tribes}</p>
          </div>
          <div className="assoc-leader-actions">
            <button type="button" className="btn btn-primary" disabled={busy}
              onClick={() => act(() => tribesApi.start(d.id), 'Турнир запущен: студенты распределены по трайбам', 'Распределить студентов по трайбам и запустить турнир?')}>
              <Flag size={16} {...ICON} />Запустить
            </button>
            <button type="button" className="btn btn-ghost cal-danger" disabled={busy} onClick={() => act(() => tribesApi.remove(d.id), 'Черновик удалён')}>Удалить</button>
          </div>
        </div>
      ))}

      {t === undefined ? <span className="skeleton cal-skeleton" /> : !t ? (
        <div className="empty-state">
          <SectionIcon section="tribes" size="lg" />
          <h2 className="cm-empty-title">Турнира пока нет</h2>
          <p>Когда администрация запустит турнир, здесь появятся трайбы, таблица и ваш вклад.</p>
        </div>
      ) : (
        <>
          <section className={`tribe-hero ${myTribe ? `hue-${myTribe.color}` : 'hue-violet'}`} aria-labelledby="tournament-title">
            <div className="tribe-hero-text">
              <p className="tribe-hero-status">
                {t.status === 'active'
                  ? <><Timer size={16} {...ICON} />Идёт · {daysLeft(t.ends_on)} {plural(daysLeft(t.ends_on), ['день', 'дня', 'дней'])} до финала</>
                  : <><Trophy size={16} {...ICON} />Турнир завершён</>}
              </p>
              <h2 id="tournament-title">{t.title}</h2>
              <p className="tribe-hero-dates">{fmt(t.starts_on)} — {fmt(t.ends_on)}</p>
              {myTribe ? (
                <p className="tribe-hero-mine">
                  Вы в трайбе <strong>«{myTribe.name}»</strong>{t.tribes.some(x => x.points !== 0) ? ` — ${myTribe.rank} место` : ''}.
                  {t.my_points !== null && (t.my_points > 0
                    ? <> Ваш вклад: <strong className="tabular">{t.my_points}</strong> {plural(t.my_points, ['очко', 'очка', 'очков'])}{t.my_rank_in_tribe ? `, ${t.my_rank_in_tribe}-й в трайбе` : ''}.</>
                    : <> Первые очки — за мероприятие, собрание или ДЗ группы.</>)}
                </p>
              ) : <p className="tribe-hero-mine">Вы не участвуете в этом турнире.</p>}
            </div>
            <ul className="tribe-prizes" aria-label="Призы">
              {t.prizes.map((p, i) => p > 0 && (
                <li key={i} className={`tribe-prize is-top-${i + 1}`}><Gift size={16} {...ICON} />{i + 1} место — {bits(p)} каждому</li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="standings-title">
            <div className="section-header"><h2 id="standings-title">Таблица</h2></div>
            <ol className="tribe-table">
              {t.tribes.map(tr => (
                <TribeRow key={tr.id} tribe={tr} leader={leader} mine={tr.id === t.my_tribe_id}
                  open={open === tr.id} onToggle={() => setOpen(o => (o === tr.id ? null : tr.id))} />
              ))}
            </ol>
            <p className="task-optional tribe-updated">Очки пересчитываются раз в несколько минут.</p>
          </section>

          {t.can_manage && t.status === 'active' && (
            <section className="card tribe-admin" aria-labelledby="tribe-admin-title">
              <h2 id="tribe-admin-title">Управление турниром</h2>
              <AwardForm tribes={t.tribes} onDone={setT} />
              <button type="button" className="btn btn-secondary" disabled={busy}
                onClick={() => act(() => tribesApi.finish(t.id), 'Турнир завершён, призы начислены', 'Завершить турнир? Места зафиксируются, участники трайбов-призёров получат биты.')}>
                <Trophy size={16} {...ICON} />Завершить и наградить
              </button>
            </section>
          )}

          <div className="tribe-bottom">
            <section className="card" aria-labelledby="awards-title">
              <h2 id="awards-title" className="cal-subhead">Бонусы и штрафы</h2>
              {t.awards.length === 0 ? <p className="cal-empty">Пока не было.</p> : (
                <ul className="list tribe-awards">
                  {t.awards.map((a, i) => (
                    <li key={i} className={`hue-${a.color}`}>
                      <span className={`tribe-award-points tabular ${a.points < 0 ? 'is-minus' : ''}`}>{a.points > 0 ? '+' : ''}{a.points}</span>
                      <span><strong>{a.tribe}</strong> · {a.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="card" aria-labelledby="rules-title">
              <h2 id="rules-title" className="cal-subhead">Как трайб набирает очки</h2>
              <ul className="tribe-rules">
                <li>Всё, за что вы получаете биты, идёт и в копилку трайба: мероприятия, волонтёрство, собрания, задачи вовремя, ДЗ группы, помощь на форуме.</li>
                <li>Администрация начисляет трайбам бонусы за хакатоны и челленджи и может оштрафовать.</li>
                <li>Лучший по вкладу в трайбе — его мастер (корона).</li>
                <li>В конце каждый участник трайбов-призёров получает биты для <Link to="/shop">магазина</Link>.</li>
              </ul>
            </section>
          </div>
        </>
      )}

      {past.filter(p => p.status === 'finished' && (!t || p.id !== t.id)).length > 0 && (
        <section className="tribe-history" aria-labelledby="history-title">
          <h2 id="history-title" className="cal-subhead">Прошлые турниры</h2>
          <ul className="list">
            {past.filter(p => p.status === 'finished' && (!t || p.id !== t.id)).map(p => (
              <li key={p.id} className="tribe-history-row">
                <span>{p.title} <span className="task-optional">{fmt(p.starts_on)} — {fmt(p.ends_on)}</span></span>
                {p.winner && <span className={`badge hue-${p.winner.color} tribe-winner`}><Crown size={14} {...ICON} />{p.winner.name}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <TournamentForm open={formOpen} onClose={() => setFormOpen(false)}
        onCreated={() => { setFormOpen(false); toast.show('Черновик турнира создан — запустите его, когда будете готовы', 'success'); load(); }} />
    </div>
  );
};

export default Tribes;
