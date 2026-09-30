import React, { useState, useEffect } from 'react';
import {
  GraduationCap, ShieldCheck, BadgeCheck,
  LogIn, LogOut, Camera, AlertCircle, Clock, Loader2, Eye, EyeOff, CalendarDays,
  Smartphone, Share
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { forumApi } from '../services/api';
import { useInstallApp } from '../utils/install';
import SectionIcon from '../components/SectionIcon';
import { ProfileAssociations, ProfileContacts } from '../components/ProfileCommunity';
import { initialsOf, shrinkAvatar } from '../utils/avatar';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

const LOGIN_MODES = [
  { id: 'sdo', label: 'Студент ЭИОС КГУ', Icon: GraduationCap },
  { id: 'staff', label: 'Администратор', Icon: ShieldCheck }
];

// Arrow-key navigation between role="tab" buttons (WAI-ARIA tabs pattern).
const handleTabsKeyDown = (e, ids, current, select, idPrefix) => {
  const idx = ids.indexOf(current);
  let next = null;
  if (e.key === 'ArrowRight') next = ids[(idx + 1) % ids.length];
  else if (e.key === 'ArrowLeft') next = ids[(idx - 1 + ids.length) % ids.length];
  else if (e.key === 'Home') next = ids[0];
  else if (e.key === 'End') next = ids[ids.length - 1];
  if (next === null) return;
  e.preventDefault();
  select(next);
  document.getElementById(`${idPrefix}${next}`)?.focus();
};

const Profile = () => {
  const { user, isLoggedIn, login, adminLogin, logout, updateUserProfile, sessionExpired } = useAuth();
  const toast = useToast();

  // Login form states
  const [loginMode, setLoginMode] = useState('sdo'); // 'sdo' | 'staff'
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [loginError, setLoginError] = useState('');
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockOn, setCapsLockOn] = useState(false);
  // 152-ФЗ: a separate, unticked consent box; signing in through EIOS needs it
  const [consent, setConsent] = useState(false);
  const [avatarLoadError, setAvatarLoadError] = useState(false);
  const app = useInstallApp();

  // Activity stats from the API
  const [forumQuestionsCount, setForumQuestionsCount] = useState(0);

  useEffect(() => {
    if (!user) return;

    forumApi.getQuestions('', '', 200, 0, user.id)
      .then(res => setForumQuestionsCount(Array.isArray(res) ? res.length : 0))
      .catch(() => {});
  }, [user?.id]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginError('');
    setIsLoggingIn(true);

    if (!loginForm.username.trim()) {
      setLoginError(loginMode === 'sdo' ? 'Введите логин ЭИОС КГУ' : 'Введите логин администратора');
      setIsLoggingIn(false);
      return;
    }
    if (loginMode !== 'staff' && !consent) {
      setLoginError('Отметьте согласие на обработку персональных данных');
      setIsLoggingIn(false);
      return;
    }

    try {
      let res;
      if (loginMode === 'staff') {
        res = await adminLogin(loginForm.username, loginForm.password);
      } else {
        res = await login(loginForm.username, '', loginForm.password, consent);
      }

      if (res && res.error) {
        setLoginError(res.error);
        setIsLoggingIn(false);
        return;
      }

      toast.show(`Успешный вход: ${res.fullName}`, 'success');
      setLoginForm({ username: '', password: '' });
    } catch (err) {
      setLoginError(err.message || 'Ошибка авторизации');
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    toast.show('Вы вышли из аккаунта', 'info');
  };

  const handleAvatarUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const allowedMimeTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
    if (!file.type || !allowedMimeTypes.includes(file.type.toLowerCase())) {
      toast.show('Неподходящий формат. Загрузите изображение PNG, JPEG, JPG или WebP', 'warning');
      e.target.value = '';
      return;
    }

    if (file.size > 15 * 1024 * 1024) {
      toast.show('Файл больше 15 МБ. Выберите изображение поменьше', 'warning');
      e.target.value = '';
      return;
    }

    shrinkAvatar(file)
      .then((dataUrl) => {
        if (updateUserProfile({ photoUrl: dataUrl })) {
          setAvatarLoadError(false);
          toast.show('Фото профиля обновлено', 'success');
        } else {
          toast.show('Браузер не дал сохранить фото. Проверьте, не включён ли приватный режим', 'warning');
        }
      })
      .catch(() => toast.show('Не удалось открыть изображение. Попробуйте другой файл', 'warning'))
      .finally(() => { e.target.value = ''; });
  };

  const handleAvatarReset = () => {
    updateUserProfile({ photoUrl: null });
    setAvatarLoadError(false);
    toast.show(user?.serverPhotoUrl ? 'Вернули фото из ЭИОС' : 'Фото убрано', 'success');
  };

  const selectLoginMode = (mode) => {
    setLoginMode(mode);
    setLoginError('');
  };

  // --- NOT LOGGED IN: SHOW LOGIN FORM WITH MODE SWITCHER ---
  if (!isLoggedIn) {
    const isStaff = loginMode === 'staff';
    const describedBy = [
      capsLockOn ? 'login-caps' : null,
      !isStaff ? 'login-password-hint' : null,
      loginError ? 'login-error' : null
    ].filter(Boolean).join(' ') || undefined;
    const trackCapsLock = (e) => setCapsLockOn(!!e.getModifierState?.('CapsLock'));

    return (
      <div className="container profile-page">
        <section className="login-shell" aria-labelledby="login-page-title">
          <div className="login-aside">
            <img src="/img/mascot-320.png" alt="" className="login-mascot" width="120" height="120" />
            <h1 id="login-page-title">Личный кабинет</h1>
            <p className="login-aside-lead">
              Войдите, и портал запомнит вас: вопросы и расписание будут под рукой.
            </p>
            <ul className="login-perks">
              <li>
                <SectionIcon section="forum" size="sm" quiet />
                <span>Вопросы и ответы на форуме от вашего имени</span>
              </li>
              <li>
                <span className="tile tile-sm tile-quiet" aria-hidden="true"><CalendarDays size={16} strokeWidth={1.75} /></span>
                <span>Расписание вашей группы на главной</span>
              </li>
            </ul>
          </div>

          <div className="login-card">
          <div
            className="segmented login-modes"
            role="tablist"
            aria-label="Способ входа"
            onKeyDown={(e) => handleTabsKeyDown(e, LOGIN_MODES.map(m => m.id), loginMode, selectLoginMode, 'login-tab-')}
          >
            {LOGIN_MODES.map(({ id, label, Icon }) => (
              <button
                key={id}
                id={`login-tab-${id}`}
                type="button"
                role="tab"
                aria-selected={loginMode === id}
                aria-controls="login-panel"
                tabIndex={loginMode === id ? 0 : -1}
                className="segmented-item"
                onClick={() => selectLoginMode(id)}
              >
                <Icon size={16} {...ICON} />
                <span>{label}</span>
              </button>
            ))}
          </div>

          <div id="login-panel" role="tabpanel" aria-labelledby={`login-tab-${loginMode}`}>
            <h2 id="login-title" className="login-title">
              {isStaff ? 'Вход для администрации ИВИТШ' : 'Вход через ЭИОС КГУ'}
            </h2>
            {isStaff && <p className="login-lead">Только для администраторов портала. Преподавателям вход не нужен: расписание, карта и справочник открыты всем.</p>}

            <form onSubmit={handleLogin} className="login-form">
              <div className="field">
                <label className="field-label" htmlFor="login-username">
                  {isStaff ? 'Логин администратора' : 'Логин ЭИОС КГУ'}
                </label>
                <input
                  id="login-username"
                  className="input"
                  type="text"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder={isStaff ? 'Учётная запись деканата' : 'Например, 22-isbo-035'}
                  value={loginForm.username}
                  onChange={e => setLoginForm({ ...loginForm, username: e.target.value })}
                  aria-describedby={loginError ? 'login-error' : undefined}
                  required
                  disabled={isLoggingIn}
                />
              </div>

              <div className="field">
                <label className="field-label" htmlFor="login-password">Пароль</label>
                <div className="input-wrap">
                  <input
                    id="login-password"
                    className="input input-with-action"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={loginForm.password}
                    onChange={e => setLoginForm({ ...loginForm, password: e.target.value })}
                    onKeyDown={trackCapsLock}
                    onKeyUp={trackCapsLock}
                    onBlur={() => setCapsLockOn(false)}
                    aria-describedby={describedBy}
                    disabled={isLoggingIn}
                    required
                  />
                  <button
                    type="button"
                    className="input-action"
                    onClick={() => setShowPassword(v => !v)}
                    aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
                    aria-pressed={showPassword}
                    aria-controls="login-password"
                    disabled={isLoggingIn}
                  >
                    {showPassword ? <EyeOff size={18} {...ICON} /> : <Eye size={18} {...ICON} />}
                  </button>
                </div>
                {capsLockOn && (
                  <p id="login-caps" className="field-hint login-caps" role="status">Включён Caps Lock</p>
                )}
                {!isStaff && (
                  <p id="login-password-hint" className="field-hint">
                    Используется единый логин и пароль от аккаунта ЭИОС КГУ (eios.kosgos.ru).
                  </p>
                )}
              </div>

              {!isStaff && (
                <label className="login-consent">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={e => { setConsent(e.target.checked); if (e.target.checked) setLoginError(''); }}
                    disabled={isLoggingIn}
                    aria-describedby={loginError ? 'login-error' : undefined}
                  />
                  <span>
                    Даю согласие на обработку персональных данных{' '}
                    (<Link to="/privacy#consent">текст согласия</Link>). Портал использует cookie для входа.
                  </span>
                </label>
              )}

              {!loginError && sessionExpired && (
                <p className="login-alert login-alert-warning" role="status">
                  <Clock size={16} {...ICON} />
                  <span>Сессия истекла — войдите снова.</span>
                </p>
              )}
              {loginError && (
                <p id="login-error" className="login-alert" role="alert">
                  <AlertCircle size={16} {...ICON} />
                  <span>{loginError}</span>
                </p>
              )}

              <button
                type="submit"
                className="btn btn-primary btn-block login-submit"
                disabled={isLoggingIn}
                data-loading={isLoggingIn || undefined}
              >
                {isLoggingIn ? (
                  <>
                    <Loader2 size={16} className="spin-icon" {...ICON} />
                    Проверка авторизации…
                  </>
                ) : (
                  <>
                    <LogIn size={16} {...ICON} />
                    {isStaff ? 'Войти в админку' : 'Войти через ЭИОС'}
                  </>
                )}
              </button>
            </form>
          </div>
          </div>
        </section>
      </div>
    );
  }

  // --- LOGGED IN: SHOW PROFILE ---
  const roleLabel = user.role === 'admin' ? 'Администратор' : user.role === 'moderator' ? 'Модератор' : 'Студент ИВИТШ';

  return (
    <div className="container profile-page">
      <header className="page-header">
        <div className="page-heading">
          <SectionIcon section="profile" size="lg" />
          <h1>Личный кабинет</h1>
        </div>
      </header>

      <div className="profile-layout">
        {/* IDENTITY */}
        <section className="card profile-identity" aria-labelledby="profile-name">
          <div className="profile-identity-main">
            <div className="profile-avatar hue-cyan">
              {user.photoUrl && !avatarLoadError ? (
                <img src={user.photoUrl} alt="" onError={() => setAvatarLoadError(true)} />
              ) : (
                <span className="profile-avatar-initials" aria-hidden="true">{initialsOf(user.fullName || user.username)}</span>
              )}
            </div>

            <div className="profile-identity-text">
              <h2 id="profile-name" className="profile-name">{user.fullName}</h2>
              <p className="profile-meta">
                {roleLabel}
                {user.group && <> · <span className="tabular">{user.group}</span></>}
              </p>
              {user.role !== 'admin' && (
                <span className="badge badge-success profile-verified" title="Аккаунт подтверждён через ЭИОС КГУ (eios.kosgos.ru)">
                  <BadgeCheck size={14} {...ICON} />
                  Подтверждено ЭИОС
                </span>
              )}
            </div>
          </div>

          <div className="profile-identity-actions">
            <div className="profile-photo">
              <label className="btn btn-secondary profile-photo-btn">
                <Camera size={16} {...ICON} />
                Сменить фото
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleAvatarUpload}
                  className="visually-hidden"
                  aria-describedby="profile-photo-hint"
                />
              </label>
              {user.hasCustomPhoto && (
                <button type="button" className="btn btn-ghost btn-sm profile-photo-reset" onClick={handleAvatarReset}>
                  {user.serverPhotoUrl ? 'Вернуть фото из ЭИОС' : 'Убрать фото'}
                </button>
              )}
              <p id="profile-photo-hint" className="profile-photo-hint">
                PNG, JPEG или WebP. Фото хранится в этом браузере — на другом устройстве выберите его снова.
              </p>
            </div>

            <button type="button" onClick={handleLogout} className="btn btn-secondary profile-logout">
              <LogOut size={16} {...ICON} />
              Выйти из аккаунта
            </button>
          </div>
        </section>

        <div className="profile-main">
          {/* REAL STATISTICS */}
          <section aria-labelledby="profile-activity-title">
            <div className="section-header">
              <h2 id="profile-activity-title">Активность</h2>
            </div>

            <ul className="card list profile-stats">
              <li className="list-row profile-stat">
                <SectionIcon section="forum" quiet />
                <div className="profile-stat-body">
                  <div className="profile-stat-head">
                    <div className="profile-stat-text">
                      <span className="profile-stat-label">Темы на форуме</span>
                      <span className="profile-stat-meta">созданы вами</span>
                    </div>
                    <span className="profile-stat-value tabular">{forumQuestionsCount}</span>
                  </div>
                </div>
              </li>
            </ul>
          </section>

          {/* ASSOCIATIONS & ACHIEVEMENTS, CONTACTS FOR LEADERS */}
          <ProfileAssociations />
          <ProfileContacts />

          {/* ON THE PHONE: install the portal as an app */}
          <section aria-labelledby="profile-phone-title">
            <div className="section-header">
              <h2 id="profile-phone-title">На телефоне</h2>
            </div>

            <ul className="card list profile-phone">
              <li className="list-row profile-phone-row">
                <span className="tile tile-quiet" aria-hidden="true"><Smartphone size={20} {...ICON} /></span>
                <div className="profile-stat-text">
                  <span className="profile-stat-label">Портал как приложение</span>
                  <span className="profile-stat-meta">
                    {app.installed
                      ? 'Установлен: открывается с главного экрана'
                      : app.ios
                        ? <>В Safari нажмите «Поделиться» <Share size={14} {...ICON} /> и «На экран „Домой“»</>
                        : app.canInstall
                          ? 'Иконка на главном экране, открывается как отдельное приложение'
                          : 'Откройте портал в Chrome на Android или в Safari на iPhone и добавьте на главный экран'}
                  </span>
                </div>
                {app.canInstall && !app.installed && (
                  <button type="button" className="btn btn-secondary profile-phone-action" onClick={app.install}>
                    Установить
                  </button>
                )}
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Profile;
