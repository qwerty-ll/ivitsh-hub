import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Award, Clock, Loader2, ChevronRight } from 'lucide-react';
import SectionIcon from './SectionIcon';
import { useToast } from '../context/ToastContext';
import { associationsApi, authApi } from '../services/api';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const EMPTY = { tg_username: '', vk_url: '', max_contact: '' };

/** The student's associations: achievements for the approved ones, pending applications below. */
export const ProfileAssociations = () => {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    associationsApi.mine().then(res => setRows(Array.isArray(res) ? res : [])).catch(() => setRows([]));
  }, []);
  if (rows === null) return null;

  const achievements = rows.filter(r => r.status === 'approved');
  const pending = rows.filter(r => r.status === 'pending');

  return (
    <section aria-labelledby="profile-assoc-title">
      <div className="section-header">
        <h2 id="profile-assoc-title">Объединения и достижения</h2>
      </div>
      <ul className="card list profile-assoc">
        {achievements.map(r => (
          <li key={r.association_id}>
            <Link to={`/associations/${r.association_id}`} className="list-row profile-assoc-row">
              <span className="tile tile-quiet" aria-hidden="true"><Award size={20} {...ICON} /></span>
              <span className="profile-stat-text">
                <span className="profile-stat-label">
                  {r.role === 'leader' ? 'Руководитель объединения' : 'Участник объединения'} «{r.association_name}»
                </span>
              </span>
              <ChevronRight size={18} {...ICON} className="profile-assoc-chevron" />
            </Link>
          </li>
        ))}
        {pending.map(r => (
          <li key={r.association_id}>
            <Link to={`/associations/${r.association_id}`} className="list-row profile-assoc-row">
              <span className="tile tile-quiet" aria-hidden="true"><Clock size={20} {...ICON} /></span>
              <span className="profile-stat-text">
                <span className="profile-stat-label">{r.association_name}</span>
                <span className="profile-stat-meta">Заявка на рассмотрении у руководителя</span>
              </span>
              <ChevronRight size={18} {...ICON} className="profile-assoc-chevron" />
            </Link>
          </li>
        ))}
        {achievements.length + pending.length === 0 ? (
          <li className="list-row profile-assoc-row">
            <SectionIcon section="associations" quiet />
            <span className="profile-stat-text">
              <span className="profile-stat-label">Вы пока не состоите в объединениях</span>
              <span className="profile-stat-meta">
                <Link to="/associations">Выбрать объединение</Link> — участие появится здесь как достижение.
              </span>
            </span>
          </li>
        ) : null}
      </ul>
    </section>
  );
};

/** Telegram / VK / Max the student shares with leaders of their associations. */
export const ProfileContacts = () => {
  const toast = useToast();
  const [saved, setSaved] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    authApi.getMe().then(me => {
      const values = { tg_username: me.tg_username || '', vk_url: me.vk_url || '', max_contact: me.max_contact || '' };
      setSaved(values);
      setForm(values);
    }).catch(() => setSaved(EMPTY));
  }, []);

  const changed = saved && Object.keys(EMPTY).some(k => form[k].trim() !== saved[k]);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const me = await authApi.updateProfile({
        tg_username: form.tg_username.trim(),
        vk_url: form.vk_url.trim(),
        max_contact: form.max_contact.trim(),
      });
      // The server returns the normalised values (a link becomes a bare name)
      const values = { tg_username: me.tg_username || '', vk_url: me.vk_url || '', max_contact: me.max_contact || '' };
      setSaved(values);
      setForm(values);
      toast.show('Контакты сохранены', 'success');
    } catch (err) {
      setError(err.message || 'Не удалось сохранить');
    } finally {
      setSaving(false);
    }
  };

  const field = (key, id, label, placeholder) => (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      <input id={id} className="input" value={form[key]} placeholder={placeholder} autoComplete="off" spellCheck={false}
        maxLength={key === 'max_contact' ? 64 : 100}
        onChange={e => setForm({ ...form, [key]: e.target.value })} disabled={saved === null} />
    </div>
  );

  return (
    <section aria-labelledby="profile-contacts-title">
      <div className="section-header">
        <h2 id="profile-contacts-title">Контакты для связи</h2>
      </div>
      <form className="card profile-contacts" onSubmit={save}>
        <p className="profile-contacts-lead">
          Их видят руководители ваших объединений, чтобы написать вам. Если вы руководитель — ещё и студенты в каталоге объединений.
          Все поля необязательные.
        </p>
        <div className="profile-contacts-grid">
          {field('tg_username', 'contact-tg', 'Telegram', '@username')}
          {field('vk_url', 'contact-vk', 'ВКонтакте', 'vk.com/id…')}
          {field('max_contact', 'contact-max', 'Max', 'Ссылка или ник')}
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div>
          <button type="submit" className="btn btn-primary" disabled={!changed || saving}>
            {saving && <Loader2 size={16} className="spin-icon" {...ICON} />}Сохранить контакты
          </button>
        </div>
      </form>
    </section>
  );
};
