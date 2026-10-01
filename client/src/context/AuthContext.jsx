import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authApi, clearApiCache, SESSION_EXPIRED_EVENT } from '../services/api';
import { dataUrlToBlob } from '../utils/avatar';

const AuthContext = createContext(null);
const AUTH_STORAGE_KEY = 'portal_auth_user';

// Per-user data kept in the browser; removed on logout so the next person on a shared computer starts clean.
const USER_SCOPED_KEYS = [AUTH_STORAGE_KEY, 'onboarding_completed_tasks', 'portal_group_number', 'portal_sched_group', 'portal_subgroup'];
// Left behind by older versions of the portal (JWT in localStorage, cached personal/admin responses).
const LEGACY_KEYS = [
  'portal_jwt_token', 'portal_faq', 'portal_announcements', 'forum_questions',
  // the removed freshman guide, its mini-games and daily reminder
  'freshman_roadmap_completed', 'vitshik_coins_count', 'vitshik_pets_count', 'ivitsh_last_daily_notif',
];

const safeRemove = (key) => {
  try { localStorage.removeItem(key); } catch { /* storage unavailable */ }
};

const clearUserStorage = () => {
  USER_SCOPED_KEYS.forEach(safeRemove);
  clearApiCache();
};

// Older versions kept a chosen photo only in the browser under this key; it is moved to the server once.
const avatarKey = (id) => `portal_avatar_${id}`;
const readAvatar = (id) => {
  try { return id ? localStorage.getItem(avatarKey(id)) : null; } catch { return null; }
};

const toClientUser = (apiUser) => ({
  id: apiUser.id,
  username: apiUser.username,
  fullName: apiUser.full_name || apiUser.username,
  group: apiUser.group_number || '',
  // EIOS timetable id of that group; missing for a group typed by hand
  groupId: apiUser.eios_group_id || null,
  role: apiUser.role || 'student',
  // The .env administrator: the only one who grants and revokes administrator rights
  mainAdmin: apiUser.auth_source === 'local',
  serverPhotoUrl: apiUser.userpictureurl || '',
  // The photo the user uploaded (kept on the server)
  customPhotoUrl: apiUser.photo_url || '',
  // Whether other signed-in students see the photo next to the name
  photoPublic: apiUser.photo_public !== false,
});

// photoUrl shown in the UI: the uploaded photo, else the EIOS picture
const withPhoto = (u) => {
  const custom = u.customPhotoUrl || '';
  return { ...u, photoUrl: custom || u.serverPhotoUrl || '', hasCustomPhoto: !!custom };
};

// Profiles cached by older versions kept a chosen photo inline; move it to its own key (uploaded later).
const fromCache = (cached) => {
  const inline = typeof cached.photoUrl === 'string' && cached.photoUrl.startsWith('data:') ? cached.photoUrl : '';
  if (inline && !readAvatar(cached.id)) {
    try {
      // Free the space first: the photo must not sit in storage twice
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ ...cached, photoUrl: '' }));
      localStorage.setItem(avatarKey(cached.id), inline);
    } catch { /* storage full */ }
  }
  const serverPhotoUrl = cached.serverPhotoUrl ?? (inline ? '' : cached.photoUrl || '');
  return withPhoto({ ...cached, serverPhotoUrl });
};

