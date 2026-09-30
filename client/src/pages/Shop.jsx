import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ShoppingBag, Coins, Gift, Sparkles, LogIn, Loader2, Pencil, Plus, Trash2, PackageCheck, Search } from 'lucide-react';
import SectionIcon from '../components/SectionIcon';
import Modal from '../components/Modal';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { adminApi, shopApi } from '../services/api';
import { bits } from '../components/Progress';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const KIND = { merch: { label: 'Мерч', hue: 'green', Icon: ShoppingBag }, privilege: { label: 'Привилегия', hue: 'violet', Icon: Sparkles } };
const STATUS_TONE = { new: 'badge-accent', ready: 'badge-warning', issued: 'badge-success', cancelled: '' };
const when = (iso) => (iso ? new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }) : '');

const ItemPicture = ({ item }) => {
  const kind = KIND[item.kind] || KIND.merch;
  return item.image
    ? <img className="shop-pic" src={shopApi.imageSrc(item.image)} alt="" loading="lazy" />
    : <span className={`shop-pic shop-pic-empty hue-${kind.hue}`} aria-hidden="true"><kind.Icon size={40} {...ICON} /></span>;
};

const ItemCard = ({ item, available, onBuy }) => {
  const kind = KIND[item.kind] || KIND.merch;
  const soldOut = item.stock !== null && item.stock <= 0;
  const short = item.price - available;
  const reason = soldOut ? 'Нет в наличии' : item.limit_reached ? 'Лимит на человека' : short > 0 ? `Не хватает ${short}` : null;
  return (
    <li className={`card shop-card hue-${kind.hue}`}>
      <ItemPicture item={item} />
      <div className="shop-card-body">
        <p className="shop-card-top">
          <span className="badge shop-kind">{kind.label}</span>
          {item.stock !== null && !soldOut && <span className="task-optional">осталось {item.stock}</span>}
        </p>
        <h3 className="shop-card-title">{item.title}</h3>
        {item.description && <p className="shop-card-desc">{item.description}</p>}
        <div className="shop-card-foot">
          <span className="shop-price tabular"><Coins size={18} {...ICON} />{item.price}</span>
          <button type="button" className="btn btn-primary btn-sm" disabled={!!reason} onClick={() => onBuy(item)} title={reason || undefined}>
            {reason || 'Обменять'}
          </button>
        </div>
      </div>
    </li>
  );
};

const ItemForm = ({ item, open, onClose, onSaved }) => {
  const toast = useToast();
  const fileRef = useRef(null);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!open) return;
    setForm(item
      ? { ...item, stock: item.stock ?? '', per_user_limit: item.per_user_limit ?? '' }
      : { title: '', description: '', kind: 'merch', price: 50, stock: '', per_user_limit: '', is_active: true, sort: 0 });
  }, [open, item]);
  if (!form) return null;
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const data = {
        title: form.title, description: form.description, kind: form.kind, price: Number(form.price),
        stock: form.stock === '' ? null : Number(form.stock), per_user_limit: form.per_user_limit === '' ? null : Number(form.per_user_limit),
        is_active: form.is_active, sort: Number(form.sort) || 0,
      };
      let saved = item ? await shopApi.editItem(item.id, data) : await shopApi.createItem(data);
      const file = fileRef.current?.files?.[0];
      if (file) saved = await shopApi.uploadImage(saved.id, file);
      onSaved(saved);
    } catch (err) {
      toast.show(err.message || 'Не удалось сохранить', 'error');
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal open={open} onClose={onClose} title={item ? 'Товар' : 'Новый товар'} titleId="item-form-title" className="task-form-modal">
      <form className="task-form" onSubmit={submit}>
        <div className="segmented" role="group" aria-label="Что это">
          {Object.entries(KIND).map(([k, v]) => (
            <button key={k} type="button" className={`segmented-item ${form.kind === k ? 'active' : ''}`} aria-pressed={form.kind === k} onClick={() => setForm({ ...form, kind: k })}>{v.label}</button>
          ))}
        </div>
        <div className="field"><label className="field-label" htmlFor="i-title">Название</label>
          <input id="i-title" className="input" maxLength={120} required value={form.title} onChange={set('title')} placeholder="Худи ИВИТШ" /></div>
        <div className="field"><label className="field-label" htmlFor="i-desc">Описание</label>
          <textarea id="i-desc" className="textarea" rows={3} maxLength={2000} value={form.description} onChange={set('description')} placeholder="Размеры, цвет, как забрать" /></div>
        <div className="meeting-when">
          <div className="field"><label className="field-label" htmlFor="i-price">Цена, бит</label>
            <input id="i-price" className="input" type="number" min={1} value={form.price} onChange={set('price')} /></div>
          <div className="field"><label className="field-label" htmlFor="i-stock">Сколько есть</label>
            <input id="i-stock" className="input" type="number" min={0} value={form.stock} onChange={set('stock')} placeholder="∞" /></div>
          <div className="field"><label className="field-label" htmlFor="i-limit">В одни руки</label>
            <input id="i-limit" className="input" type="number" min={1} value={form.per_user_limit} onChange={set('per_user_limit')} placeholder="∞" /></div>
        </div>
        <div className="field"><label className="field-label" htmlFor="i-image">Фото <span className="task-optional">(PNG, JPG, WebP)</span></label>
          <input id="i-image" ref={fileRef} className="input" type="file" accept=".png,.jpg,.jpeg,.webp" /></div>
        <label className="task-person"><input type="checkbox" checked={form.is_active} onChange={set('is_active')} /><span>Показывать в магазине</span></label>
        <div className="cm-form-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Отменить</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving && <Loader2 size={16} className="spin-icon" {...ICON} />}Сохранить</button>
        </div>
      </form>
    </Modal>
  );
};

