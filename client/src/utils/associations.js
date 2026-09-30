// Shared bits of the associations pages, the profile and the admin panel.

// The viewer's place in an association as a badge; null when there is nothing to show
export const STATUS_BADGE = (role, status) => {
  if (status === 'approved') return role === 'leader'
    ? { label: 'Вы руководитель', tone: 'badge-accent' }
    : { label: 'Вы участник', tone: 'badge-success' };
  if (status === 'pending') return { label: 'Заявка на рассмотрении', tone: 'badge-warning' };
  return null;
};

// "Спортивное программирование" -> "СП", "Е-спорт" -> "ЕС", "Театр" -> "Т"
export const monogram = (name = '') => {
  const words = name.replace(/[^\p{L}\p{N}]+/gu, ' ').trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0] || '?')[0].toUpperCase();
};

export const plural = (n, [one, few, many]) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
};

// "Иванов Артём Сергеевич" -> "Иванов Артём"
export const shortName = (fullName = '') => fullName.split(' ').slice(0, 2).join(' ');

// Every association keeps one color wherever it shows up (its tile in the catalog, chips on task cards)
const ASSOC_HUES = ['blue', 'orange', 'violet', 'green', 'pink', 'amber', 'cyan', 'olive', 'teal', 'red'];
export const assocHue = (id) => ASSOC_HUES[Math.abs(Number(id) || 0) % ASSOC_HUES.length];