export const AuthProvider = ({ children }) => {
  // The cached profile only drives the UI until /auth/session confirms it; the server enforces all access.
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem(AUTH_STORAGE_KEY);
      return saved ? fromCache(JSON.parse(saved)) : null;
    } catch {
      return null;
    }
  });

  const saveUser = useCallback((nextUser) => {
    const shown = nextUser ? withPhoto(nextUser) : null;
    setUser(shown);
    try {
      if (shown) {
        const { photoUrl, hasCustomPhoto, ...cacheable } = shown;
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(cacheable));
      }
    } catch { /* storage unavailable */ }
  }, []);

  // A photo an older version kept only in this browser goes to the server once, then leaves the browser
  const migrateLocalPhoto = useCallback((id, serverHasPhoto) => {
    const local = readAvatar(id);
    if (!local) return;
    const forget = () => safeRemove(avatarKey(id));
    if (serverHasPhoto || !local.startsWith('data:image/')) { forget(); return; }
    authApi.uploadPhoto(dataUrlToBlob(local))
      .then((res) => { forget(); saveUser(toClientUser(res)); })
      .catch(() => { /* try again on the next visit */ });
  }, [saveUser]);

  // Set when the server ended the session on its own, so the login form can explain why.
  const [sessionExpired, setSessionExpired] = useState(false);

  // Signs out locally. Per-user data is only wiped when someone was actually signed in,
  // so a guest's onboarding progress survives the 401s that guests always get.
  const resetSession = useCallback(() => {
    let hadUser = false;
    try { hadUser = !!localStorage.getItem(AUTH_STORAGE_KEY); } catch { /* ignore */ }
    setUser(null);
    if (hadUser) clearUserStorage();
    return hadUser;
  }, []);

  useEffect(() => {
    const onExpired = () => {
      if (resetSession()) setSessionExpired(true);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [resetSession]);

  // True once the server has said who is signed in (pages that need a role wait for it before redirecting)
  const [sessionChecked, setSessionChecked] = useState(false);

  // Restore & verify the session on app load. /auth/session answers guests with 200 and no user,
  // so a visitor's console stays free of 401 errors.
  useEffect(() => {
    LEGACY_KEYS.forEach(safeRemove);
    authApi.getSession()
      .then(({ user: res } = {}) => {
        if (!res || !res.id) {
          // The cookie is gone or dead: a cached profile means the session ended
          if (resetSession()) setSessionExpired(true);
          return;
        }
        const fresh = toClientUser(res);
        migrateLocalPhoto(res.id, !!fresh.customPhotoUrl);
        let cached = null;
        try { cached = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || 'null'); } catch { /* ignore */ }
        // A different account is signed in now: drop the previous person's local data.
        if (cached && cached.id !== res.id) clearUserStorage();
        saveUser(fresh);
      })
      .catch((err) => {
        // A 401 is handled by the SESSION_EXPIRED_EVENT listener above.
        if (err.status !== 401) {
          console.warn('[AuthContext] Could not verify session, keeping cached profile:', err.message);
        }
      })
      .finally(() => setSessionChecked(true));
  }, [saveUser, resetSession, migrateLocalPhoto]);

  const completeLogin = (res) => {
    if (!res || !res.user) return { error: 'Не удалось авторизоваться' };
    if (user && user.id !== res.user.id) clearUserStorage();
    setSessionExpired(false);
    const nextUser = toClientUser(res.user);
    saveUser(nextUser);
    migrateLocalPhoto(res.user.id, !!nextUser.customPhotoUrl);
    return nextUser;
  };

  // Student login through EIOS KSU (credentials are checked by the backend)
  const login = async (loginInput, groupInput = '', passwordInput = '', consent = false, remember = false) => {
    try {
      return completeLogin(await authApi.eiosLogin(loginInput.trim(), passwordInput, groupInput.trim(), consent, remember));
    } catch (err) {
      return { error: err.message || 'Ошибка входа через ЭИОС КГУ. Проверьте логин и пароль' };
    }
  };

  const adminLogin = async (username, password) => {
    try {
      return completeLogin(await authApi.adminLogin(username.trim(), password));
    } catch (err) {
      return { error: err.message || 'Неверный логин или пароль администратора' };
    }
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } catch {
      // The cookie expires on its own; local state is cleared regardless.
    }
    setUser(null);
    clearUserStorage();
  };

  const updateUserProfile = (data = {}) => {
    if (!user) return false;
    saveUser({ ...user, ...(data.group !== undefined ? { group: data.group } : {}) });
    return true;
  };

  // Uploads a new profile photo (a Blob) or, with null, removes it; throws ApiError on failure
  const setPhoto = async (blob) => {
    const res = blob ? await authApi.uploadPhoto(blob) : await authApi.deletePhoto();
    saveUser(toClientUser(res));
  };

  // Shows or hides the photo from other students: the switch moves at once, and back if the server refuses
  const setPhotoPublic = async (visible) => {
    const before = user;
    saveUser({ ...user, photoPublic: visible });
    try {
      saveUser(toClientUser(await authApi.updateProfile({ photo_public: visible })));
    } catch (err) {
      saveUser(before);
      throw err;
    }
  };

  const isLoggedIn = !!user;
  const isAdmin = user?.role === 'admin';
  const isMainAdmin = isAdmin && !!user?.mainAdmin;
  const isModerator = user?.role === 'moderator';
  const canModerate = isAdmin || isModerator;

  return (
    <AuthContext.Provider value={{
      user,
      setPhoto,
      setPhotoPublic,
      sessionChecked,
      isLoggedIn,
      isAdmin,
      isMainAdmin,
      isModerator,
      canModerate,
      sessionExpired,
      login,
      adminLogin,
      logout,
      updateUserProfile
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
