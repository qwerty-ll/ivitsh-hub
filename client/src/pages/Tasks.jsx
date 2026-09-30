import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, LogIn, MessageSquare, Paperclip, Users, CalendarClock, RotateCw } from 'lucide-react';
import SectionIcon from '../components/SectionIcon';
import TaskForm from '../components/TaskForm';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { associationsApi, tasksApi } from '../services/api';
import { STATUSES, dueInfo } from '../utils/tasks';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const DONE_SHOWN = 8;

// A card on my board; association tasks cannot be marked "Готово" by their assignee
const TaskCard = ({ card, onMove, onDragStart }) => {
  const due = dueInfo(card.due_at, card.my_status);
  const isPersonal = !card.association;
  return (
    <article
      className={`task-card ${isPersonal ? `hue-${card.color || 'blue'} task-card-personal` : ''}`}
      draggable
      onDragStart={(e) => { e.dataTransfer.setData('text/plain', String(card.id)); onDragStart(card); }}
    >
      <Link to={`/tasks/${card.id}`} className="task-card-title">{card.title}</Link>
      <p className="task-card-meta">
        {isPersonal ? <span className="task-chip">Личная</span> : <span className="task-chip">{card.association.name}</span>}
        {due && <span className={`task-due task-due-${due.tone || 'plain'}`}><CalendarClock size={14} {...ICON} />{due.label}</span>}
      </p>
      <div className="task-card-foot">
        <span className="task-counts">
          {card.comments_count > 0 && <span title="Комментарии"><MessageSquare size={14} {...ICON} />{card.comments_count}</span>}
          {card.attachments_count > 0 && <span title="Файлы и ссылки"><Paperclip size={14} {...ICON} />{card.attachments_count}</span>}
          {card.assignees_count > 1 && <span title="Исполнителей"><Users size={14} {...ICON} />{card.assignees_count}</span>}
        </span>
        <label className="visually-hidden" htmlFor={`task-status-${card.id}`}>Статус задачи «{card.title}»</label>
        <select id={`task-status-${card.id}`} className="select task-status-select" value={card.my_status}
          onChange={e => onMove(card, e.target.value)}>
          {STATUSES.map(s => (
            // "Готово" on association tasks is the leader's call after review
            <option key={s.id} value={s.id} disabled={s.id === 'done' && !isPersonal && card.my_status !== 'done'}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
    </article>
  );
};

const MyBoard = ({ cards, filter, onMove, reload }) => {
  const [mobileStatus, setMobileStatus] = useState('todo');
  const [dragged, setDragged] = useState(null);
  const [dropTarget, setDropTarget] = useState(null);
  const [showAllDone, setShowAllDone] = useState(false);

  const shown = cards.filter(c => filter === 'all' || (filter === 'personal' ? !c.association : String(c.association?.id) === filter));
  const byStatus = Object.fromEntries(STATUSES.map(s => [s.id, shown.filter(c => c.my_status === s.id)]));

  if (cards.length === 0) {
    return (
      <div className="empty-state">
        <SectionIcon section="tasks" size="lg" />
        <h2 className="cm-empty-title">Задач пока нет</h2>
        <p>Здесь появятся задачи от руководителей ваших объединений. Себе задачу можно поставить кнопкой «Новая задача».</p>
        <button type="button" className="btn btn-secondary" onClick={reload}><RotateCw size={16} {...ICON} />Обновить</button>
      </div>
    );
  }

  return (
    <>
      {/* Phone: one column at a time */}
      <div className="segmented task-mobile-tabs" role="group" aria-label="Колонка">
        {STATUSES.map(s => (
          <button key={s.id} type="button" className={`segmented-item ${mobileStatus === s.id ? 'active' : ''}`}
            aria-pressed={mobileStatus === s.id} onClick={() => setMobileStatus(s.id)}>
            {s.label} <span className="tabular task-tab-count">{byStatus[s.id].length}</span>
          </button>
        ))}
      </div>

      <div className="task-board">
        {STATUSES.map(s => {
          const list = s.id === 'done' && !showAllDone ? byStatus.done.slice(-DONE_SHOWN) : byStatus[s.id];
          return (
            <section
              key={s.id}
              className={`task-column ${mobileStatus === s.id ? 'is-mobile-active' : ''} ${dropTarget === s.id ? 'is-drop' : ''}`}
              aria-labelledby={`col-${s.id}`}
              onDragOver={(e) => { if (dragged) { e.preventDefault(); setDropTarget(s.id); } }}
              onDragLeave={() => setDropTarget(null)}
              onDrop={(e) => {
                e.preventDefault();
                setDropTarget(null);
                if (dragged && dragged.my_status !== s.id) onMove(dragged, s.id);
                setDragged(null);
              }}
            >
              <h2 className="task-column-head" id={`col-${s.id}`}>
                {s.label}<span className="badge tabular">{byStatus[s.id].length}</span>
              </h2>
              <div className="task-column-body">
                {list.length === 0 && <p className="task-column-empty">{s.id === 'review' ? 'Сдайте задачу — она окажется здесь' : 'Пусто'}</p>}
                {list.map(card => <TaskCard key={card.id} card={card} onMove={onMove} onDragStart={setDragged} />)}
                {s.id === 'done' && byStatus.done.length > DONE_SHOWN && (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowAllDone(v => !v)}>
                    {showAllDone ? 'Скрыть старые' : `Показать все (${byStatus.done.length})`}
                  </button>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </>
  );
};

const Managed = ({ tasks, filter }) => {
  const shown = tasks.filter(t => filter === 'all' || String(t.association.id) === filter);
  if (shown.length === 0) {
    return (
      <div className="empty-state">
        <h2 className="cm-empty-title">Вы ещё не ставили задач</h2>
        <p>Нажмите «Новая задача» и выберите своё объединение в поле «Для кого».</p>
      </div>
    );
  }
  return (
    <ul className="task-managed">
      {shown.map(t => {
        const due = dueInfo(t.due_at, t.counts.done === t.total ? 'done' : 'todo');
        const handedIn = t.counts.review + t.counts.done;
        return (
          <li key={t.id}>
            <Link to={`/tasks/${t.id}`} className="task-managed-row">
              <span className="task-managed-main">
                <span className="task-card-title">{t.title}</span>
                <span className="task-card-meta">
                  <span className="task-chip">{t.association.name}</span>
                  {due && <span className={`task-due task-due-${due.tone || 'plain'}`}><CalendarClock size={14} {...ICON} />{due.label}</span>}
                </span>
              </span>
              <span className="task-managed-progress">
                {t.counts.review > 0 && <span className="badge badge-warning">Ждут проверки: {t.counts.review}</span>}
                <span className="tabular task-managed-count">Сдали {handedIn} из {t.total}</span>
                <span className="progress" aria-hidden="true">
                  <span className="progress-value" style={{ transform: `scaleX(${t.total ? t.counts.done / t.total : 0})` }} />
                </span>
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
};

const Tasks = () => {
  const { isLoggedIn } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'managed' ? 'managed' : 'my';
  const [cards, setCards] = useState(null);
  const [managed, setManaged] = useState([]);
  const [leads, setLeads] = useState([]);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState(params.get('association') || 'all');
  const [formOpen, setFormOpen] = useState(params.get('new') === '1');

  const load = useCallback(() => {
    if (!isLoggedIn) return;
    setError('');
    tasksApi.my().then(res => setCards(res || [])).catch(e => { setError(e.message || 'Не удалось загрузить задачи'); setCards([]); });
    associationsApi.mine().then(rows => {
      const led = (rows || []).filter(r => r.role === 'leader' && r.status === 'approved');
      setLeads(led);
      if (led.length) tasksApi.managed().then(res => setManaged(res || [])).catch(() => setManaged([]));
    }).catch(() => setLeads([]));
  }, [isLoggedIn]);
  useEffect(load, [load]);

  const move = async (card, status) => {
    if (status === 'done' && card.association) {
      toast.show('«Готово» ставит руководитель после проверки. Отправьте задачу «На проверку».', 'info', 4000);
      return;
    }
    const before = cards;
    setCards(prev => prev.map(c => (c.id === card.id ? { ...c, my_status: status } : c)));
    try {
      await tasksApi.setStatus(card.id, status);
      if (status === 'review') toast.show('Отправлено на проверку руководителю', 'success');
    } catch (e) {
      setCards(before);
      toast.show(e.message || 'Не удалось изменить статус', 'error');
    }
  };

  const toReview = managed.reduce((n, t) => n + t.counts.review, 0);

  // Filter choices: personal + associations present on the current tab
  const filterOptions = useMemo(() => {
    const source = tab === 'managed' ? managed.map(t => t.association) : (cards || []).map(c => c.association).filter(Boolean);
    const unique = [...new Map(source.map(a => [a.id, a])).values()].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
    return unique;
  }, [tab, managed, cards]);

  const setTab = (next) => {
    const p = new URLSearchParams(params);
    if (next === 'managed') p.set('tab', 'managed'); else p.delete('tab');
    setParams(p, { replace: true });
    setFilter('all');
  };

  if (!isLoggedIn) {
    return (
      <div className="container tasks-page">
        <header className="page-header">
          <div className="page-heading">
            <SectionIcon section="tasks" size="lg" />
            <div>
              <h1>Задачи</h1>
              <p className="page-subtitle">Задачи от руководителей объединений и личные дела с дедлайнами.</p>
            </div>
          </div>
        </header>
        <div className="empty-state">
          <h2 className="cm-empty-title">Задачи видны после входа</h2>
          <p>Войдите через ЭИОС, чтобы видеть задачи своих объединений и ставить себе личные.</p>
          <Link to="/profile" className="btn btn-primary"><LogIn size={16} {...ICON} />Войти через ЭИОС</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="container tasks-page">
      <header className="page-header tasks-header">
        <div className="page-heading">
          <SectionIcon section="tasks" size="lg" />
          <div>
            <h1>Задачи</h1>
            <p className="page-subtitle">Задачи объединений и личные дела. Статус меняется в карточке — или перетащите её в другую колонку.</p>
          </div>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setFormOpen(true)}><Plus size={16} {...ICON} />Новая задача</button>
      </header>

      <div className="tasks-toolbar">
        {leads.length > 0 && (
          <div className="segmented" role="group" aria-label="Какие задачи показать">
            <button type="button" className={`segmented-item ${tab === 'my' ? 'active' : ''}`} aria-pressed={tab === 'my'} onClick={() => setTab('my')}>Мои задачи</button>
            <button type="button" className={`segmented-item ${tab === 'managed' ? 'active' : ''}`} aria-pressed={tab === 'managed'} onClick={() => setTab('managed')}>
              Поставленные
              {toReview > 0 && <span className="badge badge-warning tabular" title="Ждут проверки">{toReview}</span>}
            </button>
          </div>
        )}
        <div className="tasks-filter">
          <label className="visually-hidden" htmlFor="tasks-filter">Фильтр по объединению</label>
          <select id="tasks-filter" className="select" value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="all">Все задачи</option>
            {tab === 'my' && <option value="personal">Личные</option>}
            {filterOptions.map(a => <option key={a.id} value={String(a.id)}>{a.name}</option>)}
          </select>
        </div>
      </div>

      {error && <p className="field-error" role="alert">{error}</p>}
      {cards === null ? (
        <div className="task-board" aria-busy="true">
          {STATUSES.map(s => <div key={s.id} className="task-column"><span className="skeleton" style={{ height: '6rem' }} /></div>)}
        </div>
      ) : tab === 'managed' ? (
        <Managed tasks={managed} filter={filter} />
      ) : (
        <MyBoard cards={cards} filter={filter} onMove={move} reload={load} />
      )}

      <TaskForm
        open={formOpen}
        presetAssociation={params.get('new') === '1' ? params.get('association') : null}
        onClose={() => {
          setFormOpen(false);
          if (params.get('new')) { const p = new URLSearchParams(params); p.delete('new'); setParams(p, { replace: true }); }
        }}
        onCreated={(task) => {
          setFormOpen(false);
          toast.show(task.association ? `Задача поставлена: ${task.assignees.length} ${task.assignees.length === 1 ? 'исполнитель' : 'исполнителей'}` : 'Задача добавлена', 'success');
          navigate(`/tasks/${task.id}`);
        }}
      />
    </div>
  );
};

export default Tasks;
