// Shared bits of the events list, an event's page and the event form.
import { dayKey, dayTitle, timeLabel } from './calendar';

export const ROLE_LABEL = { participant: 'Участник', volunteer: 'Волонтёр' };
export const SOURCE_LABEL = { self: 'сам(а)', leader: 'руководитель', admin: 'администрация', admin_group: 'группой' };

/** "Пт, 3 октября, 18:00–20:00" or "3 октября 10:00 – 5 октября 18:00" */
export const eventWhen = (e) => {
  const from = new Date(e.starts_at);
  const to = new Date(e.ends_at);
  if (dayKey(from) === dayKey(to)) return `${dayTitle(dayKey(from), { weekday: 'short' })}, ${timeLabel(e.starts_at)}–${timeLabel(e.ends_at)}`;
  const fmt = (d) => d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
  return `${fmt(from)} ${timeLabel(e.starts_at)} – ${fmt(to)} ${timeLabel(e.ends_at)}`;
};

export const organizerOf = (e) => (e.association ? e.association.name : 'Администрация ИВИТШ');

/** "12 из 30 мест" / "12 участников" */
export const seatsText = (count, limit) => (limit ? `${count} из ${limit}` : String(count));

export const isOver = (e) => new Date(e.ends_at) <= new Date();
export const isFull = (e, role) => (role === 'volunteer'
  ? e.volunteer_limit !== null && e.volunteers >= e.volunteer_limit
  : e.participant_limit !== null && e.participants >= e.participant_limit);

/** Semesters for the ПГАС summary: the current one and three before it, newest first.
 * Autumn: 1 September – 31 January; spring: 1 February – 31 August (as on the server). */
export const semesters = (today = new Date()) => {
  const m = today.getMonth();
  let autumn = m >= 8 || m === 0;
  let year = m === 0 ? today.getFullYear() - 1 : today.getFullYear();
  const list = [];
  for (let i = 0; i < 4; i += 1) {
    if (autumn) {
      list.push({ id: `${year}-a`, label: `Осень ${year}/${year + 1}`, start: `${year}-09-01`, end: `${year + 1}-01-31` });
    } else {
      list.push({ id: `${year}-s`, label: `Весна ${year - 1}/${year}`, start: `${year}-02-01`, end: `${year}-08-31` });
      year -= 1;
    }
    autumn = !autumn;
  }
  return list;
};
