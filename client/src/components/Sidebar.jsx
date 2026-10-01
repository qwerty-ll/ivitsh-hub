import React from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { PanelLeftClose, PanelLeftOpen, LogIn, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { SECTIONS, NAV_GROUPS } from '../data/sections';

const ICON = { size: 20, strokeWidth: 1.75, 'aria-hidden': true };

const ROLE_LABEL = { admin: 'Администратор', moderator: 'Модератор' };

const Sidebar = ({ isCollapsed, setIsCollapsed, isMobileOpen, setIsMobileOpen }) => {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { user, isLoggedIn, isAdmin } = useAuth();

  const all = isAdmin ? [...NAV_GROUPS, { title: 'Управление', items: ['admin'] }] : NAV_GROUPS;
  // Guests see only what works without signing in
  const groups = isLoggedIn ? all : all
    .map(group => ({ ...group, items: group.items.filter(id => !SECTIONS[id].auth) }))
    .filter(group => group.items.length > 0);

  const goTo = (path) => {
    navigate(path);
    setIsMobileOpen(false);
  };

  return (
    <aside
      id="app-sidebar"
      className={`sidebar ${isCollapsed ? 'collapsed' : ''} ${isMobileOpen ? 'mobile-open' : ''}`}
      aria-label="Основная навигация"
    >
      <NavLink to="/" className="sidebar-brand" onClick={() => setIsMobileOpen(false)}>
        <span className="sidebar-brand-mark">
          <img src="/img/mascot-160.png" alt="" />
        </span>
        <span className="sidebar-brand-text">
          <span className="sidebar-brand-name">ИВИТШ Хаб</span>
          <span className="sidebar-brand-sub">КГУ · Высшая IT-школа</span>
        </span>
      </NavLink>

      <nav className="sidebar-nav">
        {groups.map(({ title, items }) => (
          <div key={title || 'main'} className="sidebar-group" role="group" aria-label={title || undefined}>
            {title && <p className="sidebar-group-title" aria-hidden="true">{title}</p>}
            <ul>
              {items.map((id) => {
                const { label, path, Icon, hue } = SECTIONS[id];
                return (
                  <li key={id}>
                    <NavLink
                      to={path}
                      end={path === '/'}
                      className={({ isActive }) => `sidebar-link hue-${hue} ${isActive ? 'active' : ''}`}
                      title={isCollapsed ? label : undefined}
                      onClick={() => setIsMobileOpen(false)}
                    >
                      <Icon {...ICON} />
                      <span className="sidebar-link-label">{label}</span>
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        {isLoggedIn ? (
          <button
            className={`sidebar-user hue-cyan ${pathname === '/profile' ? 'active' : ''}`}
            onClick={() => goTo('/profile')}
            title={isCollapsed ? user.fullName : 'Личный кабинет'}
            aria-current={pathname === '/profile' ? 'page' : undefined}
          >
            <span className="sidebar-user-avatar">
              {user.photoUrl ? (
                <img src={user.photoUrl} alt="" onError={(e) => { e.target.style.display = 'none'; }} />
              ) : (
                <User size={18} strokeWidth={1.75} aria-hidden="true" />
              )}
            </span>
            <span className="sidebar-user-info">
              <span className="sidebar-user-name">{user.fullName}</span>
              <span className="sidebar-user-role">{ROLE_LABEL[user.role] || 'Студент'}</span>
            </span>
          </button>
        ) : pathname !== '/profile' && (
          // Hidden on the login page itself, where the form is the only way in.
          <button className="btn sidebar-login" onClick={() => goTo('/profile')} title={isCollapsed ? 'Войти через ЭИОС' : undefined}>
            <LogIn size={18} strokeWidth={1.75} aria-hidden="true" />
            <span className="sidebar-link-label">Войти через ЭИОС</span>
          </button>
        )}

        <button
          className="sidebar-collapse"
          onClick={() => setIsCollapsed(!isCollapsed)}
          aria-label={isCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
          title={isCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
        >
          {isCollapsed ? <PanelLeftOpen {...ICON} /> : <PanelLeftClose {...ICON} />}
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
