import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Search, MapPin, User, AlertCircle, ChevronDown, GraduationCap, Check,
  ChevronLeft, ChevronRight, CalendarX2, CloudOff, RotateCw, Undo2, ArrowRight
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { scheduleApi } from '../services/api';
import { subgroupOf, cleanLessonTitle } from '../utils/lessons';

const EIOS_DIRECT_URL = 'https://eios.kosgos.ru/api';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

// Automatically calculate academic year from date string (YYYY-MM-DD)
const calculateAcademicYear = (dateStr) => {
  if (!dateStr) return '2025-2026';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '2025-2026';
  const year = d.getFullYear();
  const month = d.getMonth() + 1; // 1 to 12
  if (month >= 9) {
    return `${year}-${year + 1}`;
  } else {
    return `${year - 1}-${year}`;
  }
};

// Clean discipline titles (remove leading 'лек ', 'лаб ', 'пр ' and the subgroup, shown on its own)
const cleanDisciplineTitle = (rawTitle) => cleanLessonTitle(rawTitle || '');

// Helper for lesson type badge (label + badge tone)
const getLessonTypeBadge = (disciplineName) => {
  const lower = (disciplineName || '').toLowerCase();
  if (lower.startsWith('лек') || lower.includes(' лек ')) return { label: 'Лекция', tone: '' };
  if (lower.startsWith('лаб') || lower.includes(' лаб ')) return { label: 'Лабораторная', tone: '' };
  if (lower.startsWith('пр') || lower.includes(' пр ')) return { label: 'Практика', tone: '' };
  if (lower.includes('экз') || lower.includes('зач')) return { label: 'Аттестация', tone: 'badge-warning' };
  return { label: 'Занятие', tone: '' };
};

// Presentation helpers (local calendar date / time, used only for "today" and "now" markers)
const pad2 = (n) => String(n).padStart(2, '0');
const capitalize = (str) => (str ? str.charAt(0).toUpperCase() + str.slice(1) : '');
const localIso = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const toMinutes = (hm = '') => {
  const [h, m] = hm.split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
};
const formatDuration = (mins) => (mins < 60
  ? `${mins} мин`
  : `${Math.floor(mins / 60)} ч${mins % 60 ? ` ${mins % 60} мин` : ''}`);
const mondayIsoOf = (iso) => {
  const d = new Date(iso);
  const day = d.getDay();
  d.setDate(d.getDate() + (day === 0 ? -6 : 1 - day));
  return d.toISOString().split('T')[0];
};

const TARGET_TYPES = [
  { id: 'group', label: 'Группы', field: 'Группа', placeholder: 'Найти группу, например 24-ИСбо-1' },
  { id: 'teacher', label: 'Преподаватели', field: 'Преподаватель', placeholder: 'Найти преподавателя по ФИО' },
  { id: 'aud', label: 'Аудитории', field: 'Аудитория', placeholder: 'Найти аудиторию, например Б-304' },
];

// Shown to guests until they pick a group
const GUEST_GROUP_NAME = '24-ИСбо-1';
const GROUP_KEY = 'portal_sched_group';

const sameName = (a, b) => !!a && !!b && a.trim().toLowerCase() === b.trim().toLowerCase();
const findGroupByName = (items, name) => (name ? items.find(g => sameName(g.name, name)) : null);

// Only a group chosen in the list is remembered ({ picked: true }); an automatic choice is not,
// so a student's own group takes over from it.
const readSavedGroup = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(GROUP_KEY));
    return saved && saved.name ? saved : null;
  } catch { return null; }
};
const readPickedGroup = () => {
  const saved = readSavedGroup();
  return saved?.picked ? saved : null;
};

// Whose timetable was shown last (a teacher keeps seeing their own); only kept once something was chosen
const TYPE_KEY = 'portal_sched_type';
const TYPE_TARGET_KEYS = { teacher: 'portal_sched_teacher', aud: 'portal_sched_aud' };
const readJson = (key) => {
  try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch { return null; }
};
const readSavedType = () => {
  let type = null;
  try { type = localStorage.getItem(TYPE_KEY); } catch { /* storage unavailable */ }
  if (type === 'group') return 'group';
  return TYPE_TARGET_KEYS[type] && readJson(TYPE_TARGET_KEYS[type])?.id ? type : null;
};
const saveType = (type) => {
  try { localStorage.setItem(TYPE_KEY, type); } catch { /* storage unavailable */ }
};

