import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { navEntry, tabBarOrder } from '../data/sections';
import { useAuth } from '../context/AuthContext';

/** Phone-only bottom navigation: the main sections within thumb reach. */
const TabBar = () => {
  const { isLoggedIn } = useAuth();
  const { pathname } = useLocation();
  return (
    <nav className="tab-bar" aria-label="Быстрая навигация">
      <ul>
        {tabBarOrder(isLoggedIn).map((id) => {
          const { key, short, path, paths, Icon, hue } = navEntry(id, isLoggedIn);
          // A hub ("Календарь") stays highlighted on any of its tabs
          const active = path === '/' ? pathname === '/' : paths.some(p => pathname === p || pathname.startsWith(`${p}/`));
          return (
            <li key={key}>
              <Link to={path} className={`tab-bar-link hue-${hue} ${active ? 'active' : ''}`}
                aria-current={active ? 'page' : undefined}>
                <span className="tab-bar-icon"><Icon size={22} strokeWidth={1.75} aria-hidden="true" /></span>
                <span className="tab-bar-label">{short}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};

export default TabBar;
