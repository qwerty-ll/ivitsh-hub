import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, Plus, MessageSquare, ThumbsUp, ThumbsDown, X, Trash2, LogIn, RefreshCw, Pin, SearchX
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { forumApi } from '../services/api';
import SectionIcon from '../components/SectionIcon';
import { plural } from '../utils/plural';
import Avatar from '../components/Avatar';

// Threads per page of the list
const PAGE = 50;

const ICON = { strokeWidth: 1.75 };
const EASE = [0.16, 1, 0.3, 1];

/** Russian plural: plural(3, ['ответ', 'ответа', 'ответов']) → 'ответа' */
const Forum = () => {
  const navigate = useNavigate();
  const { user, isLoggedIn, canModerate } = useAuth();
  const toast = useToast();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('Все');
  const [isAskModalOpen, setIsAskModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newCategory, setNewCategory] = useState('Учеба');
  const [newText, setNewText] = useState('');
  const [errors, setErrors] = useState({});

  // API-backed state — no localStorage
  const [questions, setQuestions] = useState([]);
  // How many threads match in all (the list loads 50 at a time)
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const askTriggerRef = useRef(null);

  const categories = ['Все', 'Учеба', 'Расписание', 'Общежитие', 'Стипендия', 'Организационное'];

  const loadMore = () => {
    setLoadingMore(true);
    forumApi.getPage(selectedCategory !== 'Все' ? selectedCategory : '', searchQuery.trim(), PAGE, questions.length)
      .then(({ items, total: count }) => {
        setQuestions(prev => [...prev, ...items.filter(q => !prev.some(p => p.id === q.id))]);
        if (count != null) setTotal(count);
      })
      .catch(() => toast.show('Не удалось загрузить ещё вопросы', 'warning'))
      .finally(() => setLoadingMore(false));
  };

  // ── Load questions from API ──────────────────────────────────────────────
  const loadQuestions = useCallback(() => {
    setLoading(true);
    forumApi.getPage(selectedCategory !== 'Все' ? selectedCategory : '', searchQuery.trim(), PAGE)
      .then(({ items, total: count }) => {
        setQuestions(items);
        setTotal(count ?? items.length);
      })
      .catch(err => {
        console.warn('[Forum] Failed to load questions:', err.message);
        toast.show('Не удалось загрузить вопросы форума', 'warning');
      })
      .finally(() => setLoading(false));
  }, [selectedCategory, searchQuery]);

  useEffect(() => {
    // Debounce search to avoid excessive API calls while typing
    const timer = setTimeout(loadQuestions, searchQuery ? 400 : 0);
    return () => clearTimeout(timer);
  }, [loadQuestions]);

  // Ask-question dialog: close on Escape, return focus to the button that opened it
  useEffect(() => {
    if (!isAskModalOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setIsAskModalOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      const trigger = askTriggerRef.current;
      if (trigger && trigger.isConnected) trigger.focus();
    };
  }, [isAskModalOpen]);

  // ── Voting (API) ─────────────────────────────────────────────────────────
  const handleVote = async (id, type, e) => {
    e.stopPropagation();
    if (!isLoggedIn) {
      toast.show('Войдите через ЭИОС КГУ, чтобы голосовать', 'warning');
      return;
    }
    const voteType = type === 'like' ? 1 : -1;
    try {
      await forumApi.vote(id, voteType);
      // Optimistic update for current user's vote + rating
      setQuestions(prev => prev.map(q => {
        if (q.id !== id) return q;
        const prevUserVote = q.user_vote || 0;
        let diff = 0;
        let nextVote = voteType;
        if (prevUserVote === voteType) {
          // Toggle off
          diff = -voteType;
          nextVote = 0;
        } else if (prevUserVote !== 0) {
          // Switch direction
          diff = voteType * 2;
        } else {
          diff = voteType;
        }
        return { ...q, votes_count: (q.votes_count || 0) + diff, user_vote: nextVote };
      }));
    } catch (err) {
      toast.show(err.message || 'Ошибка при голосовании', 'warning');
    }
  };

  // ── Create Question (API) ────────────────────────────────────────────────
  const handleCreateQuestion = async (e) => {
    e.preventDefault();

    const tempErrors = {};
    if (newTitle.trim().length < 10) {
      tempErrors.title = 'Заголовок должен содержать минимум 10 символов';
    } else if (newTitle.length > 300) {
      tempErrors.title = 'Заголовок не должен превышать 300 символов';
    }
    if (newText.trim().length < 20) {
      tempErrors.text = 'Описание должно содержать минимум 20 символов';
    } else if (newText.length > 10000) {
      tempErrors.text = 'Описание не должно превышать 10 000 символов';
    }
    if (Object.keys(tempErrors).length > 0) {
      setErrors(tempErrors);
      const firstInvalid = document.getElementById(tempErrors.title ? 'ask-title' : 'ask-text');
      if (firstInvalid) firstInvalid.focus();
      return;
    }

    setSubmitting(true);
    try {
      const created = await forumApi.createQuestion({
        title: newTitle.trim(),
        category: newCategory,
        content: newText.trim()
      });
      // Normalise API response to UI shape
      setQuestions(prev => [normaliseQuestion(created), ...prev]);
      setTotal(t => t + 1);
      setIsAskModalOpen(false);
      setNewTitle('');
      setNewText('');
      setNewCategory('Учеба');
      setErrors({});
      toast.show('Вопрос опубликован', 'success');
    } catch (err) {
      toast.show(err.message || 'Ошибка при публикации вопроса', 'warning');
    } finally {
      setSubmitting(false);
    }
  };

  // ── Delete Question (API) ───────────────────────────────────────────────────
  const handleDeleteQuestion = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm('Удалить вопрос с форума?')) return;
    try {
      await forumApi.deleteQuestion(id);
      setQuestions(prev => prev.filter(q => q.id !== id));
      setTotal(t => Math.max(0, t - 1));
      toast.show('Вопрос удалён', 'info');
    } catch (err) {
      toast.show(err.message || 'Ошибка удаления вопроса', 'warning');
    }
  };

  const handleTogglePin = async (id, e) => {
    e.stopPropagation();
    try {
      const res = await forumApi.togglePin(id);
      setQuestions(prev => prev.map(q => (q.id === id ? { ...q, is_pinned: res.is_pinned } : q)));
      toast.show(res.is_pinned ? 'Вопрос закреплён' : 'Вопрос откреплён', 'info');
    } catch (err) {
      toast.show(err.message || 'Не удалось закрепить вопрос', 'warning');
    }
  };

  // ── Helpers ──────────────────────────────────────────────────────────────
  /** Normalise API ForumQuestionResponse to a UI-friendly shape */
  const normaliseQuestion = (q) => ({
    ...q,
    // Map API fields to UI fields used in the render
    author: {
      name: q.author_name || 'Студент',
      role: 'student',
      group: '',
      photo: q.author_photo_url || null,
    },
    text: q.content || '',
    rating: q.votes_count ?? 0,
    answersCount: q.answers_count ?? 0,
    userVote: q.user_vote === 1 ? 'like' : q.user_vote === -1 ? 'dislike' : null,
  });

  const normalisedQuestions = questions.map(normaliseQuestion);

  const isOwnPost = (q) => {
    if (!user) return false;
    return q.author_id === user.id;
  };

  const highlightText = (text, query) => {
    if (!query || !text) return text;
    const parts = text.split(new RegExp(`(${query.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&')})`, 'gi'));
    return (
      <span>
        {parts.map((part, index) =>
          part.toLowerCase() === query.toLowerCase()
            ? <mark key={index}>{part}</mark>
            : part
        )}
      </span>
    );
  };

  const getRoleBadge = (role) => {
    if (role === 'admin') return <span className="badge badge-accent">Админ</span>;
    if (role === 'moderator') return <span className="badge badge-warning">Модератор</span>;
    return null;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    try {
      return new Date(dateStr).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
    } catch { return dateStr; }
  };

  const openAskModal = (e) => { askTriggerRef.current = e ? e.currentTarget : null; setIsAskModalOpen(true); setErrors({}); };
  const isFiltered = selectedCategory !== 'Все' || searchQuery.trim() !== '';
  const resetFilters = () => { setSearchQuery(''); setSelectedCategory('Все'); };

  const titleErrorId = 'ask-title-error';
  const textErrorId = 'ask-text-error';

  return (
    <div className="container cm-page">
      <header className="page-header">
        <div className="page-heading">
          <SectionIcon section="forum" size="lg" />
          <div>
            <h1>Форум студентов</h1>
            <p className="page-subtitle">Вопросы об учёбе, расписании и жизни в ИВИТШ — отвечают сокурсники и кураторы.</p>
          </div>
        </div>
        {isLoggedIn && (
          <div className="cm-header-actions">
            <button type="button" className="btn btn-primary" onClick={openAskModal} aria-haspopup="dialog">
              <Plus size={18} {...ICON} /> Задать вопрос
            </button>
          </div>
        )}
      </header>

      {/* AUTH GATE */}
      {!isLoggedIn && (
        <div className="cm-notice">
          <LogIn size={20} {...ICON} className="cm-notice-icon" aria-hidden="true" />
          <div className="cm-notice-text">
            <p className="cm-notice-title">Читать обсуждения можно без входа</p>
            <p>Чтобы задавать вопросы, отвечать и голосовать, войдите через ЭИОС КГУ.</p>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => navigate('/profile')}>
            Войти через ЭИОС
          </button>
        </div>
      )}

      {/* SEARCH + FILTERS */}
      <div className="forum-toolbar">
        <div className="cm-search">
          <label htmlFor="forum-search" className="visually-hidden">Поиск по форуму</label>
          <Search size={18} {...ICON} className="cm-search-icon" aria-hidden="true" />
          <input
            id="forum-search"
            type="search"
            className="input"
            placeholder="Поиск по вопросам"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            autoComplete="off"
          />
        </div>

        <div className="cm-chips" role="group" aria-label="Категория вопросов">
          {categories.map(cat => (
            <button
              key={cat}
              type="button"
              className="chip"
              aria-pressed={selectedCategory === cat}
              onClick={() => setSelectedCategory(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* DISCUSSIONS FEED */}
      <section aria-labelledby="forum-list-heading" aria-busy={loading}>
        <div className="forum-list-head">
          <h2 id="forum-list-heading" className="visually-hidden">Вопросы</h2>
          <p className="forum-count" aria-live="polite">
            {loading ? 'Загружаем вопросы…' : normalisedQuestions.length > 0 && (
              <>
                <span className="tabular">{Math.max(total, normalisedQuestions.length)}</span>{' '}
                {plural(Math.max(total, normalisedQuestions.length), ['вопрос', 'вопроса', 'вопросов'])}
                {isFiltered ? ' по фильтру' : ''}
              </>
            )}
          </p>
          <button
            type="button"
            className="btn btn-ghost btn-sm forum-refresh"
            onClick={loadQuestions}
            disabled={loading}
          >
            <RefreshCw size={16} {...ICON} /> Обновить список
          </button>
        </div>

        {loading ? (
          <ul className="forum-list" aria-label="Загрузка вопросов">
            {[0, 1, 2].map(i => (
              <li key={i} className="forum-row forum-row-skeleton" aria-hidden="true">
                <span className="skeleton forum-skel-vote" />
                <div className="forum-row-main">
                  <span className="skeleton forum-skel-title" />
                  <span className="skeleton forum-skel-line" />
                  <span className="skeleton forum-skel-meta" />
                </div>
              </li>
            ))}
          </ul>
        ) : normalisedQuestions.length > 0 ? (
          <>
          <ul className="forum-list">
            {normalisedQuestions.map((q) => {
              const canDelete = isOwnPost(q) || canModerate;
              const excerpt = (q.text || '').length > 150 ? `${(q.text || '').slice(0, 150)}…` : (q.text || '');
              return (
                <li key={q.id} className={`forum-row ${q.is_pinned ? 'is-pinned' : ''}`}>
                  <div className="cm-vote forum-row-vote" role="group" aria-label="Оценка вопроса">
                    <button
                      type="button"
                      className="cm-vote-btn"
                      data-kind="like"
                      aria-pressed={q.userVote === 'like'}
                      aria-label="Полезный вопрос"
                      title="Полезный вопрос"
                      onClick={(e) => handleVote(q.id, 'like', e)}
                    >
                      <ThumbsUp size={16} {...ICON} />
                    </button>
                    <span className="cm-vote-count tabular" aria-label={`Рейтинг ${q.rating}`}>{q.rating}</span>
                    <button
                      type="button"
                      className="cm-vote-btn"
                      data-kind="dislike"
                      aria-pressed={q.userVote === 'dislike'}
                      aria-label="Бесполезный вопрос"
                      title="Бесполезный вопрос"
                      onClick={(e) => handleVote(q.id, 'dislike', e)}
                    >
                      <ThumbsDown size={16} {...ICON} />
                    </button>
                  </div>

                  <div className="forum-row-main">
                    <div className="forum-row-tags">
                      {q.is_pinned && (
                        <span className="badge badge-accent">
                          <Pin size={12} {...ICON} aria-hidden="true" /> Закреплён
                        </span>
                      )}
                      <span className="badge">{q.category}</span>
                      {q.answersCount === 0 && <span className="badge badge-warning">Ждёт ответа</span>}
                    </div>
                    <h3 className="forum-row-title">
                      <Link to={`/forum/question/${q.id}`}>{highlightText(q.title, searchQuery)}</Link>
                    </h3>
                    {excerpt && <p className="forum-row-excerpt">{highlightText(excerpt, searchQuery)}</p>}
                    <p className="forum-row-meta">
                      <span className="forum-row-author">
                        <Avatar name={q.author.name} url={q.author.photo} size="xs" />
                        {q.author.name}
                        {getRoleBadge(q.author.role)}
                      </span>
                      <time className="tabular cm-dot" dateTime={q.created_at}>{formatDate(q.created_at)}</time>
                      <span className="forum-row-answers cm-dot">
                        <MessageSquare size={14} {...ICON} aria-hidden="true" />
                        <span className="tabular">{q.answersCount}</span>{' '}
                        {plural(q.answersCount, ['ответ', 'ответа', 'ответов'])}
                      </span>
                    </p>
                  </div>

                  {(canModerate || canDelete) && (
                    <div className="forum-row-actions">
                      {canModerate && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm btn-icon cm-pin-btn"
                          aria-pressed={!!q.is_pinned}
                          onClick={(e) => handleTogglePin(q.id, e)}
                          aria-label={q.is_pinned ? 'Открепить вопрос' : 'Закрепить вопрос'}
                          title={q.is_pinned ? 'Открепить вопрос' : 'Закрепить вопрос'}
                        >
                          <Pin size={16} {...ICON} />
                        </button>
                      )}
                      {canDelete && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm btn-icon cm-delete-btn"
                          onClick={(e) => handleDeleteQuestion(q.id, e)}
                          aria-label="Удалить вопрос"
                          title="Удалить вопрос"
                        >
                          <Trash2 size={16} {...ICON} />
                        </button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {total > questions.length && (
            <button type="button" className="btn btn-secondary forum-more" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? 'Загружаем…' : `Показать ещё (${total - questions.length})`}
            </button>
          )}
          </>
        ) : isFiltered ? (
          <div className="empty-state">
            <SearchX size={32} {...ICON} aria-hidden="true" />
            <h3 className="cm-empty-title">Ничего не найдено</h3>
            <p>
              {searchQuery.trim()
                ? <>По запросу «{searchQuery.trim()}»{selectedCategory !== 'Все' ? ` в категории «${selectedCategory}»` : ''} вопросов нет. </>
                : <>В категории «{selectedCategory}» пока нет вопросов. </>}
              Измените запрос или посмотрите все категории.
            </p>
            <button type="button" className="btn btn-secondary" onClick={resetFilters}>Сбросить фильтры</button>
          </div>
        ) : (
          <div className="empty-state">
            <MessageSquare size={32} {...ICON} aria-hidden="true" />
            <h3 className="cm-empty-title">На форуме пока нет вопросов</h3>
            <p>
              {isLoggedIn
                ? 'Задайте первый вопрос — сокурсники и кураторы помогут разобраться.'
                : 'Войдите через ЭИОС, чтобы задать первый вопрос.'}
            </p>
            {isLoggedIn ? (
              <button type="button" className="btn btn-primary" onClick={openAskModal}>
                <Plus size={18} {...ICON} /> Задать вопрос
              </button>
            ) : (
              <button type="button" className="btn btn-secondary" onClick={() => navigate('/profile')}>
                Войти через ЭИОС
              </button>
            )}
          </div>
        )}
      </section>

      {/* CREATE QUESTION DIALOG */}
      <AnimatePresence>
        {isAskModalOpen && (
          <motion.div
            className="modal-overlay"
            onClick={() => setIsAskModalOpen(false)}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: EASE }}
          >
            <motion.div
              className="modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="ask-dialog-title"
              onClick={(e) => e.stopPropagation()}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.24, ease: EASE }}
            >
              <button
                type="button"
                className="modal-close"
                onClick={() => setIsAskModalOpen(false)}
                aria-label="Закрыть окно"
              >
                <X size={20} {...ICON} />
              </button>
              <h2 id="ask-dialog-title">Новый вопрос</h2>

              <form onSubmit={handleCreateQuestion} className="cm-form" noValidate>
                <div className="field">
                  <label className="field-label" htmlFor="ask-title">Заголовок</label>
                  <input
                    id="ask-title"
                    type="text"
                    className="input"
                    value={newTitle}
                    onChange={(e) => { setNewTitle(e.target.value); if (errors.title) setErrors(prev => ({ ...prev, title: null })); }}
                    maxLength={300}
                    required
                    autoFocus
                    aria-invalid={errors.title ? 'true' : 'false'}
                    aria-describedby={`ask-title-hint${errors.title ? ` ${titleErrorId}` : ''}`}
                  />
                  <div className="cm-field-meta">
                    {errors.title
                      ? <span className="field-error" id={titleErrorId}>{errors.title}</span>
                      : <span className="field-hint" id="ask-title-hint">Коротко опишите суть, от 10 символов</span>}
                    <span className="cm-counter tabular" aria-hidden="true">{newTitle.length} / 300</span>
                  </div>
                </div>

                <div className="field">
                  <label className="field-label" htmlFor="ask-category">Категория</label>
                  <select id="ask-category" className="select" value={newCategory} onChange={(e) => setNewCategory(e.target.value)}>
                    <option value="Учеба">Учеба</option>
                    <option value="Расписание">Расписание</option>
                    <option value="Общежитие">Общежитие</option>
                    <option value="Стипендия">Стипендия</option>
                    <option value="Организационное">Организационное</option>
                  </select>
                </div>

                <div className="field">
                  <label className="field-label" htmlFor="ask-text">Подробное описание</label>
                  <textarea
                    id="ask-text"
                    className="textarea cm-textarea-lg"
                    value={newText}
                    onChange={(e) => { setNewText(e.target.value); if (errors.text) setErrors(prev => ({ ...prev, text: null })); }}
                    maxLength={10000}
                    required
                    aria-invalid={errors.text ? 'true' : 'false'}
                    aria-describedby={`ask-text-hint${errors.text ? ` ${textErrorId}` : ''}`}
                  />
                  <div className="cm-field-meta">
                    {errors.text
                      ? <span className="field-error" id={textErrorId}>{errors.text}</span>
                      : <span className="field-hint" id="ask-text-hint">Что уже пробовали и что осталось непонятным, от 20 символов</span>}
                    <span className="cm-counter tabular" aria-hidden="true">{newText.length} / 10 000</span>
                  </div>
                </div>

                <div className="cm-form-actions">
                  <button type="button" className="btn btn-ghost" onClick={() => setIsAskModalOpen(false)}>
                    Отменить
                  </button>
                  <button type="submit" className="btn btn-primary" disabled={submitting}>
                    {submitting ? 'Публикуем…' : 'Опубликовать вопрос'}
                  </button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Forum;
