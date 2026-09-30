import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, SearchX, Users, ChevronRight, LogIn, RotateCw } from 'lucide-react';
import SectionIcon from '../components/SectionIcon';
import { useAuth } from '../context/AuthContext';
import { associationsApi } from '../services/api';
import { STATUS_BADGE, monogram, plural, shortName } from '../utils/associations';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };

const Associations = () => {
  const { isLoggedIn } = useAuth();
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [onlyMine, setOnlyMine] = useState(false);

  const load = () => {
    setError('');
    associationsApi.list()
      .then(res => setItems(Array.isArray(res) ? res : []))
      .catch(e => { setError(e.message || 'Не удалось загрузить объединения'); setItems([]); });
  };
  useEffect(load, [isLoggedIn]);

  const mineCount = (items || []).filter(a => a.my_status === 'approved' || a.my_status === 'pending').length;
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items || []).filter(a =>
      (!onlyMine || a.my_status === 'approved' || a.my_status === 'pending')
      && (!q || a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q)
        || a.leaders.some(l => l.full_name.toLowerCase().includes(q))));
  }, [items, query, onlyMine]);

  return (
    <div className="container assoc-page">
      <header className="page-header">
        <div className="page-heading">
          <SectionIcon section="associations" size="lg" />
          <div>
            <h1>Объединения</h1>
            <p className="page-subtitle">Студенческие объединения ИВИТШ: клубы, медиа, волонтёры, спорт. Выберите своё и подайте заявку.</p>
          </div>
        </div>
      </header>

      {!isLoggedIn && (
        <div className="assoc-banner">
          <p>Чтобы вступить в объединение и видеть контакты руководителей, войдите через ЭИОС.</p>
          <Link to="/profile" className="btn btn-primary btn-sm"><LogIn size={16} {...ICON} />Войти</Link>
        </div>
      )}

      <div className="assoc-toolbar">
        <div className="cm-search">
          <label htmlFor="assoc-search" className="visually-hidden">Поиск объединения</label>
          <Search size={18} {...ICON} className="cm-search-icon" />
          <input
            id="assoc-search"
            type="search"
            className="input"
            placeholder="Название, руководитель или тема"
            value={query}
            onChange={e => setQuery(e.target.value)}
            autoComplete="off"
          />
        </div>
        {isLoggedIn && mineCount > 0 && (
          <div className="segmented" role="group" aria-label="Какие объединения показать">
            <button type="button" className={`segmented-item ${!onlyMine ? 'active' : ''}`} aria-pressed={!onlyMine} onClick={() => setOnlyMine(false)}>Все</button>
            <button type="button" className={`segmented-item ${onlyMine ? 'active' : ''}`} aria-pressed={onlyMine} onClick={() => setOnlyMine(true)}>
              Мои <span className="tabular">{mineCount}</span>
            </button>
          </div>
        )}
      </div>

      {items === null ? (
        <ul className="assoc-grid" aria-busy="true" aria-label="Загрузка объединений">
          {[0, 1, 2, 3, 4, 5].map(i => <li key={i} className="assoc-card assoc-card-skeleton"><span className="skeleton" /></li>)}
        </ul>
      ) : error ? (
        <div className="empty-state" role="alert">
          <h2 className="cm-empty-title">Не удалось загрузить объединения</h2>
          <p>{error}</p>
          <button type="button" className="btn btn-secondary" onClick={load}><RotateCw size={16} {...ICON} />Повторить</button>
        </div>
      ) : shown.length === 0 ? (
        <div className="empty-state">
          <SearchX size={32} {...ICON} />
          <h2 className="cm-empty-title">{items.length ? 'Ничего не нашли' : 'Объединений пока нет'}</h2>
          {query && <button type="button" className="btn btn-secondary" onClick={() => setQuery('')}>Сбросить поиск</button>}
        </div>
      ) : (
        <ul className="assoc-grid">
          {shown.map(a => {
            const badge = STATUS_BADGE(a.my_role, a.my_status);
            return (
              <li key={a.id}>
                <Link to={`/associations/${a.id}`} className="assoc-card">
                  <span className="assoc-mono" aria-hidden="true">{monogram(a.name)}</span>
                  <span className="assoc-card-main">
                    <span className="assoc-card-name">{a.name}</span>
                    <span className="assoc-card-meta">
                      {a.leaders.length
                        ? `Руководитель: ${a.leaders.map(l => shortName(l.full_name)).join(', ')}`
                        : a.listed_leader ? `Руководитель: ${a.listed_leader}` : 'Руководитель скоро появится'}
                    </span>
                    <span className="assoc-card-foot">
                      <span className="assoc-count tabular">
                        <Users size={14} {...ICON} />
                        {a.member_count} {plural(a.member_count, ['участник', 'участника', 'участников'])}
                      </span>
                      {badge && <span className={`badge ${badge.tone}`}>{badge.label}</span>}
                    </span>
                  </span>
                  <ChevronRight size={18} {...ICON} className="assoc-chevron" />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export default Associations;
