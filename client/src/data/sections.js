import {
  LayoutDashboard, CalendarDays, Handshake, MessageSquare, Map, Users, HelpCircle, UserSquare, Shield, Lock
} from 'lucide-react';

// One place for every section's name, route, icon and wayfinding hue.
// The hue only colors the section's icon tile (see .tile and .hue-* in shared.css).
export const SECTIONS = {
  dashboard: { label: 'Главная', short: 'Главная', path: '/', Icon: LayoutDashboard, hue: 'blue' },
  schedule: { label: 'Расписание', short: 'Расписание', path: '/schedule', Icon: CalendarDays, hue: 'orange', hint: 'Группы, преподаватели, аудитории' },
  associations: { label: 'Объединения', short: 'Объединения', path: '/associations', Icon: Handshake, hue: 'olive', hint: 'Клубы, медиа, волонтёры' },
  forum: { label: 'Форум', short: 'Форум', path: '/forum', Icon: MessageSquare, hue: 'violet', hint: 'Спросить сокурсников' },
  map: { label: 'Карта кампуса', short: 'Карта', path: '/map', Icon: Map, hue: 'green', hint: 'Найти аудиторию' },
  teachers: { label: 'Преподаватели', short: 'Преподаватели', path: '/teachers', Icon: Users, hue: 'pink', hint: 'Кабинеты и почта' },
  faq: { label: 'Вопросы и ответы', short: 'FAQ', path: '/faq', Icon: HelpCircle, hue: 'amber', hint: 'Частые вопросы' },
  profile: { label: 'Личный кабинет', short: 'Профиль', path: '/profile', Icon: UserSquare, hue: 'cyan' },
  admin: { label: 'Панель управления', short: 'Админка', path: '/admin', Icon: Shield, hue: 'slate' },
  privacy: { label: 'Конфиденциальность', short: 'Cookie', path: '/privacy', Icon: Lock, hue: 'slate' },
};

export const NAV_ORDER = ['dashboard', 'schedule', 'associations', 'forum', 'map', 'teachers', 'faq', 'profile'];

// Mobile bottom bar: the sections students open most; the rest stay in the menu.
export const TAB_BAR_ORDER = ['dashboard', 'schedule', 'forum', 'map', 'profile'];
