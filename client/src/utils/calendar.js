// Dates for the calendar, the dashboard's "Сегодня" and the meeting forms. Local time is Kostroma time for students.

const pad2 = (n) => String(n).padStart(2, '0');

export const dayKey = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
export const parseDay = (key) => new Date(`${key}T00:00:00`);
export const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };

/** Monday of the week the day falls in */
export const weekStart = (d) => {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  return addDays(x, -((x.getDay() + 6) % 7));
};

export const timeLabel = (iso) => new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
export const minutesOf = (iso) => { const d = new Date(iso); return d.getHours() * 60 + d.getMinutes(); };

const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/** "Сегодня", "Завтра", "Вчера" or "Пт, 3 октября" */
export const dayTitle = (key, { weekday = 'short' } = {}) => {
  const today = dayKey(new Date());
  if (key === today) return 'Сегодня';
  if (key === dayKey(addDays(new Date(), 1))) return 'Завтра';
  if (key === dayKey(addDays(new Date(), -1))) return 'Вчера';
  return capitalize(parseDay(key).toLocaleDateString('ru-RU', { weekday, day: 'numeric', month: 'long' }));
};

/** "22–28 сентября", "29 сентября – 5 октября" */
export const rangeTitle = (from, to) => {
  const sameMonth = from.getMonth() === to.getMonth();
  const left = from.toLocaleDateString('ru-RU', sameMonth ? { day: 'numeric' } : { day: 'numeric', month: 'long' });
  const right = to.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
  return sameMonth ? `${left}–${right}` : `${left} – ${right}`;
};

// What each kind of entry is called and colored like (section hues from shared.css)
export const TYPES = {
  lesson: { label: 'Пары', one: 'Пара', hue: 'blue' },
  meeting: { label: 'Собрания', one: 'Собрание', hue: 'olive' },
  event: { label: 'Мероприятия', one: 'Мероприятие', hue: 'red' },
  task: { label: 'Задачи', one: 'Задача', hue: 'teal' },
  homework: { label: 'ДЗ группы', one: 'ДЗ группы', hue: 'violet' },
};
export const hueOf = (item) => (item.type === 'task' && item.color && !item.association ? item.color : TYPES[item.type].hue);

// The student's subgroup (0 = show every subgroup), remembered on this device
const SUBGROUP_KEY = 'portal_subgroup';
export const readSubgroup = () => {
  try { return Number(localStorage.getItem(SUBGROUP_KEY)) || 0; } catch { return 0; }
};
export const saveSubgroup = (n) => {
  try { localStorage.setItem(SUBGROUP_KEY, String(n)); } catch { /* private mode */ }
};
export const fitsSubgroup = (item, subgroup) => item.type !== 'lesson' || !subgroup || !item.subgroup || item.subgroup === subgroup;

// Deadlines are a moment in time; lessons and meetings last a while
export const isDeadline = (item) => !item.ends_at;

/**
 * Side-by-side columns for overlapping timed entries of one day, like a week view in Google Calendar:
 * returns [{ item, col, cols }], where cols is the width of the overlapping cluster.
 */
export const layoutDay = (items) => {
  const sorted = [...items].sort((a, b) => minutesOf(a.starts_at) - minutesOf(b.starts_at) || minutesOf(b.ends_at) - minutesOf(a.ends_at));
  const placed = [];
  let cluster = [];
  let clusterEnd = -1;
  const flush = () => {
    const cols = Math.max(1, ...cluster.map(p => p.col + 1));
    cluster.forEach(p => { p.cols = cols; });
    cluster = [];
  };
  sorted.forEach((item) => {
    const start = minutesOf(item.starts_at);
    const end = Math.max(start + 20, minutesOf(item.ends_at));
    if (start >= clusterEnd) { flush(); clusterEnd = -1; }
    const taken = new Set(cluster.filter(p => p.end > start).map(p => p.col));
    let col = 0;
    while (taken.has(col)) col += 1;
    const entry = { item, col, cols: 1, start, end };
    cluster.push(entry);
    placed.push(entry);
    clusterEnd = Math.max(clusterEnd, end);
  });
  flush();
  return placed;
};

// Moscow wall-clock inputs for the meeting form
export const joinDateTime = (date, time) => (date && time ? new Date(`${date}T${time}`).toISOString() : null);
export const splitDateTime = (iso) => {
  if (!iso) return { date: '', time: '' };
  const d = new Date(iso);
  return { date: dayKey(d), time: `${pad2(d.getHours())}:${pad2(d.getMinutes())}` };
};
