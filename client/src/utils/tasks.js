// Shared bits of the tasks board, a task's page and the task form.

// Each status has its own color, so the columns are told apart at a glance
export const STATUSES = [
  { id: 'todo', label: 'К выполнению', hue: 'slate' },
  { id: 'in_progress', label: 'В работе', hue: 'blue' },
  { id: 'review', label: 'На проверке', hue: 'amber' },
  { id: 'done', label: 'Готово', hue: 'green' },
];
export const STATUS_LABEL = Object.fromEntries(STATUSES.map(s => [s.id, s.label]));

// Personal task colors: the section hues (see .hue-* in shared.css)
export const COLORS = [
  { id: 'blue', label: 'Синий' },
  { id: 'green', label: 'Зелёный' },
  { id: 'amber', label: 'Жёлтый' },
  { id: 'pink', label: 'Розовый' },
  { id: 'violet', label: 'Фиолетовый' },
  { id: 'slate', label: 'Серый' },
];

const pad2 = (n) => String(n).padStart(2, '0');
const dayKey = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

/**
 * A deadline as a short label and a tone: 'overdue' (missed, not handed in), 'soon' (today or tomorrow)
 * or '' — "Сегодня, 18:00", "Завтра, 9:00", "5 окт., 18:00", "Просрочено: 3 окт."
 */
export const dueInfo = (iso, status) => {
  if (!iso) return null;
  const due = new Date(iso);
  const now = new Date();
  const handedIn = status === 'review' || status === 'done';
  const time = due.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  const date = due.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
  if (due < now && !handedIn) return { label: `Просрочено: ${date}, ${time}`, tone: 'overdue' };
  if (dayKey(due) === dayKey(now)) return { label: `Сегодня, ${time}`, tone: handedIn ? '' : 'soon' };
  if (dayKey(due) === dayKey(tomorrow)) return { label: `Завтра, ${time}`, tone: handedIn ? '' : 'soon' };
  return { label: `${date}, ${time}`, tone: '' };
};

// <input type="datetime-local"> works in local time; the API wants an ISO moment
export const toLocalInput = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  return `${dayKey(d)}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
};
export const fromLocalInput = (value) => (value ? new Date(value).toISOString() : null);

export const formatSize = (bytes) => {
  if (!bytes && bytes !== 0) return '';
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`;
};
