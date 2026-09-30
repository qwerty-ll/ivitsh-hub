import React from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { PanelLeftClose, PanelLeftOpen, LogIn, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { SECTIONS, NAV_ORDER } from '../data/sections';

const ICON = { size: 20, strokeWidth: 1.75, 'aria-hidden': true };

const ROLE_LABEL = { admin: 'Администратор', moderator: 'Модератор', curator: 'Куратор' };

const Sidebar = ({ isCollapsed, setIsCollapsed, isMobileOpen, setIsMobileOpen }) => {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { user, isLoggedIn, isAdmin } = useAuth();

  const items = isAdmin ? [...NAV_ORDER, 'admin'] : NAV_ORDER;

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
      </nav>

      <div className="sidebar-footer">
        {isLoggedIn ? (
          <button className="sidebar-user" onClick={() => goTo('/profile')} title={isCollapsed ? user.fullName : undefined}>
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