// onGroupLessons({ group, lessons }) receives the loaded lessons whenever a group's schedule is shown,
// so the dashboard can summarise today without fetching the schedule twice.
// ownGroup ({ id, name }) is the signed-in student's group from EIOS; id may be missing for a group typed by hand.
// compact: the dashboard's "today" card — no pickers, only the nearest study day of the student's group
// (or of the teacher / room a guest chose last), with a link to the full schedule page.
// titleHidden: the page around it already has the heading.
const ScheduleWidget = ({ onGroupLessons, ownGroup = null, compact = false, titleHidden = false }) => {
  const [searchParams] = useSearchParams();
  const [targetType, setTargetType] = useState(() => {
    const fromUrl = compact ? null : searchParams.get('type');
    if (TARGET_TYPES.some(t => t.id === fromUrl)) return fromUrl;
    if (compact && ownGroup?.name) return 'group';
    return readSavedType() || 'group';
  }); // 'group' | 'teacher' | 'aud'
  // A guest who has not chosen anyone yet gets a choice instead of some random group's pairs
  const needsChoice = compact && !ownGroup?.name && !readPickedGroup()
    && !['teacher', 'aud'].includes(readSavedType());
  const availableYears = ['2025-2026', '2024-2025', '2023-2024', '2026-2027'];

  // Separate target selection states per category
  const [selectedGroup, setSelectedGroup] = useState(() => (
    readPickedGroup() || (ownGroup?.name ? { id: ownGroup.id || null, name: ownGroup.name } : readSavedGroup())
  ));
  const ownGroupRef = useRef(ownGroup);
  ownGroupRef.current = ownGroup;

  const [selectedTeacher, setSelectedTeacher] = useState(() => {
    try {
      const saved = localStorage.getItem('portal_sched_teacher');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });

  const [selectedAud, setSelectedAud] = useState(() => {
    try {
      const saved = localStorage.getItem('portal_sched_aud');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });

  // Current active target object depending on active tab
  const currentTarget = useMemo(() => {
    if (targetType === 'teacher') return selectedTeacher;
    if (targetType === 'aud') return selectedAud;
    return selectedGroup;
  }, [targetType, selectedGroup, selectedTeacher, selectedAud]);

  // Input & Dropdown state
  const [searchQuery, setSearchQuery] = useState('');
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);
  // Keyboard highlight inside the combobox list (presentation only)
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  // View Mode: 'day' (1 день) | 'week' (1 неделя)
  const [viewMode, setViewMode] = useState('day');

  // Clock for the past / now / upcoming highlighting: it moves on without a page reload
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(timer);
  }, []);

  // Selected date ISO string (default to today)
  const [selectedDate, setSelectedDate] = useState(() => localIso(new Date()));

  // Academic Year State (Auto-synced with selectedDate, can also be manually selected)
  const [selectedYear, setSelectedYear] = useState(() => calculateAcademicYear(localIso(new Date())));

  // Auto-sync year when user picks a new date
  const handleDateChange = (newDateIso) => {
    setSelectedDate(newDateIso);
    if (newDateIso) {
      const autoYear = calculateAcademicYear(newDateIso);
      setSelectedYear(autoYear);
    }
  };

  // Switch category tabs and clear search input
  const handleSwitchTargetType = (newType) => {
    setTargetType(newType);
    saveType(newType);
    setSearchQuery('');
    setIsDropdownOpen(false);
  };

  // Catalog items & Lessons state
  const [catalogItems, setCatalogItems] = useState([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [rawLessons, setRawLessons] = useState([]);
  // Which target the loaded lessons belong to (the tab can change before the next fetch finishes)
  const [lessonsOwner, setLessonsOwner] = useState(null);
  const [lessonsLoading, setLessonsLoading] = useState(false);
  const [error, setError] = useState(null);
  // Set when the backend served the last saved copy because EIOS is unreachable.
  const [staleSince, setStaleSince] = useState(null);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // 1. Fetch Catalog Items for selected type & year
  useEffect(() => {
    let isMounted = true;
    const loadCatalog = async () => {
      setCatalogLoading(true);
      try {
        let rawItems = [];
        if (targetType === 'group') {
          const res = await scheduleApi.getGroups(selectedYear);
          rawItems = res?.data || [];
        } else if (targetType === 'teacher') {
          const res = await scheduleApi.getTeachers(selectedYear);
          rawItems = res?.data || [];
        } else if (targetType === 'aud') {
          const res = await scheduleApi.getAuditories(selectedYear);
          rawItems = res?.data || [];
        }

        const items = (rawItems || []).map(i => ({
          ...i,
          id: i.id || i.idName,
          idName: i.idName || i.id
        }));

        if (isMounted) {
          setCatalogItems(items);
          setCatalogLoading(false);

          if (items.length > 0) {
            const activeId = currentTarget?.id;
            const exists = activeId ? items.find(i => Number(i.id) === Number(activeId)) : null;
            if (!exists) {
              const own = ownGroupRef.current;
              const defaultItem = targetType === 'group'
                // Group ids change every academic year, names do not: keep the same group, else the student's own
                ? (findGroupByName(items, currentTarget?.name)
                  || (own?.id && items.find(g => Number(g.id) === Number(own.id)))
                  || findGroupByName(items, own?.name)
                  || findGroupByName(items, GUEST_GROUP_NAME)
                  || items.find(g => g.facul === 'ИВИТШ') || items[0])
                : (items.find(a => a.name && (a.name.includes('Б-') || a.name.includes('Б2'))) || items[0]);
              if (defaultItem) handleSelectItem(defaultItem, { auto: true });
            }
          }
        }
      } catch (err) {
        console.warn('[ScheduleWidget] Catalog load error:', err);
        if (isMounted) {
          setCatalogLoading(false);
          setError(err.message || 'Не удалось загрузить список из ЭИОС.');
        }
      }
    };

    if (!needsChoice) loadCatalog();
    return () => { isMounted = false; };
  }, [targetType, selectedYear]);

  // Handle selecting an item from search dropdown
  const handleSelectItem = (item, { auto = false } = {}) => {
    const itemId = item.id || item.idName;
    const targetObj = { id: itemId, name: item.name };
    if (!auto) saveType(targetType);

    if (targetType === 'group') {
      setSelectedGroup(targetObj);
      if (!auto) {
        // Choosing one's own group again means "follow my group", not a fixed pick
        const picked = !sameName(item.name, ownGroupRef.current?.name);
        try {
          if (picked) localStorage.setItem(GROUP_KEY, JSON.stringify({ ...targetObj, picked }));
          else localStorage.removeItem(GROUP_KEY);
        } catch { /* storage unavailable */ }
      }
    } else if (targetType === 'teacher') {
      setSelectedTeacher(targetObj);
      localStorage.setItem('portal_sched_teacher', JSON.stringify(targetObj));
    } else if (targetType === 'aud') {
      setSelectedAud(targetObj);
      localStorage.setItem('portal_sched_aud', JSON.stringify(targetObj));
    }

    setIsDropdownOpen(false);
    setSearchQuery('');
  };

  // The student's group with an id for the selected year, or null when it has no timetable
  // (a group typed by hand, or "Деканат" for staff)
  const ownGroupTarget = () => {
    if (!ownGroup?.name) return null;
    if (targetType === 'group' && catalogItems.length) {
      const listed = findGroupByName(catalogItems, ownGroup.name);
      return listed ? { id: listed.id, name: listed.name } : null;
    }
    return ownGroup.id ? { id: ownGroup.id, name: ownGroup.name } : null;
  };

  // Signing in (or the profile arriving later) switches to the student's group unless one was picked
  useEffect(() => {
    if (!ownGroup?.name || readPickedGroup()) return;
    const target = ownGroupTarget();
    if (target) setSelectedGroup(prev => (prev?.id && sameName(prev.name, target.name) ? prev : target));
  }, [ownGroup?.id, ownGroup?.name]);

  const showOwnGroup = () => {
    const target = ownGroupTarget();
    if (!target) return;
    try { localStorage.removeItem(GROUP_KEY); } catch { /* storage unavailable */ }
    setSelectedGroup(target);
  };
  const canReturnToOwnGroup = targetType === 'group' && !!selectedGroup?.name && !!ownGroup?.name
    && !sameName(selectedGroup.name, ownGroup.name) && !!ownGroupTarget();

  // Filter catalog items by search query
  const filteredCatalog = useMemo(() => {
    if (!searchQuery.trim()) return catalogItems.slice(0, 30);
    const query = searchQuery.toLowerCase().trim();
    return catalogItems.filter(item =>
      (item.name && item.name.toLowerCase().includes(query)) ||
      (item.facul && item.facul.toLowerCase().includes(query)) ||
      (item.kaf && item.kaf.toLowerCase().includes(query))
    ).slice(0, 40);
  }, [catalogItems, searchQuery]);

  // Reset the keyboard highlight whenever the list changes or closes
  useEffect(() => { setActiveIndex(-1); }, [searchQuery, isDropdownOpen, targetType]);

  // Keep the highlighted option visible while moving with the keyboard
  useEffect(() => {
    if (activeIndex < 0 || !listRef.current) return;
    const el = listRef.current.children[activeIndex];
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  // 2. Fetch Lessons Schedule
  const fetchSchedule = async (id, name) => {
    if (!id) return;
    setLessonsLoading(true);
    setError(null);
    setStaleSince(null);
    setLessonsOwner(null);
    try {
      const res = await scheduleApi.getSchedule(
        targetType === 'group' ? id : null,
        selectedYear,
        '',
        targetType === 'teacher' ? id : null,
        targetType === 'aud' ? id : null
      );

      const raspData = res?.data?.rasp || (Array.isArray(res?.data) ? res.data : []);
      setRawLessons(raspData);
      setLessonsOwner({ type: targetType, name });
      setStaleSince(res?.stale && res.cached_at ? new Date(res.cached_at * 1000) : null);
    } catch (err) {
      console.error('[ScheduleWidget] Fetch schedule error:', err);
      setError(err.message || 'Не удалось загрузить расписание.');
      setRawLessons([]);
      if (targetType === 'group') onGroupLessons?.(null);
    } finally {
      setLessonsLoading(false);
    }
  };

  useEffect(() => {
    if (currentTarget?.id) {
      fetchSchedule(currentTarget.id, currentTarget.name);
    }
  }, [currentTarget, selectedYear, targetType]);

  // 3. Deduplicate raw EIOS API lessons
  const deduplicatedLessons = useMemo(() => {
    const seen = new Set();
    const result = [];
    (rawLessons || []).forEach(item => {
      const key = `${item.код || ''}_${item.дата}_${item.начало}_${item.конец}_${item.дисциплина}_${item.преподаватель}_${item.аудитория}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(item);
      }
    });
    return result;
  }, [rawLessons]);

  // Subgroups the group has anywhere in its timetable: a slot where only one of them has a pair
  // tells the others they are free
  const knownSubgroups = useMemo(() => {
    if (lessonsOwner?.type !== 'group') return [];
    const found = new Set(deduplicatedLessons.map(subgroupOf).filter(Boolean));
    return found.size <= 4 ? [...found].sort((a, b) => a - b) : [];
  }, [deduplicatedLessons, lessonsOwner]);

  useEffect(() => {
    if (onGroupLessons && lessonsOwner?.type === 'group') {
      onGroupLessons({ group: lessonsOwner.name, lessons: deduplicatedLessons });
    }
  }, [deduplicatedLessons, lessonsOwner]);

  // Get start & end dates for Monday to Saturday of the selectedDate's week
  const weekStartEndDates = useMemo(() => {
    const d = new Date(selectedDate);
    const day = d.getDay(); // 0 is Sun
    const diffToMon = day === 0 ? -6 : 1 - day;
    const mon = new Date(d);
    mon.setDate(d.getDate() + diffToMon);

    const sat = new Date(mon);
    sat.setDate(mon.getDate() + 5);

    const monIso = mon.toISOString().split('T')[0];
    const satIso = sat.toISOString().split('T')[0];

    return { monIso, satIso, monObj: mon, satObj: sat };
  }, [selectedDate]);

  // Compact card: today while pairs are still ahead, else the next day with pairs (within two weeks)
  const compactDate = useMemo(() => {
    if (!compact) return null;
    const today = localIso(now);
    const nowMinutes = now.getHours() * 60 + now.getMinutes();
    const dates = [...new Set(deduplicatedLessons
      .filter(l => l.дата && (l.дата.slice(0, 10) > today
        || (l.дата.startsWith(today) && toMinutes(l.конец) > nowMinutes)))
      .map(l => l.дата.slice(0, 10)))].sort();
    const limit = new Date(now);
    limit.setDate(limit.getDate() + 14);
    return dates[0] && dates[0] <= localIso(limit) ? dates[0] : null;
  }, [compact, deduplicatedLessons, now]);

  // Lessons filtered by view mode (Day or Week)
  const modeLessons = useMemo(() => {
    if (compact) return compactDate ? deduplicatedLessons.filter(l => l.дата && l.дата.startsWith(compactDate)) : [];
    if (viewMode === 'day') {
      return deduplicatedLessons.filter(l => l.дата && l.дата.startsWith(selectedDate));
    }
    // Week Mode: filter lessons between Monday and Saturday
    return deduplicatedLessons.filter(l => {
      if (!l.дата) return false;
      const d = l.дата.split('T')[0];
      return d >= weekStartEndDates.monIso && d <= weekStartEndDates.satIso;
    });
  }, [compact, compactDate, deduplicatedLessons, viewMode, selectedDate, weekStartEndDates]);

  // Group modeLessons FIRST BY DATE, THEN BY TIME SLOT (Prevents date mixing!)
  const groupedByDateAndSlot = useMemo(() => {
    const dateMap = {};

    modeLessons.forEach(lesson => {
      const dateKey = lesson.дата ? lesson.дата.split('T')[0] : 'неизвестно';
      if (!dateMap[dateKey]) {
        const dObj = new Date(dateKey);
        const weekday = lesson.день_недели || dObj.toLocaleDateString('ru-RU', { weekday: 'long' });
        const dateLabel = dObj.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
        const dayTitle = `${weekday} (${dateLabel})`;
        dateMap[dateKey] = {
          dateIso: dateKey,
          dayTitle: dayTitle,
          weekday,
          dateLabel,
          slotsMap: {}
        };
      }

      const timeKey = `${lesson.начало}-${lesson.конец}`;
      if (!dateMap[dateKey].slotsMap[timeKey]) {
        dateMap[dateKey].slotsMap[timeKey] = {
          timeStart: lesson.начало,
          timeEnd: lesson.конец,
          lessonNum: lesson.номерЗанятия,
          color: lesson.цвет || 'var(--accent)',
          items: []
        };
      }
      dateMap[dateKey].slotsMap[timeKey].items.push(lesson);
    });

    // Convert to sorted list of date groups
    return Object.values(dateMap).sort((a, b) => a.dateIso.localeCompare(b.dateIso)).map(dGroup => ({
      ...dGroup,
      slots: Object.values(dGroup.slotsMap).sort((a, b) => a.timeStart.localeCompare(b.timeStart))
    }));
  }, [modeLessons]);

  // Day navigation helper: +/- days
  const changeDateByDays = (daysDelta) => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + daysDelta);
    handleDateChange(d.toISOString().split('T')[0]);
  };

  // Week navigation helper: +/- weeks
  const changeDateByWeeks = (weeksDelta) => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + (weeksDelta * 7));
    handleDateChange(d.toISOString().split('T')[0]);
  };

  // ---------- Presentation-only derived values ----------
  const todayIso = localIso(new Date()); // same expression as the default date
  const localTodayIso = localIso(now);
  const nowMin = now.getHours() * 60 + now.getMinutes();
  const isOnToday = viewMode === 'day'
    ? selectedDate === todayIso
    : mondayIsoOf(todayIso) === weekStartEndDates.monIso;
  const targetMeta = TARGET_TYPES.find(t => t.id === targetType) || TARGET_TYPES[0];
  const listboxId = 'schedule-target-listbox';
  const optionId = (item) => `schedule-target-option-${item.id}`;

  // Where a lesson stands against the clock: 'past' (faded), 'now' (highlighted block) or 'upcoming' (accent)
  const slotState = (dGroup, slot) => {
    if (dGroup.dateIso < localTodayIso) return 'past';
    if (dGroup.dateIso > localTodayIso) return 'upcoming';
    if (toMinutes(slot.timeEnd) <= nowMin) return 'past';
    if (toMinutes(slot.timeStart) <= nowMin) return 'now';
    return 'upcoming';
  };
  // The first lesson of today that has not started yet
  const nextSlotIndex = (dGroup) => (dGroup.dateIso === localTodayIso
    ? dGroup.slots.findIndex(s => toMinutes(s.timeStart) > nowMin)
    : -1);

  const handleComboKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isDropdownOpen) { setIsDropdownOpen(true); return; }
      setActiveIndex(i => Math.min(i + 1, filteredCatalog.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      if (isDropdownOpen && activeIndex >= 0 && filteredCatalog[activeIndex]) {
        e.preventDefault();
        handleSelectItem(filteredCatalog[activeIndex]);
        requestAnimationFrame(() => inputRef.current?.select());
      }
    } else if (e.key === 'Escape') {
      if (isDropdownOpen) {
        e.preventDefault();
        setIsDropdownOpen(false);
        requestAnimationFrame(() => inputRef.current?.select());
      }
    } else if (e.key === 'Tab') {
      setIsDropdownOpen(false);
    }
  };

  // Pair number and the live badges belong to the time slot, not to one lesson
  const slotBadges = (slot, state, isNext) => (
    <>
      {slot.lessonNum ? <span className="sched-lesson-num tabular">{slot.lessonNum} пара</span> : null}
      {state === 'now' && (
        <>
          <span className="badge sched-now-badge">Идёт сейчас</span>
          <span className="sched-countdown tabular">ещё {formatDuration(toMinutes(slot.timeEnd) - nowMin)}</span>
        </>
      )}
      {isNext && (
        <span className="badge badge-accent tabular">Следующая · через {formatDuration(toMinutes(slot.timeStart) - nowMin)}</span>
      )}
    </>
  );

  // inSplit: the lesson sits in a subgroup column, which already names the subgroup and the slot badges are above
  /**
   * A slot where subgroups have different pairs shows them side by side, one column per subgroup
   * (stacked on narrow screens). A subgroup without a pair gets an empty column, so its students see
   * at a glance that they are free.
   */
  const renderSlotBody = (slot, state, isNext) => {
    if (!slot.items.some(item => subgroupOf(item) > 0)) return slot.items.map(renderLesson(slot, state, isNext));
    const numbers = [...new Set([
      ...slot.items.map(subgroupOf).filter(Boolean),
      ...(targetType === 'group' ? knownSubgroups : []),
    ])].sort((a, b) => a - b);
    const wholeGroup = slot.items.filter(item => subgroupOf(item) === 0);
    const hasBadges = slot.lessonNum || state === 'now' || isNext;
    return (
      <>
        {hasBadges && <p className="sched-lesson-tags">{slotBadges(slot, state, isNext)}</p>}
        {wholeGroup.map(renderLesson(slot, state, isNext, true))}
        <div className="sched-split">
          {numbers.map(n => {
            const items = slot.items.filter(item => subgroupOf(item) === n);
            return (
              <div key={n} className={`sched-split-col${items.length ? '' : ' is-free'}`}>
                <p className="sched-sub-label tabular">{n} подгруппа</p>
                {items.length
                  ? items.map(renderLesson(slot, state, isNext, true))
                  : <p className="sched-sub-free">Нет пары</p>}
              </div>
            );
          })}
        </div>
      </>
    );
  };

  const renderLesson = (slot, state, isNext, inSplit = false) => (item, iIdx) => {
    const typeBadge = getLessonTypeBadge(item.дисциплина);
    const cleanedTitle = cleanDisciplineTitle(item.дисциплина);
    const subgroup = subgroupOf(item);
    return (
      <div key={item.код || iIdx} className="sched-lesson">
        <p className="sched-lesson-tags">
          <span className={`badge ${typeBadge.tone}`}>{typeBadge.label}</span>
          {!inSplit && subgroup > 0 && <span className="badge">Подгруппа {subgroup}</span>}
          {item.замена && <span className="badge badge-warning">Замена</span>}
          {!inSplit && iIdx === 0 && slotBadges(slot, state, isNext)}
        </p>
        <h4 className="sched-lesson-title">{cleanedTitle}</h4>
        <p className="sched-lesson-meta">
          {item.аудитория && (/^Б-?\d{3}/i.test(item.аудитория) ? (
            // Rooms in building Б open the floor plan on the campus map
            <Link to={`/map?room=${encodeURIComponent(item.аудитория)}`} className="sched-lesson-room sched-room-link">
              <MapPin size={15} {...ICON} />
              <span className="visually-hidden">Аудитория </span>{item.аудитория}
              <span className="visually-hidden"> — показать на карте</span>
            </Link>
          ) : (
            <span className="sched-lesson-room">
              <MapPin size={15} {...ICON} />
              <span className="visually-hidden">Аудитория </span>{item.аудитория}
            </span>
          ))}
          {item.преподаватель && (
            <span>
              <User size={15} {...ICON} />
              <span className="visually-hidden">Преподаватель </span>{item.преподаватель}
            </span>
          )}
          {item.группа && targetType !== 'group' && (
            <span>
              <GraduationCap size={15} {...ICON} />
              <span className="visually-hidden">Группа </span>{item.группа}
            </span>
          )}
        </p>
      </div>
    );
  };

  if (needsChoice) {
    return (
      <div className="card sched sched--compact">
        <div className="sched-compact-head">
          <h2 id="schedule-title">Расписание</h2>
        </div>
        <p className="sched-choice-lead">Покажу здесь ближайшие пары. Чьё расписание смотреть? Для этого вход не нужен.</p>
        <div className="sched-choice">
          <Link to="/schedule?type=group" className="btn btn-secondary">
            <GraduationCap size={16} {...ICON} />
            Выбрать группу
          </Link>
          <Link to="/schedule?type=teacher" className="btn btn-secondary">
            <User size={16} {...ICON} />
            Я преподаватель
          </Link>
        </div>
      </div>
    );
  }

  // Compact card title: the day it shows and whose pairs they are
  const compactTitle = (() => {
    if (!compactDate) return 'Ближайшие пары';
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    if (compactDate === localTodayIso) return 'Сегодня';
    if (compactDate === localIso(tomorrow)) return 'Завтра';
    return capitalize(new Date(`${compactDate}T00:00:00`).toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' }));
  })();
  const pastToday = compact && compactDate === localTodayIso
    ? groupedByDateAndSlot[0]?.slots.filter(slot => toMinutes(slot.timeEnd) <= nowMin).length || 0
    : 0;

  return (
    <div className={`card sched${compact ? ' sched--compact' : ''}`}>
      {compact && (
        <div className="sched-compact-head">
          <h2 id="schedule-title">
            {compactTitle}
            {currentTarget?.name && <span className="sched-compact-who">{currentTarget.name}</span>}
          </h2>
          <Link to="/schedule" className="sched-compact-all">
            Всё расписание
            <ArrowRight size={16} {...ICON} />
          </Link>
        </div>
      )}

      {!compact && (<>
      {/* 1. TITLE & TYPE SWITCHER */}
      <div className="sched-head">
        <h2 id="schedule-title" className={titleHidden ? 'visually-hidden' : undefined}>Расписание</h2>
        <div className="segmented sched-types" role="group" aria-label="Чьё расписание показать">
          {TARGET_TYPES.map(t => (
            <button
              key={t.id}
              type="button"
              onClick={() => handleSwitchTargetType(t.id)}
              className={`segmented-item ${targetType === t.id ? 'active' : ''}`}
              aria-pressed={targetType === t.id}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* 2. SEARCH COMBOBOX & ACADEMIC YEAR SELECT */}
      <div className="sched-filters">
        <div className="field sched-combo" ref={dropdownRef}>
          <div className="sched-field-head">
            <label className="field-label" htmlFor="schedule-target-input">{targetMeta.field}</label>
            {canReturnToOwnGroup && (
              <button type="button" className="sched-own-group" onClick={showOwnGroup} aria-label={`Моя группа, ${ownGroup.name}`}>
                <Undo2 size={14} {...ICON} />
                Моя группа
              </button>
            )}
          </div>
          <div className="sched-combo-control">
            <Search size={16} className="sched-combo-icon" {...ICON} />
            <input
              ref={inputRef}
              id="schedule-target-input"
              type="text"
              role="combobox"
              aria-expanded={isDropdownOpen}
              aria-controls={listboxId}
              aria-autocomplete="list"
              aria-activedescendant={isDropdownOpen && activeIndex >= 0 && filteredCatalog[activeIndex] ? optionId(filteredCatalog[activeIndex]) : undefined}
              autoComplete="off"
              spellCheck={false}
              placeholder={isDropdownOpen && currentTarget?.name ? currentTarget.name : targetMeta.placeholder}
              value={isDropdownOpen ? searchQuery : (currentTarget?.name || searchQuery)}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setIsDropdownOpen(true);
              }}
              onFocus={() => setIsDropdownOpen(true)}
              onClick={() => setIsDropdownOpen(true)}
              onKeyDown={handleComboKeyDown}
              className="input sched-combo-input"
            />
            <ChevronDown size={16} className="sched-combo-chevron" {...ICON} />
          </div>

          {/* Results popover */}
          {isDropdownOpen && (
            <div className="sched-popover">
              {catalogLoading ? (
                <div className="sched-popover-loading" role="status">
                  <span className="visually-hidden">Загрузка списка…</span>
                  <span className="skeleton sched-skel-line" />
                  <span className="skeleton sched-skel-line sched-skel-line--mid" />
                  <span className="skeleton sched-skel-line sched-skel-line--short" />
                </div>
              ) : filteredCatalog.length > 0 ? (
                <ul className="sched-options" role="listbox" id={listboxId} ref={listRef} aria-label={targetMeta.label}>
                  {filteredCatalog.map((item, idx) => {
                    const isCurrent = Number(item.id) === Number(currentTarget?.id);
                    return (
                      <li
                        key={item.id}
                        id={optionId(item)}
                        role="option"
                        aria-selected={isCurrent}
                        className={`sched-option ${idx === activeIndex ? 'is-active' : ''}`}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => {
                          handleSelectItem(item);
                          inputRef.current?.blur();
                        }}
                      >
                        <span className="sched-option-text">
                          <span className="sched-option-name">{item.name}</span>
                          {item.facul && <span className="sched-option-meta">{item.facul}</span>}
                          {!item.facul && item.kaf && <span className="sched-option-meta">{item.kaf}</span>}
                        </span>
                        {isCurrent && <Check size={16} className="sched-option-check" {...ICON} />}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="sched-popover-empty">Ничего не найдено</p>
              )}
            </div>
          )}
        </div>

        <div className="field sched-year">
          <label className="field-label" htmlFor="schedule-year-select">Учебный год</label>
          <div className="sched-select-wrap">
            <select
              id="schedule-year-select"
              value={selectedYear}
              onChange={(e) => setSelectedYear(e.target.value)}
              className="select sched-select tabular"
            >
              {availableYears.map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <ChevronDown size={16} className="sched-select-chevron" {...ICON} />
          </div>
        </div>
      </div>

      {/* 3. MODE SWITCHER (ДЕНЬ / НЕДЕЛЯ) & DATE NAVIGATION */}
      <div className="sched-nav">
        <div className="segmented sched-modes" role="group" aria-label="Период">
          <button
            type="button"
            onClick={() => setViewMode('day')}
            className={`segmented-item ${viewMode === 'day' ? 'active' : ''}`}
            aria-pressed={viewMode === 'day'}
          >
            День
          </button>
          <button
            type="button"
            onClick={() => setViewMode('week')}
            className={`segmented-item ${viewMode === 'week' ? 'active' : ''}`}
            aria-pressed={viewMode === 'week'}
          >
            Неделя
          </button>
        </div>

        <div className="sched-nav-end">
          {!isOnToday && (
            <button type="button" className="btn btn-secondary sched-today" onClick={() => handleDateChange(todayIso)}>
              {viewMode === 'day' ? 'Сегодня' : 'Эта неделя'}
            </button>
          )}
          {viewMode === 'day' ? (
            <div className="sched-dates">
              <button
                type="button"
                onClick={() => changeDateByDays(-1)}
                className="btn btn-secondary btn-icon"
                aria-label="Предыдущий день"
              >
                <ChevronLeft size={18} {...ICON} />
              </button>
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => handleDateChange(e.target.value)}
                className="input sched-date-input tabular"
                aria-label="Дата"
              />
              <button
                type="button"
                onClick={() => changeDateByDays(1)}
                className="btn btn-secondary btn-icon"
                aria-label="Следующий день"
              >
                <ChevronRight size={18} {...ICON} />
              </button>
            </div>
          ) : (
            <div className="sched-dates">
              <button
                type="button"
                onClick={() => changeDateByWeeks(-1)}
                className="btn btn-secondary btn-icon"
                aria-label="Предыдущая неделя"
              >
                <ChevronLeft size={18} {...ICON} />
              </button>
              <span className="sched-week-range tabular" aria-live="polite">
                {new Date(weekStartEndDates.monIso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })} — {new Date(weekStartEndDates.satIso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
              </span>
              <button
                type="button"
                onClick={() => changeDateByWeeks(1)}
                className="btn btn-secondary btn-icon"
                aria-label="Следующая неделя"
              >
                <ChevronRight size={18} {...ICON} />
              </button>
            </div>
          )}
        </div>
      </div>
      </>)}

      {staleSince && !lessonsLoading && !error && (
        <p className="sched-notice" role="status">
          <CloudOff size={18} {...ICON} />
          <span>
            ЭИОС сейчас недоступна — показана сохранённая копия от{' '}
            <span className="tabular">{staleSince.toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}</span>.
          </span>
        </p>
      )}

      {/* 4. LESSONS */}
      {lessonsLoading ? (
        <div className="sched-body" aria-busy="true">
          <p className="visually-hidden" role="status">
            Загрузка расписания для «{currentTarget?.name || 'выбранного объекта'}»…
          </p>
          <span className="skeleton sched-skel-heading" />
          <ul className="sched-slots" aria-hidden="true">
            {[0, 1, 2].map(i => (
              <li key={i} className="sched-slot">
                <span className="sched-time">
                  <span className="skeleton sched-skel-time" />
                </span>
                <span className="sched-skel-body">
                  <span className="skeleton sched-skel-badge" />
                  <span className="skeleton sched-skel-line sched-skel-line--mid" />
                  <span className="skeleton sched-skel-line sched-skel-line--short" />
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : error ? (
        <div className="sched-alert" role="alert">
          <AlertCircle size={20} {...ICON} />
          <div className="sched-alert-text">
            <p className="sched-alert-title">{error}</p>
            <p>Проверьте подключение к интернету и загрузите расписание ещё раз.</p>
            {currentTarget?.id && (
              <button
                type="button"
                className="btn btn-secondary sched-alert-retry"
                onClick={() => fetchSchedule(currentTarget.id, currentTarget.name)}
              >
                <RotateCw size={16} {...ICON} />
                Загрузить снова
              </button>
            )}
          </div>
        </div>
      ) : groupedByDateAndSlot.length > 0 ? (
        <div className="sched-body">
          {groupedByDateAndSlot.map((dGroup) => (
            <section key={dGroup.dateIso} className="sched-day" aria-labelledby={`sched-day-${dGroup.dateIso}`}>
              {compact ? (
                pastToday > 0 && (
                  <p className="sched-compact-past tabular">
                    {pastToday === 1 ? 'Одна пара уже прошла' : `Уже прошло пар: ${pastToday}`}
                  </p>
                )
              ) : (
                <h3 className="sched-day-title" id={`sched-day-${dGroup.dateIso}`}>
                  <span>{capitalize(dGroup.weekday)}, {dGroup.dateLabel}</span>
                  {dGroup.dateIso === localTodayIso && <span className="badge badge-accent">Сегодня</span>}
                </h3>
              )}

              <ul className="sched-slots">
                {dGroup.slots.map((slot, sIdx) => {
                  const state = slotState(dGroup, slot);
                  if (compact && state === 'past') return null;
                  const isNext = sIdx === nextSlotIndex(dGroup);
                  const start = toMinutes(slot.timeStart);
                  const length = Math.max(1, toMinutes(slot.timeEnd) - start);
                  return (
                    <li key={sIdx} className={`sched-slot is-${state}`}>
                      <p className="sched-time tabular">
                        {state === 'past' && <span className="visually-hidden">Пара прошла. </span>}
                        <span className="sched-time-start">{slot.timeStart}</span>
                        <span className="sched-time-end">
                          <span className="visually-hidden">до </span>{slot.timeEnd}
                        </span>
                      </p>
                      <div className="sched-slot-body">
                        {renderSlotBody(slot, state, isNext)}
                      </div>
                      {state === 'now' && (
                        <span className="sched-now-progress" aria-hidden="true">
                          <span style={{ transform: `scaleX(${Math.min(1, (nowMin - start) / length)})` }} />
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <div className="sched-empty">
          <CalendarX2 size={28} {...ICON} />
          <h3>{compact ? 'Ближайших пар нет' : 'Занятий нет'}</h3>
          <p>{compact ? 'В ближайшие две недели пары не запланированы.' : 'На выбранный день или неделю пары не запланированы.'}</p>
          {!compact && viewMode === 'day' && (
            <button type="button" className="btn btn-secondary" onClick={() => setViewMode('week')}>
              Показать всю неделю
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default ScheduleWidget;
