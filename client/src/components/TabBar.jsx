import React from 'react';
import { NavLink } from 'react-router-dom';
import { SECTIONS, tabBarOrder } from '../data/sections';
import { useAuth } from '../context/AuthContext';

/** Phone-only bottom navigation: the main sections within thumb reach. */
const TabBar = () => {
  const { isLoggedIn } = useAuth();
  return (
    <nav className="tab-bar" aria-label="Быстрая навигация">
      <ul>
        {tabBarOrder(isLoggedIn).map((id) => {
          const { short, path, Icon, hue } = SECTIONS[id];
          return (
            <li key={id}>
              <NavLink to={path} end={path === '/'} className={({ isActive }) => `tab-bar-link hue-${hue} ${isActive ? 'active' : ''}`}>
                <span className="tab-bar-icon"><Icon size={22} strokeWidth={1.75} aria-hidden="true" /></span>
                <span className="tab-bar-label">{short}</span>
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};

export default TabBar;
