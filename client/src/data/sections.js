import {
  LayoutDashboard, CalendarDays, CalendarSearch, SquareKanban, Handshake, PartyPopper, DoorOpen, Swords, ShoppingBag, MessageSquare, Map, Users, HelpCircle, UserSquare, Shield, Lock, Coins, LifeBuoy
} from 'lucide-react';

// One place for every section's name, route, icon and wayfinding hue.
// The hue only colors the section's icon tile (see .tile and .hue-* in shared.css).
// auth: the section is personal and empty without signing in, so guests do not see it in the menu.
export const SECTIONS = {
  dashboard: { label: 'Главная', short: 'Главная', path: '/', Icon: LayoutDashboard, hue: 'blue' },
  calendar: { label: 'Календарь', short: 'Календарь', path: '/calendar', Icon: CalendarDays, hue: 'orange', hint: 'Пары, собрания, дедлайны', auth: true },
  schedule: { label: 'Расписание', short: 'Расписание', path: '/schedule', Icon: CalendarSearch, hue: 'orange', hint: 'Группы, преподаватели, аудитории' },
  tasks: { label: 'Задачи', short: 'Задачи', path: '/tasks', Icon: SquareKanban, hue: 'teal', hint: 'Канбан и дедлайны', auth: true },
  associations: { label: 'Объединения', short: 'Объединения', path: '/associations', Icon: Handshake, hue: 'olive', hint: 'Клубы, медиа, волонтёры' },
  events: { label: 'Мероприятия', short: 'События', path: '/events', Icon: PartyPopper, hue: 'red', hint: 'Запись и ПГАС' },
  tribes: { label: 'Трайбы', short: 'Трайбы', path: '/tribes', Icon: Swords, hue: 'violet', hint: 'Турнир команд', auth: true },
  shop: { label: 'Магазин', short: 'Магазин', path: '/shop', Icon: ShoppingBag, hue: 'green', hint: 'Мерч за биты', auth: true },
  booking: { label: 'Бронь 108', short: 'Бронь', path: '/booking', Icon: DoorOpen, hue: 'cyan', hint: 'Коворкинг и ноутбуки', auth: true },
  forum: { label: 'Форум', short: 'Форум', path: '/forum', Icon: MessageSquare, hue: 'violet', hint: 'Спросить сокурсников' },
  map: { label: 'Карта кампуса', short: 'Карта', path: '/map', Icon: Map, hue: 'green', hint: 'Найти аудиторию' },
  teachers: { label: 'Преподаватели', short: 'Педагоги', path: '/teachers', Icon: Users, hue: 'pink', hint: 'Кабинеты и почта' },
  faq: { label: 'Вопросы и ответы', short: 'FAQ', path: '/faq', Icon: HelpCircle, hue: 'amber', hint: 'Частые вопросы' },
  profile: { label: 'Личный кабинет', short: 'Профиль', path: '/profile', Icon: UserSquare, hue: 'cyan' },
  admin: { label: 'Панель управления', short: 'Админка', path: '/admin', Icon: Shield, hue: 'slate' },
  privacy: { label: 'Конфиденциальность', short: 'Cookie', path: '/privacy', Icon: Lock, hue: 'slate' },
};

// Related sections share one menu entry and show tabs on top of their pages (nothing is removed: every page
// keeps its address). The entry leads to the first tab the visitor can open.
export const HUBS = {
  calendar: { label: 'Календарь', short: 'Календарь', Icon: CalendarDays, hue: 'orange', tabs: ['calendar', 'schedule'], hint: 'Пары, собрания, расписание' },
  bits: { label: 'Биты', short: 'Биты', Icon: Coins, hue: 'violet', tabs: ['tribes', 'shop'], hint: 'Трайбы и магазин мерча' },
  help: { label: 'Помощь', short: 'Помощь', Icon: LifeBuoy, hue: 'amber', tabs: ['forum', 'map', 'teachers', 'faq'], hint: 'Форум, карта, преподаватели, FAQ' },
};

// Tabs of a hub the visitor can open (guests: no personal sections)
export const hubTabs = (hubId, isLoggedIn) => HUBS[hubId].tabs.filter(id => isLoggedIn || !SECTIONS[id].auth);

// The hub whose tab page this is (exact section pages only, not e.g. a forum question)
export const hubOfPath = (pathname) => Object.keys(HUBS).find(
  hubId => HUBS[hubId].tabs.some(id => SECTIONS[id].path === pathname),
);

// One menu entry: a section, or a hub ("hub:<id>") standing for its tabs
export const navEntry = (id, isLoggedIn) => {
  if (!id.startsWith('hub:')) {
    const s = SECTIONS[id];
    return { key: id, ...s, paths: [s.path], hidden: !isLoggedIn && s.auth };
  }
  const hubId = id.slice(4);
  const hub = HUBS[hubId];
  const tabs = hubTabs(hubId, isLoggedIn);
  const first = tabs[0] && SECTIONS[tabs[0]];
  return {
    key: id, ...hub,
    // A guest's "Календарь" is the public timetable
    label: tabs.length === 1 ? first.label : hub.label,
    short: tabs.length === 1 ? first.short : hub.short,
    Icon: tabs.length === 1 ? first.Icon : hub.Icon,
    path: first ? first.path : '/',
    paths: tabs.map(t => SECTIONS[t].path),
    hidden: tabs.length === 0,
  };
};

// Sidebar groups; the profile opens from the user button at the bottom of the sidebar.
export const NAV_GROUPS = [
  { title: null, items: ['dashboard'] },
  { title: 'Учёба', items: ['hub:calendar', 'tasks'] },
  { title: 'Студжизнь', items: ['associations', 'events', 'booking', 'hub:bits'] },
  { title: null, items: ['hub:help'] },
];

// Mobile bottom bar: the sections students open most; the rest stay in the menu.
// Guests have no tasks of their own: they get the events instead (the calendar hub turns into the timetable).
export const TAB_BAR_ORDER = ['dashboard', 'hub:calendar', 'tasks', 'associations', 'profile'];
const GUEST_TABS = { tasks: 'events' };
export const tabBarOrder = (isLoggedIn) => (isLoggedIn ? TAB_BAR_ORDER : TAB_BAR_ORDER.map(id => GUEST_TABS[id] || id));
