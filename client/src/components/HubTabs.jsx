import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { HUBS, SECTIONS, hubOfPath, hubTabs } from '../data/sections';
import { useAuth } from '../context/AuthContext';

/**
 * Tabs over the pages that share one menu entry ("Календарь": my calendar and the timetable,
 * "Помощь": forum, map, teachers, FAQ, "Биты": tribes and the shop). Shown above the page itself.
 */
const HubTabs = () => {
  const { pathname } = useLocation();
  const { isLoggedIn } = useAuth();
  const hubId = hubOfPath(pathname);
  if (!hubId) return null;
  const tabs = hubTabs(hubId, isLoggedIn);
  if (tabs.length < 2) return null;
  return (
    <nav className={`hub-tabs-bar hue-${HUBS[hubId].hue}`} aria-label={HUBS[hubId].label}>
      <ul className="hub-tabs">
        {tabs.map((id) => {
          const { label, short, path, Icon } = SECTIONS[id];
          const active = pathname === path;
          return (
            <li key={id}>
              <Link to={path} className={`hub-tab ${active ? 'active' : ''}`} aria-current={active ? 'page' : undefined}>
                <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
                <span className="hub-tab-label">{label}</span>
                <span className="hub-tab-short" aria-hidden="true">{short}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};

export default HubTabs;
