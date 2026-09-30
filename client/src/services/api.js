// Unified API client for the FastAPI backend.
// Authentication is an httpOnly cookie set by the backend: page scripts never see the JWT.
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const CACHE_PREFIX = 'portal_swr_cache_';

// Only public reference data may be kept in localStorage for offline use.
// Personal or admin responses must never outlive the session on a shared computer.
const CACHEABLE_PREFIXES = [
  '/api/v1/teachers',
  '/api/v1/subjects',
  '/api/v1/announcements',
  '/api/v1/faq',
  '/api/v1/schedule/',
  '/api/v1/rooms',
];

const isCacheable = (endpoint) => CACHEABLE_PREFIXES.some((prefix) => endpoint.startsWith(prefix));

// Fired when the server rejects the session (expired, revoked or blocked); AuthContext signs the user out.
export const SESSION_EXPIRED_EVENT = 'portal:session-expired';
// A 401 from these means wrong credentials, not an expired session.
const LOGIN_ENDPOINTS = ['/api/v1/auth/eios-login', '/api/v1/auth/admin-login', '/api/v1/auth/logout'];

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export const clearApiCache = () => {
  try {
    Object.keys(localStorage)
      .filter((key) => key.startsWith(CACHE_PREFIX))
      .forEach((key) => localStorage.removeItem(key));
  } catch {
    // localStorage unavailable (private mode) — nothing cached anyway
  }
};

const readCache = (endpoint) => {
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_PREFIX + endpoint) || 'null');
    return cached && cached.data !== undefined ? cached.data : undefined;
  } catch {
    return undefined;
  }
};

const writeCache = (endpoint, data) => {
  try {
    localStorage.setItem(CACHE_PREFIX + endpoint, JSON.stringify({ timestamp: Date.now(), data }));
  } catch {
    // Ignore quota errors
  }
};

export const apiFetch = async (endpoint, options = {}) => {
  const { retries, timeout, useCache, headers: extraHeaders, ...fetchOptions } = options;
  const method = (fetchOptions.method || 'GET').toUpperCase();
  const isGet = method === 'GET';
  const headers = {
    'Content-Type': 'application/json',
    // Required by the backend CSRF check for cookie-authenticated writes.
    'X-Requested-With': 'XMLHttpRequest',
    ...extraHeaders,
  };
  // Offline there is nothing to wait for: go straight to the saved copy
  const offline = typeof navigator !== 'undefined' && navigator.onLine === false;
  const maxRetries = offline ? 0 : (retries !== undefined ? retries : (isGet ? 2 : 0));
  const timeoutMs = timeout || 12000;
  const enableCache = useCache !== false && isGet && isCacheable(endpoint);

  let lastError = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    let res;
    try {
      res = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...fetchOptions,
        credentials: 'include',
        signal: controller.signal,
        headers,
      });
    } catch (err) {
      clearTimeout(timeoutId);
      // Network failure or timeout: retry GETs with backoff.
      lastError = err.name === 'AbortError'
        ? new ApiError('Превышено время ожидания ответа сервера (слабое соединение). Попробуйте позже.', 0)
        : new ApiError('Нет соединения с сервером', 0);
      if (isGet && attempt < maxRetries) {
        await new Promise((resolve) => setTimeout(resolve, (attempt + 1) * 1000));
        continue;
      }
      break;
    }
    clearTimeout(timeoutId);

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      const detail = typeof errorData.detail === 'string' ? errorData.detail : `Ошибка сервера: ${res.status}`;
      if (res.status === 401 && !LOGIN_ENDPOINTS.includes(endpoint)) {
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
      }
      // The server answered: an HTTP error is authoritative and is never masked by cached data.
      throw new ApiError(detail, res.status);
    }

    const data = await res.json();
    if (enableCache) writeCache(endpoint, data);
    return data;
  }

  // Offline fallback only for public reference data.
  if (enableCache) {
    const cached = readCache(endpoint);
    if (cached !== undefined) return cached;
  }
  throw lastError || new ApiError('Ошибка сети', 0);
};

