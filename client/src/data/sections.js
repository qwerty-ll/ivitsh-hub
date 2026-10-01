import {
  LayoutDashboard, CalendarDays, CalendarSearch, SquareKanban, Handshake, PartyPopper, DoorOpen, Swords, ShoppingBag, MessageSquare, Map, Users, HelpCircle, UserSquare, Shield, Lock
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
  teachers: { label: 'Преподаватели', short: 'Преподаватели', path: '/teachers', Icon: Users, hue: 'pink', hint: 'Кабинеты и почта' },
  faq: { label: 'Вопросы и ответы', short: 'FAQ', path: '/faq', Icon: HelpCircle, hue: 'amber', hint: 'Частые вопросы' },
  profile: { label: 'Личный кабинет', short: 'Профиль', path: '/profile', Icon: UserSquare, hue: 'cyan' },
  admin: { label: 'Панель управления', short: 'Админка', path: '/admin', Icon: Shield, hue: 'slate' },
  privacy: { label: 'Конфиденциальность', short: 'Cookie', path: '/privacy', Icon: Lock, hue: 'slate' },
};

// Sidebar groups; the profile opens from the user button at the bottom of the sidebar.
export const NAV_GROUPS = [
  { title: null, items: ['dashboard'] },
  { title: 'Учёба', items: ['calendar', 'schedule', 'tasks'] },
  { title: 'Студжизнь', items: ['associations', 'events', 'tribes', 'shop', 'booking'] },
  { title: 'Помощь', items: ['forum', 'map', 'teachers', 'faq'] },
];

// Mobile bottom bar: the sections students open most; the rest stay in the menu.
// Guests have no calendar or tasks of their own: they get the public timetable and events instead.
export const TAB_BAR_ORDER = ['dashboard', 'calendar', 'tasks', 'associations', 'profile'];
const GUEST_TABS = { calendar: 'schedule', tasks: 'events' };
export const tabBarOrder = (isLoggedIn) => (isLoggedIn ? TAB_BAR_ORDER : TAB_BAR_ORDER.map(id => GUEST_TABS[id] || id));
