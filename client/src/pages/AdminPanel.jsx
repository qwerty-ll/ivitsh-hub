import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import DOMPurify from 'dompurify';
import { Pencil, Trash2, Save, RefreshCw, Lock, LockOpen, CircleAlert } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { adminApi } from '../services/api';
import SectionIcon from '../components/SectionIcon';

const ICON = { size: 16, strokeWidth: 1.75, 'aria-hidden': true };

const ROLE_LABELS = { student: 'Студент', moderator: 'Модератор', admin: 'Администратор' };

const formatLongDate = (value) => (value
  ? new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
  : '');

// Moves keyboard focus to the first field of an editor after "Редактировать" and brings the form into view.
const focusEditor = (fieldId) => {
  window.requestAnimationFrame(() => {
    const field = document.getElementById(fieldId);
    if (!field) return;
    field.focus({ preventScroll: true });
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    field.closest('.admin-editor')?.scrollIntoView({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
  });
};

const Field = ({ id, label, required, hint, className = '', children }) => (
  <div className={`field ${className}`.trim()}>
    <label className="field-label" htmlFor={id}>
      {label}
      {required && <span className="admin-required" aria-hidden="true"> *</span>}
    </label>
    {children}
    {hint && <p className="field-hint" id={`${id}-hint`}>{hint}</p>}
  </div>
);

const Toolbar = ({ id, title, description, children }) => (
  <div className="admin-toolbar">
    <div className="admin-toolbar-text">
      <h2 id={id}>{title}</h2>
      {description && <p>{description}</p>}
    </div>
    {children && <div className="admin-toolbar-actions">{children}</div>}
  </div>
);

const RefreshButton = ({ onClick, disabled }) => (
  <button type="button" className="btn btn-secondary btn-sm" onClick={onClick} disabled={disabled}>
    <RefreshCw {...ICON} /> Обновить список
  </button>
);

const ListSkeleton = () => (
  <div className="admin-skeleton" role="status">
    <span className="visually-hidden">Загрузка списка</span>
    {[0, 1, 2].map(i => (
      <div key={i} className="admin-skeleton-row" aria-hidden="true">
        <span className="skeleton admin-skeleton-line" />
        <span className="skeleton admin-skeleton-line admin-skeleton-line-short" />
      </div>
    ))}
  </div>
);

const LoadError = ({ message, onRetry }) => (
  <div className="admin-error" role="alert">
    <CircleAlert {...ICON} />
    <p>Ошибка загрузки: {message}</p>
    <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
      <RefreshCw {...ICON} /> Повторить загрузку
    </button>
  </div>
);

const RowActions = ({ label, onEdit, onDelete, deleteLabel = 'Удалить' }) => (
  <div className="admin-actions">
    {onEdit && (
      <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={onEdit}
        title="Редактировать" aria-label={`Редактировать: ${label}`}>
        <Pencil {...ICON} />
      </button>
    )}
    <button type="button" className="btn btn-ghost btn-icon btn-sm admin-icon-danger" onClick={onDelete}
      title={deleteLabel} aria-label={`${deleteLabel}: ${label}`}>
      <Trash2 {...ICON} />
    </button>
  </div>
);

const AdminPanel = () => {
  const { isAdmin, user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const tabRefs = useRef({});
  const [activeTab, setActiveTab] = useState('announcements');
  const [usersList, setUsersList] = useState([]);

  // Redirect non-admins
  useEffect(() => {
    if (!isAdmin) {
      navigate('/');
    }
  }, [isAdmin, navigate]);

  // --- USERS ---
  const [usersError, setUsersError] = useState('');
  const loadUsers = useCallback(() => {
    adminApi.getUsers()
      .then(res => { setUsersError(''); if (Array.isArray(res)) setUsersList(res); })
      .catch(e => { setUsersError(e.message || 'Не удалось загрузить пользователей'); setUsersList([]); });
  }, []);

  useEffect(() => {
    if (isAdmin) loadUsers();
  }, [isAdmin, loadUsers]);

  const handleRoleChange = async (userId, newRole) => {
    try {
      const updated = await adminApi.updateUserRole(userId, newRole);
      setUsersList(prev => prev.map(u => u.id === userId ? { ...u, role: updated.role } : u));
      toast.show(`Роль пользователя обновлена на ${newRole}`, 'success');
    } catch (err) {
      toast.show(err.message || 'Ошибка изменения роли', 'warning');
    }
  };

  const handleToggleBlock = async (userId, username, blocked) => {
    const action = blocked ? 'заблокировать' : 'разблокировать';
    if (!window.confirm(`${blocked ? 'Заблокировать' : 'Разблокировать'} пользователя "${username}"?`)) return;
    try {
      const updated = await adminApi.setUserBlocked(userId, blocked);
      setUsersList(prev => prev.map(u => u.id === userId ? { ...u, is_blocked: updated.is_blocked } : u));
      toast.show(`Пользователь "${username}" ${blocked ? 'заблокирован' : 'разблокирован'}`, 'success');
    } catch (err) {
      toast.show(err.message || `Не удалось ${action} пользователя`, 'warning');
    }
  };

  const handleDeleteUser = async (userId, username) => {
    if (!window.confirm(`Удалить пользователя "${username}" вместе с его вопросами и ответами? При следующем входе через ЭИОС аккаунт создастся заново — чтобы закрыть доступ, используйте блокировку.`)) return;
    try {
      await adminApi.deleteUser(userId);
      setUsersList(prev => prev.filter(u => u.id !== userId));
      toast.show(`Пользователь "${username}" успешно удалён из базы`, 'success');
    } catch (err) {
      toast.show(err.message || 'Ошибка удаления пользователя', 'warning');
    }
  };

  // ============================================================
  // ANNOUNCEMENTS — fully server-side, no localStorage
  // ============================================================
  const [announcements, setAnnouncements] = useState([]);
  const [annLoading, setAnnLoading] = useState(false);
  const [annForm, setAnnForm] = useState({ title: '', text: '', is_important: false });
  const [editingAnnId, setEditingAnnId] = useState(null);

  const loadAnnouncements = useCallback(() => {
    setAnnLoading(true);
    adminApi.getAnnouncements()
      .then(res => { if (Array.isArray(res)) setAnnouncements(res); })
      .catch(e => { console.warn('Failed to load announcements:', e); toast.show('Ошибка загрузки объявлений', 'warning'); })
      .finally(() => setAnnLoading(false));
  }, []);

  useEffect(() => {
    if (isAdmin) loadAnnouncements();
  }, [isAdmin, loadAnnouncements]);

  const handleAddAnnouncement = async (e) => {
    e.preventDefault();
    if (!annForm.title.trim() || !annForm.text.trim()) return;
    const payload = {
      title: annForm.title.trim(),
      content: annForm.text.trim(),
      is_important: annForm.is_important
    };
    try {
      if (editingAnnId) {
        // FIX (A-06): Use atomic PUT instead of duplicate-creating CREATE
        const updated = await adminApi.updateAnnouncement(editingAnnId, payload);
        setAnnouncements(prev => prev.map(a => a.id === editingAnnId ? updated : a));
        toast.show('Объявление обновлено', 'success');
      } else {
        const created = await adminApi.createAnnouncement(payload);
        setAnnouncements(prev => [created, ...prev]);
        toast.show('Объявление создано', 'success');
      }
      setAnnForm({ title: '', text: '', is_important: false });
      setEditingAnnId(null);
    } catch (err) {
      toast.show(err.message || 'Ошибка сохранения объявления', 'warning');
    }
  };

  const handleEditAnnouncement = (ann) => {
    setAnnForm({ title: ann.title, text: ann.content || ann.text || '', is_important: ann.is_important || false });
    setEditingAnnId(ann.id);
  };

  const handleDeleteAnnouncement = async (id) => {
    if (!window.confirm('Удалить объявление? Действие необратимо.')) return;
    try {
      await adminApi.deleteAnnouncement(id);
      setAnnouncements(prev => prev.filter(a => a.id !== id));
      toast.show('Объявление удалено', 'info');
    } catch (err) {
      toast.show(err.message || 'Ошибка удаления объявления', 'warning');
    }
  };

  const handleCancelAnn = () => {
    setEditingAnnId(null);
    setAnnForm({ title: '', text: '', is_important: false });
  };

  // ============================================================
  // TEACHERS — server-side
  // ============================================================
  const [teachers, setTeachers] = useState([]);
  const [teacherForm, setTeacherForm] = useState({
    name: '', department: '', role: '', email: '', office: '', hours: '', courses: '', photo: ''
  });
  const [editingTeacherId, setEditingTeacherId] = useState(null);

  useEffect(() => {
    if (!isAdmin) return;
    adminApi.getTeachers()
      .then(res => { if (Array.isArray(res)) setTeachers(res); })
      .catch(e => console.warn('Failed to load teachers:', e));
  }, [isAdmin]);

  const handlePhotoUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const allowedMimeTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
    if (!allowedMimeTypes.includes(file.type?.toLowerCase())) {
      toast.show('Разрешены только PNG, JPEG, JPG и WebP', 'warning');
      e.target.value = '';
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      toast.show('Размер файла не должен превышать 2 МБ', 'warning');
      e.target.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onloadend = () => setTeacherForm(prev => ({ ...prev, photo: reader.result }));
    reader.readAsDataURL(file);
  };

  const handleAddTeacher = async (e) => {
    e.preventDefault();
    if (!teacherForm.name.trim()) return;
    const teacherData = {
      name: teacherForm.name.trim(),
      department: teacherForm.department.trim() || 'Высшая ИТ-школа КГУ',
      role: teacherForm.role.trim() || 'Преподаватель',
      email: teacherForm.email.trim(),
      office: teacherForm.office.trim() || 'Корпус Б',
      hours: teacherForm.hours.trim(),
      courses: teacherForm.courses,
      photo_url: teacherForm.photo || 'https://kosgos.ru/images/INSTITUTS/nophoto.jpg'
    };
    try {
      const created = await adminApi.createTeacher(teacherData);
      setTeachers(prev => [created, ...prev.filter(t => t.id !== created.id)]);
      toast.show('Преподаватель сохранён', 'success');
      setTeacherForm({ name: '', department: '', role: '', email: '', office: '', hours: '', courses: '', photo: '' });
      setEditingTeacherId(null);
    } catch (err) {
      toast.show(err.message || 'Ошибка сохранения преподавателя', 'warning');
    }
  };

  const handleEditTeacher = (t) => {
    setTeacherForm({
      name: t.name, department: t.department, role: t.role,
      email: t.email || '', office: t.office || '',
      hours: t.hours || '', courses: t.courses || '',
      photo: t.photo_url || t.photo || ''
    });
    setEditingTeacherId(t.id);
  };

  const handleDeleteTeacher = async (id) => {
    if (!window.confirm('Удалить преподавателя?')) return;
    try {
      await adminApi.deleteTeacher(id);
      setTeachers(prev => prev.filter(t => t.id !== id));
      toast.show('Преподаватель удалён', 'info');
    } catch (err) {
      toast.show(err.message || 'Ошибка удаления', 'warning');
    }
  };

  // ============================================================
  // SUBJECTS — server-side
  // ============================================================
  const [subjects, setSubjects] = useState([]);
  const [subjectForm, setSubjectForm] = useState({
    subject_code: '', name: '', short_name: '', emoji: '📚', color: '#007AFF',
    difficulty: 3, hours: 108, credits: 3, semester: 1, control_type: 'Зачет',
    extra_type: '', description: '', mascot_hack: '', senior_advice: ''
  });
  const [editingSubjectId, setEditingSubjectId] = useState(null);

  useEffect(() => {
    if (!isAdmin) return;
    adminApi.getSubjects()
      .then(res => { if (Array.isArray(res)) setSubjects(res); })
      .catch(e => console.warn('Failed to load subjects:', e));
  }, [isAdmin]);

  const handleAddSubject = async (e) => {
    e.preventDefault();
    if (!subjectForm.name.trim() || !subjectForm.subject_code.trim()) return;
    try {
      if (editingSubjectId) {
        const updated = await adminApi.updateSubject(editingSubjectId, subjectForm);
        setSubjects(prev => prev.map(s => s.id === editingSubjectId ? updated : s));
        toast.show('Предмет обновлён', 'success');
        setEditingSubjectId(null);
      } else {
        const created = await adminApi.createSubject(subjectForm);
        setSubjects(prev => [...prev, created]);
        toast.show('Предмет создан', 'success');
      }
      setSubjectForm({
        subject_code: '', name: '', short_name: '', emoji: '📚', color: '#007AFF',
        difficulty: 3, hours: 108, credits: 3, semester: 1, control_type: 'Зачет',
        extra_type: '', description: '', mascot_hack: '', senior_advice: ''
      });
    } catch (err) {
      toast.show(err.message || 'Ошибка сохранения предмета', 'warning');
    }
  };

  const handleEditSubject = (s) => {
    setSubjectForm({
      subject_code: s.subject_code, name: s.name, short_name: s.short_name,
      emoji: s.emoji || '📚', color: s.color || '#007AFF',
      difficulty: s.difficulty || 3, hours: s.hours || 108,
      credits: s.credits || 3, semester: s.semester || 1,
      control_type: s.control_type || 'Зачет', extra_type: s.extra_type || '',
      description: s.description || '', mascot_hack: s.mascot_hack || '',
      senior_advice: s.senior_advice || ''
    });
    setEditingSubjectId(s.id);
  };

  const handleDeleteSubject = async (id) => {
    if (!window.confirm('Удалить дисциплину из каталога?')) return;
    try {
      await adminApi.deleteSubject(id);
      setSubjects(prev => prev.filter(s => s.id !== id));
      toast.show('Предмет удалён', 'info');
    } catch (err) {
      toast.show(err.message || 'Ошибка удаления', 'warning');
    }
  };

  // ============================================================
  // FAQ — fully server-side, no localStorage
  // ============================================================
  const [faqItems, setFaqItems] = useState([]);
  const [faqLoading, setFaqLoading] = useState(false);
  const [faqForm, setFaqForm] = useState({ question: '', answer: '' });
  const [editingFaqId, setEditingFaqId] = useState(null);

  const loadFaq = useCallback(() => {
    setFaqLoading(true);
    adminApi.getFaq()
      .then(res => { if (Array.isArray(res)) setFaqItems(res); })
      .catch(e => { console.warn('Failed to load FAQ:', e); toast.show('Ошибка загрузки FAQ', 'warning'); })
      .finally(() => setFaqLoading(false));
  }, []);

  useEffect(() => {
    if (isAdmin) loadFaq();
  }, [isAdmin, loadFaq]);

  const handleAddFaq = async (e) => {
    e.preventDefault();
    if (!faqForm.question.trim() || !faqForm.answer.trim()) return;
    const payload = {
      question: faqForm.question.trim(),
      answer: faqForm.answer.trim()
    };
    try {
      if (editingFaqId) {
        // FIX (A-07): Atomic PUT instead of delete+create (prevents data loss on partial failure)
        const updated = await adminApi.updateFaq(editingFaqId, payload);
        setFaqItems(prev => prev.map(f => f.id === editingFaqId ? updated : f));
        toast.show('FAQ обновлён', 'success');
        setEditingFaqId(null);
      } else {
        const created = await adminApi.createFaq(payload);
        setFaqItems(prev => [...prev, created]);
        toast.show('Вопрос добавлен в FAQ', 'success');
      }
      setFaqForm({ question: '', answer: '' });
    } catch (err) {
      toast.show(err.message || 'Ошибка сохранения FAQ', 'warning');
    }
  };

  const handleEditFaq = (f) => {
    setFaqForm({ question: f.question, answer: f.answer });
    setEditingFaqId(f.id);
  };

  const handleDeleteFaq = async (id) => {
    if (!window.confirm('Удалить вопрос из FAQ?')) return;
    try {
      await adminApi.deleteFaq(id);
      setFaqItems(prev => prev.filter(f => f.id !== id));
      toast.show('Вопрос удалён из FAQ', 'info');
    } catch (err) {
      toast.show(err.message || 'Ошибка удаления', 'warning');
    }
  };

  const handleCancelFaq = () => {
    setEditingFaqId(null);
    setFaqForm({ question: '', answer: '' });
  };

  // ============================================================
  // FORUM MODERATION — load from API
  // ============================================================
  const [forumQuestions, setForumQuestions] = useState([]);

  useEffect(() => {
    if (!isAdmin) return;
    import('../services/api').then(({ forumApi }) => {
      forumApi.getQuestions().then(res => {
        if (Array.isArray(res)) setForumQuestions(res);
      }).catch(() => {});
    });
  }, [isAdmin]);

  const handleDeleteForumQuestion = (id) => {
    // Forum delete via API not implemented yet — show informative message
    toast.show('Удаление тем форума через API в разработке. Используйте БД напрямую.', 'info');
  };

  if (!isAdmin) return null;

  const tabs = [
    { id: 'announcements', label: 'Объявления', count: announcements.length },
    { id: 'teachers', label: 'Преподаватели', count: teachers.length },
    { id: 'subjects', label: 'Предметы', count: subjects.length },
    { id: 'faq', label: 'FAQ', count: faqItems.length },
    { id: 'forum', label: 'Модерация форума', count: forumQuestions.length },
    { id: 'users', label: 'Пользователи', count: usersList.length },
  ];

  // WAI-ARIA tabs: arrows / Home / End move between tabs, Tab moves into the panel
  const handleTabKeyDown = (e, index) => {
    let next = null;
    if (e.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = tabs.length - 1;
    if (next === null) return;
    e.preventDefault();
    setActiveTab(tabs[next].id);
    tabRefs.current[tabs[next].id]?.focus();
  };

  const panelProps = (id) => ({
    id: `admin-panel-${id}`,
    role: 'tabpanel',
    'aria-labelledby': `admin-tab-${id}`,
    className: 'admin-panel',
  });

  return (
    <div className="container admin-page">
      <div className="page-header">
        <div className="page-heading">
          <SectionIcon section="admin" size="lg" />
          <h1>Панель управления</h1>
        </div>
      </div>

      {/* TABS */}
      <div className="admin-tabs" role="tablist" aria-label="Разделы панели управления">
        {tabs.map((tab, index) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              ref={el => { tabRefs.current[tab.id] = el; }}
              type="button"
              role="tab"
              id={`admin-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`admin-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              className="admin-tab"
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={e => handleTabKeyDown(e, index)}
            >
              <span>{tab.label}</span>
              <span className="badge tabular admin-tab-count">{tab.count}</span>
            </button>
          );
        })}
      </div>

      {/* ANNOUNCEMENTS TAB */}
      {activeTab === 'announcements' && (
        <section {...panelProps('announcements')}>
          <Toolbar title="Объявления">
            <RefreshButton onClick={loadAnnouncements} disabled={annLoading} />
          </Toolbar>

          <div className="card admin-editor">
            <div className="admin-editor-head">
              <h3>{editingAnnId ? 'Редактировать объявление' : 'Новое объявление'}</h3>
              <p>Объявления показываются студентам на главной странице.</p>
            </div>
            <form onSubmit={handleAddAnnouncement} className="admin-form">
              <Field id="admin-ann-title" label="Заголовок" required>
                <input
                  id="admin-ann-title"
                  className="input"
                  type="text"
                  value={annForm.title}
                  onChange={e => setAnnForm({ ...annForm, title: e.target.value })}
                  required
                />
              </Field>
              <Field id="admin-ann-text" label="Текст объявления" required>
                <textarea
                  id="admin-ann-text"
                  className="textarea"
                  value={annForm.text}
                  onChange={e => setAnnForm({ ...annForm, text: e.target.value })}
                  required
                  rows={4}
                />
              </Field>
              <label className="admin-check">
                <input
                  type="checkbox"
                  checked={annForm.is_important}
                  onChange={e => setAnnForm({ ...annForm, is_important: e.target.checked })}
                />
                Важное объявление
              </label>
              <div className="admin-form-actions">
                <button type="submit" className="btn btn-primary">
                  <Save {...ICON} /> {editingAnnId ? 'Сохранить изменения' : 'Создать объявление'}
                </button>
                {editingAnnId && (
                  <button type="button" className="btn btn-ghost" onClick={handleCancelAnn}>
                    Отменить редактирование
                  </button>
                )}
              </div>
            </form>
          </div>

          <div className="admin-list">
            {annLoading ? (
              <ListSkeleton />
            ) : announcements.length === 0 ? (
              <p className="admin-empty">Объявлений пока нет. Создайте первое в форме выше.</p>
            ) : (
              <table className="admin-table">
                <caption className="visually-hidden">Опубликованные объявления</caption>
                <thead>
                  <tr>
                    <th scope="col">Объявление</th>
                    <th scope="col">Дата</th>
                    <th scope="col" className="admin-cell-actions"><span className="visually-hidden">Действия</span></th>
                  </tr>
                </thead>
                <tbody>
                  {announcements.map(ann => {
                    const body = ann.content || ann.text || '';
                    return (
                      <tr key={ann.id} className={editingAnnId === ann.id ? 'is-editing' : undefined}>
                        <td className="admin-cell-main">
                          <div className="admin-cell-head">
                            <span className="admin-cell-title">{ann.title}</span>
                            {ann.is_important && <span className="badge badge-danger">Важное</span>}
                          </div>
                          <p className="admin-cell-sub">{body.slice(0, 100)}{body.length > 100 ? '…' : ''}</p>
                        </td>
                        <td className="admin-cell-meta tabular" data-label="Дата">{formatLongDate(ann.created_at)}</td>
                        <td className="admin-cell-actions">
                          <RowActions
                            label={ann.title}
                            onEdit={() => { handleEditAnnouncement(ann); focusEditor('admin-ann-title'); }}
                            onDelete={() => handleDeleteAnnouncement(ann.id)}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}

      {/* TEACHERS TAB */}
      {activeTab === 'teachers' && (
        <section {...panelProps('teachers')}>
          <Toolbar title="Преподаватели" />

          <div className="card admin-editor">
            <div className="admin-editor-head">
              <h3>{editingTeacherId ? 'Редактировать преподавателя' : 'Добавить преподавателя'}</h3>
              <p>Карточка появится в разделе «Преподаватели». Пустые поля заполнятся значениями по умолчанию.</p>
            </div>
            <form onSubmit={handleAddTeacher} className="admin-form">
              <div className="admin-grid">
                <Field id="admin-teacher-name" label="ФИО" required>
                  <input id="admin-teacher-name" className="input" type="text" autoComplete="off" value={teacherForm.name} onChange={e => setTeacherForm({ ...teacherForm, name: e.target.value })} required />
                </Field>
                <Field id="admin-teacher-department" label="Кафедра">
                  <input id="admin-teacher-department" className="input" type="text" placeholder="Высшая ИТ-школа КГУ" value={teacherForm.department} onChange={e => setTeacherForm({ ...teacherForm, department: e.target.value })} />
                </Field>
                <Field id="admin-teacher-role" label="Должность">
                  <input id="admin-teacher-role" className="input" type="text" placeholder="Доцент, профессор" value={teacherForm.role} onChange={e => setTeacherForm({ ...teacherForm, role: e.target.value })} />
                </Field>
                <Field id="admin-teacher-email" label="Email">
                  <input id="admin-teacher-email" className="input" type="email" autoComplete="off" value={teacherForm.email} onChange={e => setTeacherForm({ ...teacherForm, email: e.target.value })} />
                </Field>
                <Field id="admin-teacher-office" label="Кабинет">
                  <input id="admin-teacher-office" className="input" type="text" placeholder="Б-209" value={teacherForm.office} onChange={e => setTeacherForm({ ...teacherForm, office: e.target.value })} />
                </Field>
                <Field id="admin-teacher-hours" label="Часы приёма">
                  <input id="admin-teacher-hours" className="input" type="text" placeholder="Вт 12:00–14:00" value={teacherForm.hours} onChange={e => setTeacherForm({ ...teacherForm, hours: e.target.value })} />
                </Field>
                <Field id="admin-teacher-courses" label="Курсы" hint="Через запятую: Базы данных, SQL, ООП" className="admin-span-full">
                  <input id="admin-teacher-courses" className="input" type="text" aria-describedby="admin-teacher-courses-hint" value={teacherForm.courses} onChange={e => setTeacherForm({ ...teacherForm, courses: e.target.value })} />
                </Field>
                <Field id="admin-teacher-photo" label="Фотография" hint="Необязательно. PNG, JPEG или WebP, до 2 МБ" className="admin-span-full">
                  <div className="admin-file-row">
                    <input id="admin-teacher-photo" className="admin-file" type="file" accept="image/png,image/jpeg,image/jpg,image/webp" aria-describedby="admin-teacher-photo-hint" onChange={handlePhotoUpload} />
                    {teacherForm.photo && (
                      <div className="admin-photo-preview">
                        <img src={teacherForm.photo.startsWith('data:') || teacherForm.photo.startsWith('http') ? teacherForm.photo : `/img/teachers/${teacherForm.photo}`}
                          alt="Предпросмотр фотографии"
                          onError={e => { e.target.style.display = 'none'; }}
                        />
                      </div>
                    )}
                  </div>
                </Field>
              </div>
              <div className="admin-form-actions">
                <button type="submit" className="btn btn-primary">
                  <Save {...ICON} /> {editingTeacherId ? 'Сохранить изменения' : 'Добавить преподавателя'}
                </button>
                {editingTeacherId && (
                  <button type="button" className="btn btn-ghost" onClick={() => { setEditingTeacherId(null); setTeacherForm({ name: '', department: '', role: '', email: '', office: '', hours: '', courses: '', photo: '' }); }}>
                    Отменить редактирование
                  </button>
                )}
              </div>
            </form>
          </div>

          <div className="admin-list">
            {teachers.length === 0 ? (
              <p className="admin-empty">Преподаватели ещё не добавлены. Заполните форму выше, чтобы добавить первого.</p>
            ) : (
              <table className="admin-table">
                <caption className="visually-hidden">Преподаватели</caption>
                <thead>
                  <tr>
                    <th scope="col">Преподаватель</th>
                    <th scope="col">Кафедра</th>
                    <th scope="col">Email</th>
                    <th scope="col" className="admin-cell-actions"><span className="visually-hidden">Действия</span></th>
                  </tr>
                </thead>
                <tbody>
                  {teachers.map(t => (
                    <tr key={t.id} className={editingTeacherId === t.id ? 'is-editing' : undefined}>
                      <td className="admin-cell-main">
                        <span className="admin-cell-title">{t.name}</span>
                        {t.role && <p className="admin-cell-sub">{t.role}</p>}
                      </td>
                      <td className="admin-cell-meta admin-cell-wrap" data-label="Кафедра">{t.department}</td>
                      <td className="admin-cell-meta admin-cell-email" data-label="Email">{t.email || '—'}</td>
                      <td className="admin-cell-actions">
                        <RowActions
                          label={t.name}
                          onEdit={() => { handleEditTeacher(t); focusEditor('admin-teacher-name'); }}
                          onDelete={() => handleDeleteTeacher(t.id)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}

      {/* SUBJECTS TAB */}
      {activeTab === 'subjects' && (
        <section {...panelProps('subjects')}>
          <Toolbar title="Предметы" />

          <div className="card admin-editor">
            <div className="admin-editor-head">
              <h3>{editingSubjectId ? 'Редактировать дисциплину' : 'Добавить новую дисциплину'}</h3>
              <p>Справочник дисциплин учебного плана по семестрам.</p>
            </div>
            <form onSubmit={handleAddSubject} className="admin-form">
              <div className="admin-grid admin-grid-3">
                <Field id="admin-subject-code" label="Код" required>
                  <input id="admin-subject-code" className="input" type="text" placeholder="s1-algo" autoComplete="off" value={subjectForm.subject_code} onChange={e => setSubjectForm({ ...subjectForm, subject_code: e.target.value })} required />
                </Field>
                <Field id="admin-subject-name" label="Полное название" required>
                  <input id="admin-subject-name" className="input" type="text" value={subjectForm.name} onChange={e => setSubjectForm({ ...subjectForm, name: e.target.value })} required />
                </Field>
                <Field id="admin-subject-short" label="Сокращение" required>
                  <input id="admin-subject-short" className="input" type="text" value={subjectForm.short_name} onChange={e => setSubjectForm({ ...subjectForm, short_name: e.target.value })} required />
                </Field>
              </div>
              <div className="admin-grid admin-grid-5">
                <Field id="admin-subject-semester" label="Семестр" required>
                  <input id="admin-subject-semester" className="input tabular" type="number" inputMode="numeric" min={1} max={12} value={subjectForm.semester} onChange={e => setSubjectForm({ ...subjectForm, semester: Number(e.target.value) })} required />
                </Field>
                <Field id="admin-subject-hours" label="Часы" required>
                  <input id="admin-subject-hours" className="input tabular" type="number" inputMode="numeric" value={subjectForm.hours} onChange={e => setSubjectForm({ ...subjectForm, hours: Number(e.target.value) })} required />
                </Field>
                <Field id="admin-subject-credits" label="Зач. ед." required>
                  <input id="admin-subject-credits" className="input tabular" type="number" inputMode="numeric" value={subjectForm.credits} onChange={e => setSubjectForm({ ...subjectForm, credits: Number(e.target.value) })} required />
                </Field>
                <Field id="admin-subject-control" label="Контроль">
                  <select id="admin-subject-control" className="select" value={subjectForm.control_type} onChange={e => setSubjectForm({ ...subjectForm, control_type: e.target.value })}>
                    <option value="Зачет">Зачет</option>
                    <option value="Экзамен">Экзамен</option>
                    <option value="Практика">Практика</option>
                  </select>
                </Field>
                <Field id="admin-subject-emoji" label="Эмодзи">
                  <input id="admin-subject-emoji" className="input" type="text" value={subjectForm.emoji} onChange={e => setSubjectForm({ ...subjectForm, emoji: e.target.value })} />
                </Field>
              </div>
              <Field id="admin-subject-description" label="Описание предмета" required>
                <textarea id="admin-subject-description" className="textarea" value={subjectForm.description} onChange={e => setSubjectForm({ ...subjectForm, description: e.target.value })} required rows={3} />
              </Field>
              <div className="admin-grid">
                <Field id="admin-subject-hack" label="Лайфхак ВИТШика">
                  <textarea id="admin-subject-hack" className="textarea" value={subjectForm.mascot_hack} onChange={e => setSubjectForm({ ...subjectForm, mascot_hack: e.target.value })} rows={3} />
                </Field>
                <Field id="admin-subject-advice" label="Совет старшекурсника">
                  <textarea id="admin-subject-advice" className="textarea" value={subjectForm.senior_advice} onChange={e => setSubjectForm({ ...subjectForm, senior_advice: e.target.value })} rows={3} />
                </Field>
              </div>
              <div className="admin-form-actions">
                <button type="submit" className="btn btn-primary">
                  <Save {...ICON} /> {editingSubjectId ? 'Сохранить изменения' : 'Добавить предмет'}
                </button>
                {editingSubjectId && (
                  <button type="button" className="btn btn-ghost" onClick={() => { setEditingSubjectId(null); setSubjectForm({ subject_code: '', name: '', short_name: '', emoji: '📚', color: '#007AFF', difficulty: 3, hours: 108, credits: 3, semester: 1, control_type: 'Зачет', extra_type: '', description: '', mascot_hack: '', senior_advice: '' }); }}>
                    Отменить редактирование
                  </button>
                )}
              </div>
            </form>
          </div>

          <div className="admin-list">
            {subjects.length === 0 ? (
              <p className="admin-empty">Предметы не найдены. Заполните форму выше, чтобы занести первый предмет.</p>
            ) : (
              <table className="admin-table">
                <caption className="visually-hidden">Дисциплины</caption>
                <thead>
                  <tr>
                    <th scope="col">Дисциплина</th>
                    <th scope="col" className="admin-num">Семестр</th>
                    <th scope="col" className="admin-num">Часы</th>
                    <th scope="col" className="admin-num">З. е.</th>
                    <th scope="col">Контроль</th>
                    <th scope="col" className="admin-cell-actions"><span className="visually-hidden">Действия</span></th>
                  </tr>
                </thead>
                <tbody>
                  {subjects.map(s => (
                    <tr key={s.id} className={editingSubjectId === s.id ? 'is-editing' : undefined}>
                      <td className="admin-cell-main">
                        <span className="admin-cell-title">{s.name}</span>
                        <p className="admin-cell-sub">{s.short_name} · {s.subject_code}</p>
                      </td>
                      <td className="admin-cell-meta admin-num" data-label="Семестр">{s.semester}</td>
                      <td className="admin-cell-meta admin-num" data-label="Часы">{s.hours}</td>
                      <td className="admin-cell-meta admin-num" data-label="З. е.">{s.credits}</td>
                      <td className="admin-cell-meta" data-label="Контроль">{s.control_type}</td>
                      <td className="admin-cell-actions">
                        <RowActions
                          label={s.name}
                          onEdit={() => { handleEditSubject(s); focusEditor('admin-subject-code'); }}
                          onDelete={() => handleDeleteSubject(s.id)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}

      {/* FAQ TAB */}
      {activeTab === 'faq' && (
        <section {...panelProps('faq')}>
          <Toolbar title="FAQ">
            <RefreshButton onClick={loadFaq} disabled={faqLoading} />
          </Toolbar>

          <div className="card admin-editor">
            <div className="admin-editor-head">
              <h3>{editingFaqId ? 'Редактировать FAQ' : 'Добавить вопрос в FAQ'}</h3>
              <p>Вопросы показываются в разделе «Вопросы и ответы».</p>
            </div>
            <form onSubmit={handleAddFaq} className="admin-form">
              <Field id="admin-faq-question" label="Вопрос" required>
                <input id="admin-faq-question" className="input" type="text" value={faqForm.question} onChange={e => setFaqForm({ ...faqForm, question: e.target.value })} required />
              </Field>
              <Field id="admin-faq-answer" label="Ответ" required hint="Поддерживается HTML">
                <textarea id="admin-faq-answer" className="textarea" aria-describedby="admin-faq-answer-hint" value={faqForm.answer} onChange={e => setFaqForm({ ...faqForm, answer: e.target.value })} required rows={5} />
              </Field>
              <div className="admin-form-actions">
                <button type="submit" className="btn btn-primary">
                  <Save {...ICON} /> {editingFaqId ? 'Сохранить изменения' : 'Добавить вопрос'}
                </button>
                {editingFaqId && (
                  <button type="button" className="btn btn-ghost" onClick={handleCancelFaq}>
                    Отменить редактирование
                  </button>
                )}
              </div>
            </form>
          </div>

          <div className="admin-list">
            {faqLoading ? (
              <ListSkeleton />
            ) : faqItems.length === 0 ? (
              <p className="admin-empty">В FAQ пока нет вопросов. Добавьте первый в форме выше.</p>
            ) : (
              <table className="admin-table">
                <caption className="visually-hidden">Вопросы FAQ</caption>
                <thead>
                  <tr>
                    <th scope="col">Вопрос и ответ</th>
                    <th scope="col" className="admin-cell-actions"><span className="visually-hidden">Действия</span></th>
                  </tr>
                </thead>
                <tbody>
                  {faqItems.map(f => (
                    <tr key={f.id} className={editingFaqId === f.id ? 'is-editing' : undefined}>
                      <td className="admin-cell-main">
                        <span className="admin-cell-title">{f.question}</span>
                        <div className="admin-cell-sub" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(f.answer.length > 120 ? f.answer.slice(0, 120) + '…' : f.answer) }} />
                      </td>
                      <td className="admin-cell-actions">
                        <RowActions
                          label={f.question}
                          onEdit={() => { handleEditFaq(f); focusEditor('admin-faq-question'); }}
                          onDelete={() => handleDeleteFaq(f.id)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}

      {/* FORUM MODERATION TAB */}
      {activeTab === 'forum' && (
        <section {...panelProps('forum')}>
          <Toolbar
            title="Модерация форума"
            description="Просмотр всех тем форума. Данные загружаются из базы данных в реальном времени."
          />

          <div className="admin-list">
            {forumQuestions.length === 0 ? (
              <p className="admin-empty">На форуме пока нет тем.</p>
            ) : (
              <table className="admin-table">
                <caption className="visually-hidden">Темы форума</caption>
                <thead>
                  <tr>
                    <th scope="col">Тема</th>
                    <th scope="col">Автор</th>
                    <th scope="col">Категория</th>
                    <th scope="col">Дата</th>
                    <th scope="col" className="admin-cell-actions"><span className="visually-hidden">Действия</span></th>
                  </tr>
                </thead>
                <tbody>
                  {forumQuestions.map(q => (
                    <tr key={q.id}>
                      <td className="admin-cell-main">
                        <span className="admin-cell-title">{q.title}</span>
                      </td>
                      <td className="admin-cell-meta" data-label="Автор">{q.author_name}</td>
                      <td className="admin-cell-meta" data-label="Категория">{q.category}</td>
                      <td className="admin-cell-meta tabular" data-label="Дата">{new Date(q.created_at).toLocaleDateString('ru-RU')}</td>
                      <td className="admin-cell-actions">
                        <RowActions
                          label={q.title}
                          deleteLabel="Удалить тему"
                          onDelete={() => handleDeleteForumQuestion(q.id)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}

      {/* USERS & ROLES TAB */}
      {activeTab === 'users' && (
        <section {...panelProps('users')}>
          <Toolbar
            title="Управление ролями пользователей"
            description="Назначайте права Администратора или Модератора зарегистрированным студентам ИВИТШ."
          >
            <RefreshButton onClick={loadUsers} />
          </Toolbar>

          <div className="admin-list">
            {usersError ? (
              <LoadError message={usersError} onRetry={loadUsers} />
            ) : usersList.length === 0 ? (
              <p className="admin-empty">Нет зарегистрированных пользователей.</p>
            ) : (
              <table className="admin-table">
                <caption className="visually-hidden">Пользователи портала</caption>
                <thead>
                  <tr>
                    <th scope="col">Пользователь</th>
                    <th scope="col">Группа</th>
                    <th scope="col">Роль</th>
                    <th scope="col" className="admin-cell-controls"><span className="visually-hidden">Действия</span></th>
                  </tr>
                </thead>
                <tbody>
                  {usersList.map(u => {
                    const isSuperAdmin = u.auth_source === 'local';
                    const isSelf = user && u.id === user.id;
                    const locked = isSuperAdmin || isSelf;
                    return (
                      <tr key={u.id}>
                        <td className="admin-cell-main">
                          <div className="admin-cell-head">
                            <span className="admin-cell-title">{u.full_name || u.username}</span>
                            {isSuperAdmin && <span className="badge badge-accent">Главный Админ</span>}
                            {u.is_blocked && <span className="badge badge-danger">Заблокирован</span>}
                            {isSelf && <span className="badge">Это вы</span>}
                          </div>
                          <p className="admin-cell-sub">Логин: {u.username}</p>
                        </td>
                        <td className={`admin-cell-meta${u.group_number ? '' : ' admin-cell-muted'}`} data-label="Группа">
                          {u.group_number || 'Не указана'}
                        </td>
                        <td className="admin-cell-role" data-label="Роль">
                          {locked ? (
                            <span className="admin-role-fixed" title="Роль этого пользователя нельзя изменить">
                              <Lock {...ICON} />
                              {isSuperAdmin ? 'Администратор ИВИТШ' : (ROLE_LABELS[u.role] || u.role)}
                              <span className="visually-hidden">, роль нельзя изменить</span>
                            </span>
                          ) : (
                            <select
                              className="select admin-role-select"
                              aria-label={`Роль пользователя ${u.username}`}
                              value={u.role}
                              onChange={(e) => handleRoleChange(u.id, e.target.value)}
                            >
                              <option value="student">{ROLE_LABELS.student}</option>
                              <option value="moderator">{ROLE_LABELS.moderator}</option>
                              <option value="admin">{ROLE_LABELS.admin}</option>
                            </select>
                          )}
                        </td>
                        <td className="admin-cell-controls">
                          {!locked && (
                            <div className="admin-controls">
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleToggleBlock(u.id, u.username, !u.is_blocked)}
                                title={u.is_blocked ? 'Разблокировать пользователя' : 'Заблокировать пользователя'}
                              >
                                {u.is_blocked ? <LockOpen {...ICON} /> : <Lock {...ICON} />}
                                {u.is_blocked ? 'Разблокировать' : 'Заблокировать'}
                              </button>
                              <button
                                type="button"
                                className="btn btn-danger btn-sm"
                                onClick={() => handleDeleteUser(u.id, u.username)}
                                title="Удалить пользователя"
                              >
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
        </section>
      )}

    </div>
  );
};

export default AdminPanel;
