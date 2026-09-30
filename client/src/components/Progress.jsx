import React from 'react';
import { Link } from 'react-router-dom';
import {
  PartyPopper, HandHeart, Users, Clock, NotebookPen, MessageCircle, Handshake, Megaphone, Trophy, Lock, ArrowRight,
} from 'lucide-react';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const ICONS = { PartyPopper, HandHeart, Users, Clock, NotebookPen, MessageCircle, Handshake, Megaphone };
// Bronze, silver, gold
export const TIERS = [null, { label: 'Бронза', hue: 'orange' }, { label: 'Серебро', hue: 'slate' }, { label: 'Золото', hue: 'amber' }];

const plural = (n, [one, few, many]) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
};
export const bits = (n) => `${n} ${plural(n, ['бит', 'бита', 'бит'])}`;

/** Level, points and the way to the next level */
export const LevelCard = ({ data, compact = false }) => {
  const { level } = data;
  const span = level.next_at ? level.next_at - level.from : 1;
  const done = level.next_at ? Math.min(1, (data.points - level.from) / span) : 1;
  return (
    <div className={`level-card ${compact ? 'is-compact' : ''}`}>
      <span className="level-badge" aria-hidden="true"><Trophy size={compact ? 20 : 26} {...ICON} /></span>
      <div className="level-text">
        <p className="level-title">
          <span className="level-name">{level.title}</span>
          <span className="level-index tabular">уровень {level.index}</span>
        </p>
        <p className="level-points tabular">
          <strong>{bits(data.points)}</strong> заработано · в этом семестре {data.semester_points}
          {data.balance && <> · <Link to="/shop" className="level-wallet">на счёте {data.balance.available}</Link></>}
        </p>
        <div className="progress level-progress" role="progressbar" aria-label="До следующего уровня"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(done * 100)}>
          <div className="progress-value" style={{ transform: `scaleX(${done})` }} />
        </div>
        <p className="level-next">
          {level.next_title ? <>До «{level.next_title}» — {bits(level.next_at - data.points)}</> : 'Высший уровень — вы легенда'}
        </p>
      </div>
    </div>
  );
};

const BadgeTile = ({ b }) => {
  const Icon = ICONS[b.icon] || Trophy;
  const tier = TIERS[b.level];
  const share = b.next ? Math.min(1, b.value / b.next) : 1;
  return (
    <li className={`badge-tile ${tier ? `hue-${tier.hue} is-earned` : 'is-locked'}`}>
      <span className="badge-tile-icon" aria-hidden="true">
        {tier ? <Icon size={22} {...ICON} /> : <Lock size={18} {...ICON} />}
      </span>
      <span className="badge-tile-text">
        <span className="badge-tile-title">{b.title}</span>
        <span className="badge-tile-tier">{tier ? tier.label : 'Ещё не получено'}</span>
        {b.next !== null ? (
          <>
            <span className="badge-tile-hint">{b.hint}</span>
            <span className="progress badge-tile-progress" aria-label={`${b.value} из ${b.next}`}>
              <span className="progress-value" style={{ transform: `scaleX(${share})` }} />
            </span>
            <span className="badge-tile-count tabular">{b.value} из {b.next}</span>
          </>
        ) : <span className="badge-tile-hint">Все ступени пройдены</span>}
      </span>
    </li>
  );
};

/** All badges: earned ones in their tier color, the rest with the way to them */
export const BadgeGrid = ({ badges }) => {
  const sorted = [...badges].sort((a, b) => b.level - a.level || (b.next ? b.value / b.next : 1) - (a.next ? a.value / a.next : 1));
  return <ul className="badge-grid">{sorted.map(b => <BadgeTile key={b.id} b={b} />)}</ul>;
};

/** How points are earned, so it is clear what counts */
export const PointsRules = ({ rules, caps }) => (
  <details className="points-rules">
    <summary>За что начисляются биты</summary>
    <ul>
      <li>Мероприятие — {rules.event}, волонтёром — {rules.volunteer} (мероприятий объединений — до {caps.association_events} за семестр, института — без лимита)</li>
      <li>Собрание объединения (отмечено присутствие) — {rules.meeting}, до {caps.meetings} за семестр</li>
      <li>Задача объединения, принятая руководителем, вовремя — {rules.task_on_time}, с опозданием — {rules.task_late}; до {caps.tasks} задач за семестр</li>
      <li>Запись ДЗ для группы — {rules.homework} (до {caps.homework} за семестр)</li>
      <li>Ответ на форуме — {rules.answer} (до {caps.answer} за семестр), ответ выбран лучшим — ещё {rules.solution}</li>
      <li>Проведённое мероприятие объединения (пришли хотя бы трое) — {rules.organized}, до {caps.organized} за семестр</li>
    </ul>
    <p>Считается только подтверждённое: присутствие отмечают организаторы, задачу принимает руководитель, лучший ответ выбирает автор вопроса.
      Задача засчитывается, только если у неё был срок, её поставил другой человек и она висела хотя бы 12 часов — мелкими задачками не накрутить.
      Личные задачи баллов не дают. Биты тратятся в <Link to="/shop">магазине</Link>, призы трайбов добавляются к ним.</p>
  </details>
);

/** Dashboard: level and the badge closest to being earned */
export const ProgressMini = ({ data }) => {
  const next = [...data.badges].filter(b => b.next !== null)
    .sort((a, b) => (b.value / b.next) - (a.value / a.next))[0];
  return (
    <section className="card dash-card hue-amber dash-progress" aria-labelledby="progress-title">
      <div className="dash-card-head">
        <h2 id="progress-title">Мои достижения</h2>
        <Link to="/profile#achievements" className="dash-card-link">Все<ArrowRight size={16} {...ICON} /></Link>
      </div>
      <LevelCard data={data} compact />
      {next && (
        <p className="dash-progress-next">
          Ближе всего: <strong>{next.title}</strong>{TIERS[next.level + 1] ? ` (${TIERS[next.level + 1].label.toLowerCase()})` : ''} — {next.value} из {next.next}
        </p>
      )}
    </section>
  );
};
