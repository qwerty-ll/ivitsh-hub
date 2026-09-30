import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Plus, LogIn, Loader2, Clock, User, Handshake, Laptop, XCircle } from 'lucide-react';
import SectionIcon from '../components/SectionIcon';
import Modal from '../components/Modal';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { associationsApi, bookingApi } from '../services/api';
import { addDays, dayKey, dayTitle, layoutDay, minutesOf, parseDay, timeLabel } from '../utils/calendar';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const PX_PER_MIN = 0.8;
const ZONE_LABEL = { top: 'Верх', bottom: 'Низ', whole: 'Всё помещение' };
const toMin = (hm) => { const [h, m] = hm.split(':').map(Number); return h * 60 + m; };
const hm = (min) => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;

const title = (b) => (b.resource === 'room' ? ZONE_LABEL[b.zone] : `${b.laptops} ${b.laptops === 1 ? 'ноутбук' : b.laptops < 5 ? 'ноутбука' : 'ноутбуков'}`);

/** The most laptops taken at any moment of [from, to) — the same rule as on the server */
const laptopsTaken = (items, from, to) => {
  const list = items.filter(b => b.resource === 'laptops' && new Date(b.starts_at) < to && new Date(b.ends_at) > from);
  const moments = [from, ...list.map(b => new Date(b.starts_at)).filter(d => d >= from && d < to)];
  return Math.max(0, ...moments.map(m => list.filter(b => new Date(b.starts_at) <= m && m < new Date(b.ends_at)).reduce((n, b) => n + b.laptops, 0)));
};

const BookingForm = ({ open, preset, day, dayData, onClose, onSaved }) => {
  const { isAdmin } = useAuth();
  const [form, setForm] = useState(null);
  const [associations, setAssociations] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setError('');
    setForm({ resource: 'room', zone: 'whole', laptops: 1, date: day, start: '16:00', end: '18:00', association: '', purpose: '', ...preset });
    const load = isAdmin
      ? associationsApi.list().then(rows => (rows || []).map(a => ({ id: a.id, name: a.name })))
      : associationsApi.mine().then(rows => (rows || []).filter(r => r.role === 'leader' && r.status === 'approved')
        .map(r => ({ id: r.association_id, name: r.association_name })));
    load.then((list) => {
      setAssociations(list);
      if (!isAdmin && list.length) setForm(f => ({ ...f, association: f.association || String(list[0].id) }));
    }).catch(() => setAssociations([]));
  }, [open, preset, day, isAdmin]);

  if (!form) return null;
  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));
  const total = dayData?.laptops_total || 5;
  const from = new Date(`${form.date}T${form.start}`);
  const to = new Date(`${form.date}T${form.end}`);
  // A hint for the chosen day only: the server has the final word
  const free = form.resource === 'laptops' && form.date === day && dayData && to > from
    ? total - laptopsTaken(dayData.items, from, to) : null;

  const submit = async (e) => {
    e.preventDefault();
    if (!(to > from)) { setError('Конец брони должен быть позже начала'); return; }
    if (!isAdmin && !form.association) { setError('Выберите объединение'); return; }
    setSaving(true);
    setError('');
    try {
      const saved = await bookingApi.create({
        resource: form.resource,
        zone: form.resource === 'room' ? form.zone : null,
        laptops: form.resource === 'laptops' ? Number(form.laptops) : null,
        starts_at: from.toISOString(),
        ends_at: to.toISOString(),
        purpose: form.purpose.trim(),
        association_id: form.association ? Number(form.association) : null,
      });
      onSaved(saved);
    } catch (err) {
      setError(err.message || 'Не удалось забронировать');
    } finally {
      setSaving(false);
    }
  };

  const seg = (field, value, label) => (
    <button type="button" className={`segmented-item ${form[field] === value ? 'active' : ''}`} aria-pressed={form[field] === value}
      onClick={() => setForm(f => ({ ...f, [field]: value }))}>{label}</button>
  );

  return (
    <Modal open={open} onClose={onClose} title="Забронировать" titleId="booking-form-title" className="task-form-modal">
      <form className="task-form" onSubmit={submit} noValidate>
        <div className="segmented" role="group" aria-label="Что бронируем">
          {seg('resource', 'room', 'Коворкинг Б-108')}
          {seg('resource', 'laptops', 'Ноутбуки')}
        </div>
        {form.resource === 'room' ? (
          <fieldset className="field">
            <legend className="field-label">Часть помещения</legend>
            <div className="segmented" role="group" aria-label="Часть помещения">
              {seg('zone', 'top', 'Верх')}{seg('zone', 'bottom', 'Низ')}{seg('zone', 'whole', 'Всё помещение')}
            </div>
          </fieldset>
        ) : (
          <div className="field">
            <label className="field-label" htmlFor="booking-laptops">Сколько ноутбуков</label>
            <input id="booking-laptops" className="input" type="number" min={1} max={total} value={form.laptops} onChange={set('laptops')} />
            {free !== null && <p className={`task-optional ${free < Number(form.laptops) ? 'field-error' : ''}`}>В это время свободно: {Math.max(free, 0)} из {total}</p>}
          </div>
        )}
        <div className="meeting-when">
          <div className="field">
            <label className="field-label" htmlFor="booking-date">Дата</label>
            <input id="booking-date" className="input" type="date" value={form.date} onChange={set('date')} />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="booking-start">С</label>
            <input id="booking-start" className="input" type="time" step={300} min={dayData?.open} max={dayData?.close} value={form.start} onChange={set('start')} />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="booking-end">До</label>
            <input id="booking-end" className="input" type="time" step={300} min={dayData?.open} max={dayData?.close} value={form.end} onChange={set('end')} />
          </div>
        </div>
        {(isAdmin || associations.length > 1) && (
          <div className="field">
            <label className="field-label" htmlFor="booking-association">Для кого</label>
            <select id="booking-association" className="select" value={form.association} onChange={set('association')}>
              {isAdmin && <option value="">Администрация ИВИТШ</option>}
              {associations.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
        )}
        <div className="field">
          <label className="field-label" htmlFor="booking-purpose">Зачем <span className="task-optional">(необязательно)</span></label>
          <input id="booking-purpose" className="input" maxLength={300} value={form.purpose} onChange={set('purpose')} placeholder="Репетиция, съёмка, собрание…" />
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="cm-form-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Отменить</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving && <Loader2 size={16} className="spin-icon" {...ICON} />}Забронировать
          </button>
        </div>
      </form>
    </Modal>
  );
};

