import {
  LayoutDashboard, CalendarDays, CalendarSearch, SquareKanban, Handshake, PartyPopper, DoorOpen, Swords, ShoppingBag, MessageSquare, Map, Users, HelpCircle, UserSquare, Shield, Lock
} from 'lucide-react';

// One place for every section's name, route, icon and wayfinding hue.
// The hue only colors the section's icon tile (see .tile and .hue-* in shared.css).
export const SECTIONS = {
  dashboard: { label: 'Главная', short: 'Главная', path: '/', Icon: LayoutDashboard, hue: 'blue' },
  calendar: { label: 'Календарь', short: 'Календарь', path: '/calendar', Icon: CalendarDays, hue: 'orange', hint: 'Пары, собрания, дедлайны' },
  schedule: { label: 'Расписание', short: 'Расписание', path: '/schedule', Icon: CalendarSearch, hue: 'orange', hint: 'Группы, преподаватели, аудитории' },
  tasks: { label: 'Задачи', short: 'Задачи', path: '/tasks', Icon: SquareKanban, hue: 'teal', hint: 'Канбан и дедлайны' },
  associations: { label: 'Объединения', short: 'Объединения', path: '/associations', Icon: Handshake, hue: 'olive', hint: 'Клубы, медиа, волонтёры' },
  events: { label: 'Мероприятия', short: 'События', path: '/events', Icon: PartyPopper, hue: 'red', hint: 'Запись и ПГАС' },
  tribes: { label: 'Трайбы', short: 'Трайбы', path: '/tribes', Icon: Swords, hue: 'violet', hint: 'Турнир команд' },
  shop: { label: 'Магазин', short: 'Магазин', path: '/shop', Icon: ShoppingBag, hue: 'green', hint: 'Мерч за биты' },
  booking: { label: 'Бронь 108', short: 'Бронь', path: '/booking', Icon: DoorOpen, hue: 'cyan', hint: 'Коворкинг и ноутбуки' },
  forum: { label: 'Форум', short: 'Форум', path: '/forum', Icon: MessageSquare, hue: 'violet', hint: 'Спросить сокурсников' },
  map: { label: 'Карта кампуса', short: 'Карта', path: '/map', Icon: Map, hue: 'green', hint: 'Найти аудиторию' },
  teachers: { label: 'Преподаватели', short: 'Преподаватели', path: '/teachers', Icon: Users, hue: 'pink', hint: 'Кабинеты и почта' },
  faq: { label: 'Вопросы и ответы', short: 'FAQ', path: '/faq', Icon: HelpCircle, hue: 'amber', hint: 'Частые вопросы' },
  profile: { label: 'Личный кабинет', short: 'Профиль', path: '/profile', Icon: UserSquare, hue: 'cyan' },
  admin: { label: 'Панель управления', short: 'Админка', path: '/admin', Icon: Shield, hue: 'slate' },
  privacy: { label: 'Конфиденциальность', short: 'Cookie', path: '/privacy', Icon: Lock, hue: 'slate' },
};

export const NAV_ORDER = ['dashboard', 'calendar', 'schedule', 'tasks', 'associations', 'events', 'tribes', 'shop', 'booking', 'forum', 'map', 'teachers', 'faq', 'profile'];

// Mobile bottom bar: the sections students open most; the rest stay in the menu.
// Guests have no calendar of their own, so they get the public timetable in its place.
export const TAB_BAR_ORDER = ['dashboard', 'calendar', 'tasks', 'associations', 'profile'];
export const tabBarOrder = (isLoggedIn) => (isLoggedIn ? TAB_BAR_ORDER : TAB_BAR_ORDER.map(id => (id === 'calendar' ? 'schedule' : id)));