const json = (method, body) => ({ method, body: JSON.stringify(body) });

// Auth Services
export const authApi = {
  // consent: the "I agree to personal data processing" box; the server refuses the sign-in without it
  eiosLogin: (username, password, groupNumber = '', consent = false) =>
    apiFetch('/api/v1/auth/eios-login', json('POST', { username, password, group_number: groupNumber, consent })),
  adminLogin: (username, password) =>
    apiFetch('/api/v1/auth/admin-login', json('POST', { username, password })),
  logout: () =>
    apiFetch('/api/v1/auth/logout', { method: 'POST' }),
  getMe: () =>
    apiFetch('/api/v1/auth/me'),
  updateProfile: (data) =>
    apiFetch('/api/v1/auth/me', json('PATCH', data)),
};

// Forum Services
export const forumApi = {
  getQuestions: (category = '', search = '', limit = 50, offset = 0, authorId = null) => {
    const query = new URLSearchParams({ limit, offset });
    if (category) query.append('category', category);
    if (search) query.append('search', search);
    if (authorId !== null) query.append('author_id', authorId);
    return apiFetch(`/api/v1/forum/questions?${query.toString()}`);
  },
  createQuestion: (data) =>
    apiFetch('/api/v1/forum/questions', json('POST', data)),
  getQuestionDetail: (id) =>
    apiFetch(`/api/v1/forum/questions/${id}`),
  getAnswers: (id) =>
    apiFetch(`/api/v1/forum/questions/${id}/answers`),
  postAnswer: (id, text) =>
    apiFetch(`/api/v1/forum/questions/${id}/answers`, json('POST', { content: text })),
  vote: (id, voteType) =>
    apiFetch(`/api/v1/forum/questions/${id}/vote`, json('POST', { vote_type: voteType })),
  deleteQuestion: (id) =>
    apiFetch(`/api/v1/forum/questions/${id}`, { method: 'DELETE' }),
  togglePin: (id) =>
    apiFetch(`/api/v1/forum/questions/${id}/pin`, { method: 'POST' }),
  deleteAnswer: (answerId) =>
    apiFetch(`/api/v1/forum/answers/${answerId}`, { method: 'DELETE' }),
  toggleSolution: (answerId) =>
    apiFetch(`/api/v1/forum/answers/${answerId}/solution`, { method: 'POST' }),
};

// Admin Services
export const adminApi = {
  // Users
  getUsers: (limit = 100, offset = 0) =>
    apiFetch(`/api/v1/admin/users?limit=${limit}&offset=${offset}`),
  updateUserRole: (userId, role) =>
    apiFetch(`/api/v1/admin/users/${userId}/role`, json('PATCH', { role })),
  setUserBlocked: (userId, blocked) =>
    apiFetch(`/api/v1/admin/users/${userId}/block`, json('PATCH', { blocked })),
  deleteUser: (userId) =>
    apiFetch(`/api/v1/admin/users/${userId}`, { method: 'DELETE' }),

  // Teachers
  getTeachers: () => apiFetch('/api/v1/teachers'),
  createTeacher: (data) =>
    apiFetch('/api/v1/admin/teachers', json('POST', data)),
  deleteTeacher: (id) =>
    apiFetch(`/api/v1/admin/teachers/${id}`, { method: 'DELETE' }),

  // Announcements
  getAnnouncements: () => apiFetch('/api/v1/announcements'),
  createAnnouncement: (data) =>
    apiFetch('/api/v1/admin/announcements', json('POST', data)),
  updateAnnouncement: (id, data) =>
    apiFetch(`/api/v1/admin/announcements/${id}`, json('PUT', data)),
  deleteAnnouncement: (id) =>
    apiFetch(`/api/v1/admin/announcements/${id}`, { method: 'DELETE' }),

  // FAQ
  getFaq: () => apiFetch('/api/v1/faq'),
  createFaq: (data) =>
    apiFetch('/api/v1/admin/faq', json('POST', data)),
  updateFaq: (id, data) =>
    apiFetch(`/api/v1/admin/faq/${id}`, json('PUT', data)),
  deleteFaq: (id) =>
    apiFetch(`/api/v1/admin/faq/${id}`, { method: 'DELETE' }),

  // Subjects
  getSubjects: () => apiFetch('/api/v1/subjects'),
  createSubject: (data) =>
    apiFetch('/api/v1/admin/subjects', json('POST', data)),
  updateSubject: (id, data) =>
    apiFetch(`/api/v1/admin/subjects/${id}`, json('PUT', data)),
  deleteSubject: (id) =>
    apiFetch(`/api/v1/admin/subjects/${id}`, { method: 'DELETE' }),
};

