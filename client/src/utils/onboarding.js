// Progress of the "Знакомство с порталом" checklist on the dashboard.
// Kept per account (like the chosen photo) so an expired session or signing out does not reset it;
// guests use a shared key that is merged into the account on the next visit.
export const ONBOARDING_EVENT = 'portal:onboarding';

const GUEST_KEY = 'onboarding_completed_tasks';
const keyFor = (userId) => (userId ? `portal_onboarding_${userId}` : GUEST_KEY);

// Opening these sections from anywhere (sidebar, tab bar, links) completes the matching step.
// ("Зайти в личный кабинет" means signing in, so App marks it for any signed-in visit instead.)
export const ROUTE_STEPS = {
  '/schedule': 'schedule',
  '/faq': 'faq',
  '/teachers': 'teachers',
  '/map': 'map',
  '/forum': 'forum',
};

const read = (key) => {
  try {
    const value = JSON.parse(localStorage.getItem(key) || '[]');
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
};

export const readSteps = (userId) => {
  const steps = read(keyFor(userId));
  return userId ? [...new Set([...steps, ...read(GUEST_KEY)])] : steps;
};

export const markStep = (userId, stepId) => {
  if (!stepId) return;
  const steps = readSteps(userId);
  if (steps.includes(stepId) && read(keyFor(userId)).length === steps.length) return;
  try {
    localStorage.setItem(keyFor(userId), JSON.stringify([...new Set([...steps, stepId])]));
  } catch { /* storage unavailable */ }
  window.dispatchEvent(new Event(ONBOARDING_EVENT));
};