const BookingDialog = ({ booking, onClose, onCancelled }) => {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const cancel = async () => {
    let reason = '';
    if (isAdmin && !booking.mine) {
      reason = window.prompt('Причина отмены (её увидит тот, кто бронировал):', '');
      if (reason === null) return;
    } else if (!window.confirm('Отменить бронь?')) return;
    try {
      await bookingApi.cancel(booking.id, reason);
      toast.show('Бронь отменена', 'success');
      onCancelled();
    } catch (e) {
      toast.show(e.message || 'Не удалось отменить', 'error');
    }
  };
  return (
    <Modal open={!!booking} onClose={onClose} title={booking ? (booking.resource === 'room' ? `Б-108: ${ZONE_LABEL[booking.zone].toLowerCase()}` : title(booking)) : ''}
      titleId="booking-dialog-title" className="cal-dialog">
      {booking && (
        <div className="cal-dialog-body">
          <ul className="cal-facts">
            <li><Clock size={16} {...ICON} />{dayTitle(dayKey(new Date(booking.starts_at)), { weekday: 'long' })}, {timeLabel(booking.starts_at)}–{timeLabel(booking.ends_at)}</li>
            <li><Handshake size={16} {...ICON} />{booking.association ? booking.association.name : 'Администрация ИВИТШ'}</li>
            {booking.booked_by && <li><User size={16} {...ICON} />{booking.booked_by}</li>}
          </ul>
          {booking.purpose && <p className="cal-text">{booking.purpose}</p>}
          {booking.can_cancel && (
            <div className="cal-dialog-actions">
              <button type="button" className="btn btn-ghost btn-sm cal-danger" onClick={cancel}><XCircle size={16} {...ICON} />Отменить бронь</button>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};

const LANES = [
  { id: 'top', label: 'Верх' },
  { id: 'bottom', label: 'Низ' },
  { id: 'laptops', label: 'Ноутбуки' },
];

/** The day as a grid: the two parts of the room (a whole-room booking spans both) and the laptops */
const DayGrid = ({ data, onOpen, onPick, canBook }) => {
  const open = toMin(data.open);
  const close = toMin(data.close);
  const hours = [];
  for (let m = Math.ceil(open / 60) * 60; m < close; m += 60) hours.push(m);
  const top = (iso) => (Math.max(open, Math.min(close, minutesOf(iso))) - open) * PX_PER_MIN;
  const laptops = layoutDay(data.items.filter(b => b.resource === 'laptops'));
  const now = new Date();

  const pick = (lane) => (e) => {
    if (!canBook || e.target !== e.currentTarget) return;
    const y = e.nativeEvent.offsetY;
    const start = Math.min(close - 60, Math.max(open, open + Math.round(y / PX_PER_MIN / 30) * 30));
    onPick(lane === 'laptops'
      ? { resource: 'laptops', start: hm(start), end: hm(Math.min(close, start + 90)) }
      : { resource: 'room', zone: lane, start: hm(start), end: hm(Math.min(close, start + 90)) });
  };

  const block = (b, style) => (
    <button key={b.id} type="button" className={`booking-block ${b.resource === 'room' && b.zone === 'whole' ? 'is-whole' : ''} ${new Date(b.ends_at) < now ? 'is-past' : ''}`}
      style={style} onClick={() => onOpen(b)}>
      <span className="cal-block-time tabular">{timeLabel(b.starts_at)}–{timeLabel(b.ends_at)}</span>
      <span className="cal-block-title">{b.resource === 'laptops' ? (b.narrow ? `${b.laptops} шт.` : title(b)) : (b.association?.name || 'Администрация')}</span>
      <span className="cal-block-meta">{b.resource === 'laptops' ? (b.association?.name || 'Администрация') : (b.zone === 'whole' ? 'Всё помещение' : b.purpose)}</span>
    </button>
  );

  return (
    <div className="booking-grid">
      <div className="booking-head">
        <span />
        {LANES.map(l => <span key={l.id} className="booking-lane-title">{l.id === 'laptops' ? <><Laptop size={16} {...ICON} />{l.label}</> : l.label}</span>)}
      </div>
      <div className="booking-body" style={{ height: (close - open) * PX_PER_MIN }}>
        <div className="cal-gutter">
          {hours.map(m => <span key={m} className="cal-hour tabular" style={{ top: (m - open) * PX_PER_MIN }}>{`${m / 60}:00`}</span>)}
        </div>
        {LANES.map(l => (
          <div key={l.id} className={`booking-lane ${canBook ? 'is-pickable' : ''}`} onClick={pick(l.id)}
            title={canBook ? 'Нажмите на свободное время, чтобы забронировать' : undefined}>
            {hours.map(m => <span key={m} className="cal-hour-line" style={{ top: (m - open) * PX_PER_MIN }} />)}
            {l.id !== 'laptops' && data.items.filter(b => b.resource === 'room' && b.zone === l.id).map(b => block(b, {
              top: top(b.starts_at), height: Math.max(22, top(b.ends_at) - top(b.starts_at) - 2), left: 2, right: 2,
            }))}
            {l.id === 'laptops' && laptops.map(({ item: b, col, cols }) => block({ ...b, narrow: cols > 1 }, {
              top: top(b.starts_at), height: Math.max(22, top(b.ends_at) - top(b.starts_at) - 2),
              left: `calc(${(col / cols) * 100}% + 2px)`, width: `calc(${100 / cols}% - 4px)`,
            }))}
          </div>
        ))}
        {/* Whole-room bookings over both parts */}
        <div className="booking-whole-layer">
          {data.items.filter(b => b.resource === 'room' && b.zone === 'whole').map(b => block(b, {
            top: top(b.starts_at), height: Math.max(22, top(b.ends_at) - top(b.starts_at) - 2), left: 2, right: 2,
          }))}
        </div>
      </div>
    </div>
  );
};

const Booking = () => {
  const { isLoggedIn } = useAuth();
  const toast = useToast();
  const [params] = useSearchParams();
  const [day, setDay] = useState(() => (/^\d{4}-\d{2}-\d{2}$/.test(params.get('day') || '') ? params.get('day') : dayKey(new Date())));
  const [data, setData] = useState(null);
  const [mine, setMine] = useState([]);
  const [preset, setPreset] = useState(null);
  const [opened, setOpened] = useState(null);

  const load = useCallback(() => {
    if (!isLoggedIn) return;
    bookingApi.day(day).then(setData).catch(() => setData({ items: [], open: '08:00', close: '21:00', laptops_total: 5, can_book: false }));
    bookingApi.mine().then(r => setMine(r || [])).catch(() => setMine([]));
  }, [isLoggedIn, day]);
  useEffect(load, [load]);

  const upcomingMine = useMemo(() => mine.filter(b => b.cancelled_at || new Date(b.ends_at) > new Date()), [mine]);

  const header = (
    <header className="page-header tasks-header">
      <div className="page-heading">
        <SectionIcon section="booking" size="lg" />
        <div>
          <h1>Бронь 108 и ноутбуков</h1>
          <p className="page-subtitle">Коворкинг «8 бит»: верх, низ или всё помещение, и {data?.laptops_total || 5} ноутбуков. Бронь подтверждается сразу.</p>
        </div>
      </div>
      {data?.can_book && <button type="button" className="btn btn-primary" onClick={() => setPreset({})}><Plus size={16} {...ICON} />Забронировать</button>}
    </header>
  );

  if (!isLoggedIn) {
    return (
      <div className="container">
        {header}
        <div className="empty-state">
          <p>Расписание коворкинга видно после входа. Бронируют руководители объединений.</p>
          <Link to="/profile" className="btn btn-primary"><LogIn size={16} {...ICON} />Войти через ЭИОС</Link>
        </div>
      </div>
    );
  }

  const shift = (n) => { setData(null); setDay(dayKey(addDays(parseDay(day), n))); };

  return (
    <div className="container booking-page">
      {header}
      {data && !data.can_book && (
        <p className="cal-note">Бронировать могут руководители объединений и администрация. Здесь видно, когда помещение и ноутбуки заняты.</p>
      )}
      <div className="cal-toolbar">
        <div className="cal-nav">
          <button type="button" className="btn btn-secondary btn-icon" onClick={() => shift(-1)} aria-label="Предыдущий день"><ChevronLeft size={18} {...ICON} /></button>
          <button type="button" className="btn btn-secondary" onClick={() => { setData(null); setDay(dayKey(new Date())); }} disabled={day === dayKey(new Date())}>Сегодня</button>
          <button type="button" className="btn btn-secondary btn-icon" onClick={() => shift(1)} aria-label="Следующий день"><ChevronRight size={18} {...ICON} /></button>
          <h2 className="cal-range" aria-live="polite">{dayTitle(day, { weekday: 'long' })}</h2>
        </div>
        <label className="visually-hidden" htmlFor="booking-day">Дата</label>
        <input id="booking-day" className="input booking-day-input" type="date" value={day} onChange={e => { if (e.target.value) { setData(null); setDay(e.target.value); } }} />
      </div>

      {data === null ? <span className="skeleton cal-skeleton" /> : (
        <DayGrid data={data} canBook={data.can_book} onOpen={setOpened} onPick={p => setPreset(p)} />
      )}

      {upcomingMine.length > 0 && (
        <section className="card cal-side-card booking-mine" aria-labelledby="mine-title">
          <div className="dash-card-head"><h2 id="mine-title">Мои брони</h2></div>
          <ul className="list dash-rows">
            {upcomingMine.map(b => (
              <li key={b.id}>
                <button type="button" className="dash-row-btn booking-mine-row" onClick={() => (b.cancelled_at ? null : setOpened(b))} disabled={!!b.cancelled_at}>
                  <span className="dash-task-text">
                    <span className="dash-task-title">{b.resource === 'room' ? `Б-108: ${ZONE_LABEL[b.zone].toLowerCase()}` : title(b)}</span>
                    <span className="dash-task-meta tabular">
                      {dayTitle(dayKey(new Date(b.starts_at)))}, {timeLabel(b.starts_at)}–{timeLabel(b.ends_at)}
                      {b.association ? ` · ${b.association.name}` : ''}
                    </span>
                    {b.cancelled_at && (
                      <span className="booking-cancelled">
                        Отменена{b.cancelled_by && b.cancelled_by !== b.booked_by ? ` администрацией (${b.cancelled_by})` : ''}{b.cancel_reason ? `: ${b.cancel_reason}` : ''}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <BookingForm open={!!preset} preset={preset} day={day} dayData={data} onClose={() => setPreset(null)}
        onSaved={(b) => { setPreset(null); toast.show('Забронировано', 'success'); const d = dayKey(new Date(b.starts_at)); if (d !== day) setDay(d); else load(); }} />
      <BookingDialog booking={opened} onClose={() => setOpened(null)} onCancelled={() => { setOpened(null); load(); }} />
    </div>
  );
};

export default Booking;
