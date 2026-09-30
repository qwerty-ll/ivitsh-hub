/** Russian plural form: plural(5, ['бит', 'бита', 'бит']) → 'бит' */
export const plural = (n, [one, few, many]) => {
  const m10 = Math.abs(n) % 10, m100 = Math.abs(n) % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
};
