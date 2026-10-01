import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, MessageSquare, ThumbsUp, ThumbsDown, Send, CheckCircle2, LogIn, Trash2, SearchX
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { forumApi } from '../services/api';
import Avatar from '../components/Avatar';

const ICON = { strokeWidth: 1.75 };

const QuestionDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, isLoggedIn, canModerate } = useAuth();
  const toast = useToast();

  const [question, setQuestion] = useState(null);
  const [answers, setAnswers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [replyText, setReplyText] = useState('');
  const [submittingReply, setSubmittingReply] = useState(false);

  // ── Load Question Detail & Answers from Backend API ────────────────────────
  const loadQuestionData = useCallback(async () => {
    setLoading(true);
    try {
      const [qData, aData] = await Promise.all([
        forumApi.getQuestionDetail(id),
        forumApi.getAnswers(id)
      ]);
      setQuestion(qData);
      setAnswers(Array.isArray(aData) ? aData : []);
    } catch (err) {
      console.warn('[QuestionDetail] Failed to load detail:', err.message);
      toast.show(err.message || 'Ошибка загрузки вопроса', 'warning');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadQuestionData();
  }, [loadQuestionData]);

  // Role badge helper
  const getRoleBadge = (role) => {
    if (role === 'admin') return <span className="badge badge-accent">Админ</span>;
    if (role === 'moderator') return <span className="badge badge-warning">Модератор</span>;
    return null;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    try {
      return new Date(dateStr).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
    } catch {
      return dateStr;
    }
  };

  // Safe author name helper (format login if full_name is username)
  const formatAuthorName = (name, username) => {
    if (!name || name === username || /^\d{2}-[a-zа-я]+-\d+/i.test(name)) {
      return `Студент ${name || username || ''}`;
    }
    return name;
  };

  // Voting on the main question
  const handleVoteQuestion = async (type) => {
    if (!isLoggedIn) {
      toast.show('Войдите через ЭИОС КГУ, чтобы голосовать', 'warning');
      return;
    }
    const voteType = type === 'like' ? 1 : -1;
    try {
      await forumApi.vote(id, voteType);
      setQuestion(prev => {
        if (!prev) return prev;
        const prevUserVote = prev.user_vote || 0;
        let diff = 0;
        let nextVote = voteType;
        if (prevUserVote === voteType) {
          diff = -voteType;
          nextVote = 0;
        } else if (prevUserVote !== 0) {
          diff = voteType * 2;
        } else {
          diff = voteType;
        }
        return {
          ...prev,
          votes_count: (prev.votes_count || 0) + diff,
          user_vote: nextVote
        };
      });
    } catch (err) {
      toast.show(err.message || 'Ошибка при голосовании', 'warning');
    }
  };

  const handleDeleteAnswer = async (answerId) => {
    if (!window.confirm('Удалить этот ответ?')) return;
    try {
      await forumApi.deleteAnswer(answerId);
      setAnswers(prev => prev.filter(a => a.id !== answerId));
      setQuestion(prev => prev ? { ...prev, answers_count: Math.max((prev.answers_count || 1) - 1, 0) } : prev);
      toast.show('Ответ удалён', 'info');
    } catch (err) {
      toast.show(err.message || 'Ошибка удаления ответа', 'warning');
    }
  };

  const handleToggleSolution = async (answerId) => {
    try {
      const res = await forumApi.toggleSolution(answerId);
      // Only one answer can be the solution: the server unmarks the others.
      setAnswers(prev => prev.map(a => ({ ...a, is_solution: a.id === answerId ? res.is_solution : (res.is_solution ? false : a.is_solution) })));
    } catch (err) {
      toast.show(err.message || 'Не удалось отметить решение', 'warning');
    }
  };

  // Submit new answer via API
  const handleSendReply = async (e) => {
    e.preventDefault();
    if (!replyText.trim()) return;

    setSubmittingReply(true);
    try {
      const createdAns = await forumApi.postAnswer(id, replyText.trim());
      setAnswers(prev => [...prev, createdAns]);
      setQuestion(prev => prev ? { ...prev, answers_count: (prev.answers_count || 0) + 1 } : prev);
      setReplyText('');
      toast.show('Ответ опубликован', 'success');
    } catch (err) {
      toast.show(err.message || 'Ошибка отправки ответа', 'warning');
    } finally {
      setSubmittingReply(false);
    }
  };

  // Ctrl/Cmd + Enter sends the reply from the textarea
  const handleReplyKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && e.currentTarget.form) {
      e.preventDefault();
      e.currentTarget.form.requestSubmit();
    }
  };

  const backButton = (
    <button type="button" onClick={() => navigate('/forum')} className="btn btn-ghost btn-sm qd-back">
      <ArrowLeft size={18} {...ICON} /> Все вопросы
    </button>
  );

  if (loading) {
    return (
      <div className="container cm-page" aria-busy="true">
        {backButton}
        <div className="card qd-question">
          <span className="skeleton qd-skel-meta" />
          <span className="skeleton qd-skel-title" />
          <span className="skeleton qd-skel-line" />
          <span className="skeleton qd-skel-line qd-skel-short" />
        </div>
        <div className="section">
          <span className="skeleton qd-skel-heading" />
          <div className="qd-answers">
            <div className="qd-answer" aria-hidden="true">
              <span className="skeleton qd-skel-meta" />
              <span className="skeleton qd-skel-line" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!question) {
    return (
      <div className="container cm-page">
        {backButton}
        <div className="empty-state qd-missing">
          <SearchX size={32} {...ICON} aria-hidden="true" />
          <h1 className="cm-empty-title">Вопрос не найден</h1>
          <p>Возможно, его удалили или ссылка неточная. Вернитесь к списку и найдите вопрос через поиск.</p>
          <button type="button" onClick={() => navigate('/forum')} className="btn btn-primary">
            Вернуться на форум
          </button>
        </div>
      </div>
    );
  }

  const isQuestionCreator = user && question.author_id === user.id;
  const rating = question.votes_count || 0;

  return (
    <div className="container cm-page">
      {backButton}

      {/* QUESTION */}
      <article className="card qd-question" aria-labelledby="qd-title">
        <p className="qd-meta">
          <span className="badge">{question.category}</span>
          <span className="qd-author with-avatar">
            <Avatar name={question.author_name} url={question.author_photo_url} size="xs" />
            {formatAuthorName(question.author_name, question.author_username)}
          </span>
          <time className="tabular cm-dot" dateTime={question.created_at}>{formatDate(question.created_at)}</time>
        </p>
        <h1 id="qd-title" className="qd-title">{question.title}</h1>
        <p className="qd-content">{question.content}</p>

        <div className="qd-question-foot">
          <div className="cm-vote cm-vote-row" role="group" aria-label="Оценка вопроса">
            <button
              type="button"
              className="cm-vote-btn"
              data-kind="like"
              aria-pressed={question.user_vote === 1}
              onClick={() => handleVoteQuestion('like')}
              aria-label="Полезный вопрос"
              title="Полезный вопрос"
            >
              <ThumbsUp size={18} {...ICON} />
            </button>
            <span className="cm-vote-count tabular" aria-label={`Рейтинг ${rating}`}>{rating}</span>
            <button
              type="button"
              className="cm-vote-btn"
              data-kind="dislike"
              aria-pressed={question.user_vote === -1}
              onClick={() => handleVoteQuestion('dislike')}
              aria-label="Бесполезный вопрос"
              title="Бесполезный вопрос"
            >
              <ThumbsDown size={18} {...ICON} />
            </button>
          </div>
        </div>
      </article>

      {/* ANSWERS */}
      <section className="section" aria-labelledby="qd-answers-heading">
        <div className="section-header">
          <h2 id="qd-answers-heading">
            Ответы <span className="qd-heading-count tabular">{answers.length}</span>
          </h2>
        </div>

        {answers.length > 0 ? (
          <ul className="qd-answers">
            {answers.map((reply) => {
              const isReplyAuthor = user && reply.author_id === user.id;
              const canDeleteReply = isReplyAuthor || canModerate;
              const canMarkSolution = isQuestionCreator || canModerate;
              return (
                <li key={reply.id} className={`qd-answer ${reply.is_solution ? 'is-solution' : ''}`}>
                  <p className="qd-meta">
                    <span className="qd-author with-avatar">
                      <Avatar name={reply.author_name} url={reply.author_photo_url} size="xs" />
                      {formatAuthorName(reply.author_name)}
                    </span>
                    <time className="tabular cm-dot" dateTime={reply.created_at}>{formatDate(reply.created_at)}</time>
                    {reply.is_solution && (
                      <span className="badge badge-success qd-solution-badge">
                        <CheckCircle2 size={14} {...ICON} aria-hidden="true" /> Решение
                      </span>
                    )}
                  </p>

                  <p className="qd-answer-content">{reply.content}</p>

                  {(canMarkSolution || canDeleteReply) && (
                    <div className="qd-answer-actions">
                      {canMarkSolution && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          aria-pressed={!!reply.is_solution}
                          onClick={() => handleToggleSolution(reply.id)}
                        >
                          <CheckCircle2 size={16} {...ICON} />
                          {reply.is_solution ? 'Снять отметку решения' : 'Отметить как решение'}
                        </button>
                      )}
                      {canDeleteReply && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm btn-icon cm-delete-btn"
                          onClick={() => handleDeleteAnswer(reply.id)}
                          aria-label="Удалить ответ"
                          title="Удалить ответ"
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
        ) : (
          <div className="empty-state">
            <MessageSquare size={32} {...ICON} aria-hidden="true" />
            <h3 className="cm-empty-title">Ответов пока нет</h3>
            <p>
              {isLoggedIn
                ? 'Если знаете ответ, напишите его ниже — это поможет сокурснику.'
                : 'Войдите через ЭИОС, чтобы первым ответить на вопрос.'}
            </p>
          </div>
        )}
      </section>

      {/* REPLY */}
      {isLoggedIn ? (
        <section className="section" aria-labelledby="qd-reply-heading">
          <form onSubmit={handleSendReply} className="card qd-reply">
            <h2 id="qd-reply-heading" className="qd-reply-title">Ваш ответ</h2>
            <div className="field">
              <label htmlFor="qd-reply-text" className="visually-hidden">Текст ответа</label>
              <textarea
                id="qd-reply-text"
                className="textarea"
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                onKeyDown={handleReplyKeyDown}
                disabled={submittingReply}
                required
                aria-describedby="qd-reply-hint"
              />
              <span className="field-hint" id="qd-reply-hint">Ctrl + Enter — отправить</span>
            </div>
            <div className="cm-form-actions">
              <button type="submit" className="btn btn-primary" disabled={submittingReply}>
                <Send size={16} {...ICON} /> {submittingReply ? 'Отправляем…' : 'Отправить ответ'}
              </button>
            </div>
          </form>
        </section>
      ) : (
        <div className="cm-notice qd-gate">
          <LogIn size={20} {...ICON} className="cm-notice-icon" aria-hidden="true" />
          <div className="cm-notice-text">
            <p className="cm-notice-title">Войдите через ЭИОС, чтобы ответить на вопрос</p>
            <p>Читать ответы можно без входа.</p>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => navigate('/profile')}>
            Войти через ЭИОС
          </button>
        </div>
      )}
    </div>
  );
};

export default QuestionDetail;