// Public read access to reference data managed in the admin panel
export const contentApi = {
  getTeachers: () => adminApi.getTeachers(),
  getSubjects: () => adminApi.getSubjects(),
  getFaq: () => adminApi.getFaq(),
  getAnnouncements: () => adminApi.getAnnouncements(),
};

// Chatbot Services
export const chatApi = {
  // group: the group picked in the dashboard schedule, for visitors who have not signed in
  // The server may wait for GigaChat's single stream and call the portal's functions: up to ~20 s
  sendMessage: (message, history, group = null) =>
    apiFetch('/api/v1/chat', { ...json('POST', { message, history, ...(group ? { group } : {}) }), timeout: 24000 }),
};

// Schedule EIOS Services
export const scheduleApi = {
  getYears: () =>
    apiFetch('/api/v1/schedule/years'),
  getGroups: (year = '2025-2026') =>
    apiFetch(`/api/v1/schedule/groups?year=${encodeURIComponent(year)}`),
  getTeachers: (year = '2025-2026') =>
    apiFetch(`/api/v1/schedule/teachers?year=${encodeURIComponent(year)}`),
  getAuditories: (year = '2025-2026') =>
    apiFetch(`/api/v1/schedule/auditories?year=${encodeURIComponent(year)}`),
  getSchedule: (idGroup = null, year = '2025-2026', sdate = '', idTeacher = null, idAud = null) => {
    const query = new URLSearchParams({ year });
    if (idGroup) query.append('idGroup', idGroup);
    if (idTeacher) query.append('idTeacher', idTeacher);
    if (idAud) query.append('idAud', idAud);
    if (sdate) query.append('sdate', sdate);
    return apiFetch(`/api/v1/schedule/rasp?${query.toString()}`);
  },
  // Today's lessons of the portal's teachers: { date, teachers: { [teacherId]: lessons[] } }
  getTeachersToday: () =>
    apiFetch('/api/v1/schedule/teachers/today', { retries: 0, timeout: 20000 }),
};

// Rooms of корпус Б: places, computers, OS, equipment, software; today's pairs in one of them
export const roomsApi = {
  getRooms: () => apiFetch('/api/v1/rooms'),
  getToday: (number) => apiFetch(`/api/v1/rooms/${encodeURIComponent(number)}/today`, { retries: 0, useCache: false }),
};

// Documents ВИТШик prepares (explanatory note, retake request), downloaded as Word or PDF
const filenameOf = (disposition, fallback) => {
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition || '');
  if (star) {
    try { return decodeURIComponent(star[1]); } catch { /* malformed: use the fallback */ }
  }
  return fallback;
};

export const documentsApi = {
  pairs: (date) => apiFetch(`/api/v1/documents/pairs?date=${encodeURIComponent(date)}`, { retries: 0 }),
  download: async (kind, format, fields) => {
    let res;
    try {
      res = await fetch(`${API_BASE_URL}/api/v1/documents/${kind}?format=${format}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify(fields),
      });
    } catch {
      throw new ApiError('Нет соединения с сервером', 0);
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      if (res.status === 401) window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
      const detail = typeof data.detail === 'string'
        ? data.detail
        : (res.status === 422 ? 'Проверьте поля: что-то заполнено не так.' : `Ошибка сервера: ${res.status}`);
      throw new ApiError(detail, res.status);
    }
    const blob = await res.blob();
    const name = filenameOf(res.headers.get('Content-Disposition'), `document.${format}`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return name;
  },
};