/** Administration: goods, the queue of orders to hand out, and bits by hand */
const ShopAdmin = ({ onChanged }) => {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('open');
  const [editing, setEditing] = useState(null);
  const [grant, setGrant] = useState({ q: '', found: [], user: null, amount: 50, reason: '' });

  const load = useCallback(() => shopApi.admin(status).then(setData).catch(() => setData({ items: [], orders: [] })), [status]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (grant.user || grant.q.trim().length < 2) return undefined;
    const t = setTimeout(() => adminApi.searchUsers(grant.q.trim()).then(r => setGrant(g => ({ ...g, found: r || [] }))).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [grant.q, grant.user]);

  const setOrder = async (o, next) => {
    let comment = '';
    if (next === 'cancelled') {
      comment = window.prompt('Причина отмены (увидит студент, биты вернутся):', '');
      if (comment === null) return;
    } else if (next === 'ready') {
      comment = window.prompt('Где и когда забрать?', 'В дирекции ИВИТШ, Б-209, в будни 10–17') || '';
    }
    try {
      await shopApi.setOrder(o.id, next, comment);
      load();
    } catch (e) {
      toast.show(e.message || 'Не получилось', 'error');
    }
  };
  const remove = async (item) => {
    if (!window.confirm(`Убрать «${item.title}»?`)) return;
    const r = await shopApi.removeItem(item.id);
    toast.show(r.hidden ? 'Товар скрыт: его уже покупали' : 'Товар удалён', 'success');
    load(); onChanged();
  };
  const giveBits = async (e) => {
    e.preventDefault();
    if (!grant.user || !grant.reason.trim()) return;
    try {
      const r = await shopApi.grant(grant.user.id, Number(grant.amount), grant.reason.trim());
      toast.show(`Готово. У ${grant.user.full_name} теперь ${bits(r.balance.available)}`, 'success');
      setGrant({ q: '', found: [], user: null, amount: 50, reason: '' });
    } catch (err) {
      toast.show(err.message || 'Не получилось', 'error');
    }
  };

  if (!data) return <span className="skeleton cal-skeleton" />;
  return (
    <div className="shop-admin">
      <section className="card">
        <div className="assoc-manage-head">
          <h2 className="cal-subhead">Заказы</h2>
          <select className="select shop-admin-filter" value={status} onChange={e => setStatus(e.target.value)} aria-label="Какие заказы">
            <option value="open">Ждут выдачи</option><option value="all">Все</option><option value="issued">Выданы</option><option value="cancelled">Отменены</option>
          </select>
        </div>
        {data.orders.length === 0 ? <p className="cal-empty">Заказов нет.</p> : (
          <ul className="list shop-orders">
            {data.orders.map(o => (
              <li key={o.id} className="shop-order">
                <span className="shop-order-main">
                  <strong>{o.item_title}</strong> · <span className="tabular">{o.price}</span> бит
                  <span className="task-optional"> — {o.user.full_name}{o.user.group_number ? `, ${o.user.group_number}` : ''} · {when(o.created_at)}</span>
                  {o.comment && <span className="task-optional shop-order-comment">{o.comment}</span>}
                </span>
                <span className={`badge ${STATUS_TONE[o.status]}`}>{o.status_text}</span>
                {['new', 'ready'].includes(o.status) && (
                  <span className="shop-order-actions">
                    {o.status === 'new' && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOrder(o, 'ready')}>Готов к выдаче</button>}
                    <button type="button" className="btn btn-primary btn-sm" onClick={() => setOrder(o, 'issued')}><PackageCheck size={16} {...ICON} />Выдан</button>
                    <button type="button" className="btn btn-ghost btn-sm cal-danger" onClick={() => setOrder(o, 'cancelled')}>Отменить</button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <div className="assoc-manage-head">
          <h2 className="cal-subhead">Товары</h2>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing({})}><Plus size={16} {...ICON} />Добавить</button>
        </div>
        <ul className="list shop-orders">
          {data.items.map(i => (
            <li key={i.id} className="shop-order">
              <span className="shop-order-main">
                <strong>{i.title}</strong>{!i.is_active && <span className="badge">скрыт</span>}
                <span className="task-optional"> — {i.price} бит · {i.stock === null ? 'без лимита' : `осталось ${i.stock}`} · продано {i.sold}</span>
              </span>
              <span className="shop-order-actions">
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing(i)}><Pencil size={16} {...ICON} />Изменить</button>
                <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => remove(i)} aria-label={`Убрать ${i.title}`}><Trash2 size={16} {...ICON} /></button>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2 className="cal-subhead">Начислить биты</h2>
        <p className="task-optional">За конкурс вне портала или в поправку. Можно и снять — отрицательным числом.</p>
        <form className="shop-grant" onSubmit={giveBits}>
          {grant.user ? (
            <p className="shop-grant-user"><strong>{grant.user.full_name}</strong> {grant.user.group_number}
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setGrant(g => ({ ...g, user: null }))}>Другой</button></p>
          ) : (
            <div className="shop-grant-search">
              <Search size={16} {...ICON} />
              <input className="input" placeholder="Фамилия, логин или группа" value={grant.q} onChange={e => setGrant({ ...grant, q: e.target.value })} aria-label="Кому" />
              {grant.found.length > 0 && (
                <ul className="cal-add-menu shop-grant-found">
                  {grant.found.slice(0, 8).map(u => (
                    <li key={u.id}><button type="button" onClick={() => setGrant(g => ({ ...g, user: u, found: [] }))}>{u.full_name} <span className="task-optional">{u.group_number}</span></button></li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <input className="input" type="number" value={grant.amount} onChange={e => setGrant({ ...grant, amount: e.target.value })} aria-label="Сколько бит" />
          <input className="input" maxLength={200} placeholder="За что" value={grant.reason} onChange={e => setGrant({ ...grant, reason: e.target.value })} aria-label="За что" />
          <button type="submit" className="btn btn-primary" disabled={!grant.user || !grant.reason.trim()}>Начислить</button>
        </form>
      </section>

      <ItemForm open={!!editing} item={editing?.id ? editing : null} onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); toast.show('Сохранено', 'success'); load(); onChanged(); }} />
    </div>
  );
};

const Shop = () => {
  const { isLoggedIn, isAdmin } = useAuth();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('shop');
  const [buying, setBuying] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (isLoggedIn) shopApi.get().then(setData).catch(() => setData({ items: [], orders: [], grants: [], balance: { available: 0, earned: 0, granted: 0, spent: 0 } }));
  }, [isLoggedIn]);
  useEffect(load, [load]);

  const buy = async () => {
    setBusy(true);
    try {
      await shopApi.buy(buying.id);
      toast.show(`Заказ оформлен: «${buying.title}». Когда будет готов — статус появится в «Мои заказы».`, 'success', 5000);
      setBuying(null);
      setTab('orders');
      load();
    } catch (e) {
      toast.show(e.message || 'Не получилось', 'error');
    } finally {
      setBusy(false);
    }
  };
  const cancel = async (o) => {
    if (!window.confirm(`Отменить заказ «${o.item_title}»? Биты вернутся.`)) return;
    try { await shopApi.cancel(o.id); load(); } catch (e) { toast.show(e.message || 'Не получилось', 'error'); }
  };

  const header = (
    <header className="page-header">
      <div className="page-heading">
        <SectionIcon section="shop" size="lg" />
        <div>
          <h1>Магазин ИВИТШ</h1>
          <p className="page-subtitle">Биты за активность на портале меняются на мерч и привилегии. Заказ выдают лично в дирекции.</p>
        </div>
      </div>
    </header>
  );
  if (!isLoggedIn) {
    return (
      <div className="container">{header}
        <div className="empty-state"><p>Магазин открыт после входа.</p><Link to="/profile" className="btn btn-primary"><LogIn size={16} {...ICON} />Войти через ЭИОС</Link></div>
      </div>
    );
  }
  if (!data) return <div className="container">{header}<span className="skeleton cal-skeleton" /></div>;
  const b = data.balance;
  const merch = data.items.filter(i => i.kind === 'merch');
  const privileges = data.items.filter(i => i.kind === 'privilege');

  return (
    <div className="container shop-page">
      {header}
      <section className="shop-wallet" aria-label="Мои биты">
        <span className="shop-wallet-icon" aria-hidden="true"><Coins size={28} {...ICON} /></span>
        <div className="shop-wallet-text">
          <p className="shop-wallet-amount tabular">{bits(b.available)}</p>
          <p className="shop-wallet-meta tabular">заработано {b.earned}{b.granted ? ` · призы и начисления ${b.granted > 0 ? '+' : ''}${b.granted}` : ''}{b.spent ? ` · потрачено ${b.spent}` : ''}</p>
        </div>
        <Link to="/profile#achievements" className="btn btn-secondary btn-sm">Как заработать</Link>
      </section>

      <div className="segmented shop-tabs" role="group" aria-label="Раздел магазина">
        {[['shop', 'Витрина'], ['orders', `Мои заказы${data.orders.filter(o => ['new', 'ready'].includes(o.status)).length ? ` · ${data.orders.filter(o => ['new', 'ready'].includes(o.status)).length}` : ''}`], ...(isAdmin ? [['admin', 'Управление']] : [])].map(([k, l]) => (
          <button key={k} type="button" className={`segmented-item ${tab === k ? 'active' : ''}`} aria-pressed={tab === k} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      {tab === 'shop' && (data.items.length === 0 ? (
        <div className="empty-state"><Gift size={32} {...ICON} /><p>Витрина пока пустая — скоро здесь появится мерч ИВИТШ.</p></div>
      ) : (
        <>
          {merch.length > 0 && (<><h2 className="shop-section-title">Мерч</h2><ul className="shop-grid">{merch.map(i => <ItemCard key={i.id} item={i} available={b.available} onBuy={setBuying} />)}</ul></>)}
          {privileges.length > 0 && (<><h2 className="shop-section-title">Привилегии</h2><ul className="shop-grid">{privileges.map(i => <ItemCard key={i.id} item={i} available={b.available} onBuy={setBuying} />)}</ul></>)}
        </>
      ))}

      {tab === 'orders' && (
        <div className="shop-mine">
          {data.orders.length === 0 ? <p className="cal-empty">Заказов пока нет.</p> : (
            <ul className="list shop-orders card">
              {data.orders.map(o => (
                <li key={o.id} className="shop-order">
                  <span className="shop-order-main">
                    <strong>{o.item_title}</strong> · <span className="tabular">{o.price}</span> бит <span className="task-optional">· {when(o.created_at)}</span>
                    {o.comment && <span className="task-optional shop-order-comment">{o.comment}</span>}
                  </span>
                  <span className={`badge ${STATUS_TONE[o.status]}`}>{o.status_text}</span>
                  {o.status === 'new' && <button type="button" className="btn btn-ghost btn-sm cal-danger" onClick={() => cancel(o)}>Отменить</button>}
                </li>
              ))}
            </ul>
          )}
          {data.grants.length > 0 && (
            <section className="card shop-grants">
              <h2 className="cal-subhead">Призы и начисления</h2>
              <ul className="list">
                {data.grants.map((g, i) => (
                  <li key={i} className="shop-order"><span className="shop-order-main">{g.reason} <span className="task-optional">· {when(g.created_at)}</span></span>
                    <span className={`tabular shop-grant-amount ${g.amount < 0 ? 'is-minus' : ''}`}>{g.amount > 0 ? '+' : ''}{g.amount}</span></li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {tab === 'admin' && isAdmin && <ShopAdmin onChanged={load} />}

      <Modal open={!!buying} onClose={() => setBuying(null)} title="Обменять биты" titleId="buy-title" className="cal-dialog">
        {buying && (
          <div className="cal-dialog-body">
            <div className="shop-buy">
              <ItemPicture item={buying} />
              <div>
                <p className="shop-card-title">{buying.title}</p>
                <p className="shop-price tabular"><Coins size={18} {...ICON} />{buying.price}</p>
                <p className="task-optional">После обмена останется {bits(b.available - buying.price)}.</p>
              </div>
            </div>
            <p className="task-optional">Заказ соберут и напишут в «Мои заказы», где и когда забрать. Пока заказ не начали собирать, его можно отменить — биты вернутся.</p>
            <div className="cal-dialog-actions">
              <button type="button" className="btn btn-primary" onClick={buy} disabled={busy}>{busy && <Loader2 size={16} className="spin-icon" {...ICON} />}Обменять</button>
              <button type="button" className="btn btn-ghost" onClick={() => setBuying(null)}>Отмена</button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Shop;
