import React, { useState, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Search, Mail, MapPin, Phone, ChevronRight, SearchX, Users as UsersIcon, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { contentApi, scheduleApi } from '../services/api';
import SectionIcon from '../components/SectionIcon';
import { initialsOf } from '../utils/avatar';
import { mskNow, toMinutes } from '../utils/time';
import { plural } from '../utils/plural';

const ICON = { strokeWidth: 1.75 };
const EASE = [0.16, 1, 0.3, 1];

/** Russian plural: plural(3, ['преподаватель', 'преподавателя', 'преподавателей']) */

/** Teacher photo from kosgos.ru with an initials fallback when the image is missing or fails to load. */
const TeacherPhoto = ({ photo, name, size = 'md' }) => {
  const [failed, setFailed] = useState(false);
  const hasPhoto = photo && !photo.includes('nophoto') && !failed;
  return (
    <span className={`cm-avatar cm-avatar-${size}`} aria-hidden="true">
      {hasPhoto ? (
        <img src={photo} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />
      ) : (
        <span className="cm-avatar-initials">{initialsOf(name)}</span>
      )}
    </span>
  );
};

const isFemale = (name) => /(вна|чна)$/i.test((name || '').trim().split(/\s+/)[2] || '');

const BUILDING_B_ROOM = /^Б-?\d{3}$/i;

/** Where a teacher is right now, from today's lessons: { tone, text } */
const teacherStatus = (lessons, name, nowMin) => {
  if (!lessons) return null;
  const current = lessons.find(l => toMinutes(l.start) <= nowMin && nowMin < toMinutes(l.end));
  if (current) return { tone: 'busy', text: `На паре${current.room ? ` в ${current.room}` : ''} до ${current.end}` };
  const later = lessons.find(l => toMinutes(l.start) > nowMin);
  const free = isFemale(name) ? 'Свободна' : 'Свободен';
  if (later) return { tone: 'free', text: `${free} до ${later.start}` };
  if (lessons.length) return { tone: 'idle', text: 'Пары на сегодня закончились' };
  return { tone: 'idle', text: 'Сегодня без пар' };
};

const TeacherStatus = ({ status }) => (status ? (
  <span className={`teacher-status is-${status.tone}`}>
    <span className="teacher-status-dot" aria-hidden="true" />
    {status.text}
  </span>
) : null);

const Teachers = () => {
  const [searchParams] = useSearchParams();
  // /teachers?q=Киприна opens the directory filtered (links from the assistant)
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get('q') || '');
  const [selectedTeacher, setSelectedTeacher] = useState(null);
  const [teachersList, setTeachersList] = useState([]);
  const [loading, setLoading] = useState(true);
  const rowTriggerRef = useRef(null);

  // Today's lessons per teacher; statuses are recomputed from the clock every 30 s
  const [today, setToday] = useState(null);
  const [clock, setClock] = useState(() => mskNow());
  useEffect(() => {
    let active = true;
    scheduleApi.getTeachersToday()
      .then(res => { if (active && res?.date === mskNow().date) setToday(res.teachers || {}); })
      .catch(() => { /* statuses are optional: EIOS may be unreachable */ });
    const timer = setInterval(() => setClock(mskNow()), 30000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  const statusOf = (teacher) => (today ? teacherStatus(today[teacher.id], teacher.name, clock.minutes) : null);

  useEffect(() => {
    contentApi.getTeachers().then(res => {
      if (Array.isArray(res) && res.length > 0) {
        setTeachersList(res.map(t => ({
          id: t.id,
          name: t.name,
          department: t.department,
          role: t.role,
          email: t.email || '',
          office: t.office || 'Корпус Б',
          hours: t.hours || '',
          courses: t.courses ? t.courses.split(',') : [],
          photo: t.photo_url || 'https://kosgos.ru/images/INSTITUTS/nophoto.jpg'
        })));
      }
    }).catch(e => console.warn('Using static teachers fallback:', e))
      .finally(() => setLoading(false));
  }, []);

  // Teacher dialog: close on Escape, return focus to the row that opened it
  useEffect(() => {
    if (!selectedTeacher) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setSelectedTeacher(null); };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      const trigger = rowTriggerRef.current;
      if (trigger && trigger.isConnected) trigger.focus();
    };
  }, [selectedTeacher]);

  const filteredTeachers = teachersList.filter(teacher =>
    teacher.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    teacher.role.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (teacher.email && teacher.email.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  // Group filtered teachers by department
  const groupedTeachers = filteredTeachers.reduce((groups, teacher) => {
    const dept = teacher.department || 'Высшая ИТ-школа КГУ';
    if (!groups[dept]) {
      groups[dept] = [];
    }
    groups[dept].push(teacher);
    return groups;
  }, {});

  // Helper to highlight search term
  const highlightText = (text, query) => {
    if (!query || !text) return text || '';
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

  const emailsOf = (email) => (email || '').split(',').map(s => s.trim()).filter(Boolean);

  return (
    <div className="container cm-page">
      <header className="page-header">
        <div className="page-heading">
          <SectionIcon section="teachers" size="lg" />
          <div>
            <h1>Преподаватели</h1>
            <p className="page-subtitle">Преподаватели ИВИТШ КГУ: должности, кабинеты и контакты.</p>
          </div>
        </div>
      </header>

      {/* SEARCH */}
      <div className="teachers-toolbar">
        <div className="cm-search">
          <label htmlFor="teachers-search" className="visually-hidden">Поиск преподавателя</label>
          <Search size={18} {...ICON} className="cm-search-icon" aria-hidden="true" />
          <input
            id="teachers-search"
            type="search"
            className="input"
            placeholder="ФИО, должность или e-mail"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            autoComplete="off"
          />
        </div>
        {!loading && teachersList.length > 0 && (
          <p className="teachers-count" aria-live="polite">
            <span className="tabular">{filteredTeachers.length}</span>{' '}
            {plural(filteredTeachers.length, ['преподаватель', 'преподавателя', 'преподавателей'])}
            {searchQuery ? ' найдено' : ''}
          </p>
        )}
      </div>

      {/* DIRECTORY */}
      {loading ? (
        <ul className="teacher-list" aria-busy="true" aria-label="Загрузка списка преподавателей">
          {[0, 1, 2, 3].map(i => (
            <li key={i} className="teacher-skeleton" aria-hidden="true">
              <span className="skeleton teacher-skel-avatar" />
              <span className="teacher-skel-text">
                <span className="skeleton teacher-skel-name" />
                <span className="skeleton teacher-skel-role" />
              </span>
            </li>
          ))}
        </ul>
      ) : teachersList.length === 0 ? (
        <div className="empty-state">
          <UsersIcon size={32} {...ICON} aria-hidden="true" />
          <h2 className="cm-empty-title">Список преподавателей недоступен</h2>
          <p>Обновите страницу через минуту. Контакты кафедры также есть на сайте kosgos.ru.</p>
        </div>
      ) : filteredTeachers.length === 0 ? (
        <div className="empty-state">
          <SearchX size={32} {...ICON} aria-hidden="true" />
          <h2 className="cm-empty-title">Никого не нашли</h2>
          <p>По запросу «{searchQuery}» преподавателей нет. Проверьте написание фамилии или поищите по должности.</p>
          <button type="button" className="btn btn-secondary" onClick={() => setSearchQuery('')}>Сбросить поиск</button>
        </div>
      ) : (
        <div className="teachers-groups">
          {Object.keys(groupedTeachers).map((deptName, deptIdx) => (
            <section key={deptName} className="teachers-group" aria-labelledby={`dept-${deptIdx}`}>
              <div className="section-header">
                <h2 id={`dept-${deptIdx}`}>{deptName}</h2>
                {Object.keys(groupedTeachers).length > 1 && (
                  <p className="tabular">{groupedTeachers[deptName].length}</p>
                )}
              </div>

              <ul className="teacher-list">
                {groupedTeachers[deptName].map(teacher => (
                  <li key={teacher.id}>
                    <button
                      type="button"
                      className="teacher-row"
                      onClick={(e) => { rowTriggerRef.current = e.currentTarget; setSelectedTeacher(teacher); }}
                      aria-haspopup="dialog"
                    >
                      <TeacherPhoto photo={teacher.photo} name={teacher.name} />
                      <span className="teacher-main">
                        <span className="teacher-name">{highlightText(teacher.name, searchQuery)}</span>
                        <span className="teacher-role">{highlightText(teacher.role, searchQuery)}</span>
                        <TeacherStatus status={statusOf(teacher)} />
                      </span>
                      <span className="teacher-details">
                        {teacher.office && (
                          <span className="teacher-detail">
                            <MapPin size={14} {...ICON} aria-hidden="true" />
                            <span>{teacher.office}</span>
                          </span>
                        )}
                        {teacher.email && (
                          <span className="teacher-detail teacher-email">
                            <Mail size={14} {...ICON} aria-hidden="true" />
                            <span>{highlightText(teacher.email, searchQuery)}</span>
                          </span>
                        )}
                      </span>
                      <ChevronRight size={18} {...ICON} className="teacher-chevron" aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {/* TEACHER DIALOG */}
      <AnimatePresence>
        {selectedTeacher && (
          <motion.div
            className="modal-overlay"
            onClick={() => setSelectedTeacher(null)}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: EASE }}
          >
            <motion.div
              className="modal teacher-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="teacher-dialog-name"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.24, ease: EASE }}
              onClick={e => e.stopPropagation()}
            >
              <button
                type="button"
                className="modal-close"
                onClick={() => setSelectedTeacher(null)}
                aria-label="Закрыть карточку"
              >
                <X size={20} {...ICON} />
              </button>

              <div className="teacher-modal-head">
                <TeacherPhoto photo={selectedTeacher.photo} name={selectedTeacher.name} size="lg" />
                <div>
                  <h2 id="teacher-dialog-name">{selectedTeacher.name}</h2>
                  <p className="teacher-modal-role">{selectedTeacher.role}</p>
                  <TeacherStatus status={statusOf(selectedTeacher)} />
                </div>
              </div>

              {today?.[selectedTeacher.id]?.length > 0 && (
                <section className="teacher-today" aria-labelledby="teacher-today-title">
                  <h3 id="teacher-today-title" className="teacher-today-title">Пары сегодня</h3>
                  <ul className="teacher-day">
                    {today[selectedTeacher.id].map(l => {
                      const isNow = toMinutes(l.start) <= clock.minutes && clock.minutes < toMinutes(l.end);
                      const isPast = toMinutes(l.end) <= clock.minutes;
                      return (
                        <li key={`${l.start}-${l.discipline}-${l.subgroup}`} className={`teacher-day-item${isNow ? ' is-now' : ''}${isPast ? ' is-past' : ''}`}>
                          <span className="teacher-day-time tabular">{l.start}–{l.end}</span>
                          <span className="teacher-day-body">
                            <span className="teacher-day-title">{l.discipline}</span>
                            <span className="teacher-day-meta">
                              {isNow && <><strong>Сейчас</strong> · </>}
                              {l.kind}
                              {l.subgroup > 0 && <> · {l.subgroup} подгруппа</>}
                              {l.room && <> · {BUILDING_B_ROOM.test(l.room)
                                ? <Link to={`/map?room=${encodeURIComponent(l.room)}`}>{l.room}</Link>
                                : l.room}</>}
                              {l.groups?.map(g => <React.Fragment key={g}> · <span className="teacher-day-group">{g}</span></React.Fragment>)}
                            </span>
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              )}

              <dl className="teacher-facts">
                <div className="teacher-fact">
                  <dt>Кафедра</dt>
                  <dd>{selectedTeacher.department}</dd>
                </div>
                {selectedTeacher.office && (
                  <div className="teacher-fact">
                    <dt>Кабинет / корпус</dt>
                    <dd>{selectedTeacher.office}</dd>
                  </div>
                )}
                {selectedTeacher.email && (
                  <div className="teacher-fact">
                    <dt>E-mail</dt>
                    <dd className="teacher-fact-links">
                      {emailsOf(selectedTeacher.email).map(addr => (
                        <a key={addr} href={`mailto:${addr}`}>
                          <Mail size={16} {...ICON} aria-hidden="true" />
                          {addr}
                        </a>
                      ))}
                    </dd>
                  </div>
                )}
                {selectedTeacher.hours && (
                  <div className="teacher-fact">
                    <dt>Контакты / часы</dt>
                    <dd className="teacher-fact-icon">
                      <Phone size={16} {...ICON} aria-hidden="true" />
                      <span className="tabular">{selectedTeacher.hours}</span>
                    </dd>
                  </div>
                )}
              </dl>

              <div className="cm-form-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setSelectedTeacher(null)}
                  autoFocus
                >
                  Закрыть карточку
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Teachers;
