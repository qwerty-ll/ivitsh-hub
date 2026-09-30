import React, { useState, useEffect, Suspense, lazy } from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { X, Menu } from 'lucide-react';
import './styles/index.css';

// Components
import Sidebar from './components/Sidebar';
import TabBar from './components/TabBar';
import ChatWidget from './components/ChatWidget';
import CookieNotice from './components/CookieNotice';

// Lazy Loaded Pages for Optimal Bundle Splitting
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Schedule = lazy(() => import('./pages/Schedule'));
const Calendar = lazy(() => import('./pages/Calendar'));
const Tasks = lazy(() => import('./pages/Tasks'));
const TaskDetail = lazy(() => import('./pages/TaskDetail'));
const Associations = lazy(() => import('./pages/Associations'));
const AssociationDetail = lazy(() => import('./pages/AssociationDetail'));
const Events = lazy(() => import('./pages/Events'));
const Booking = lazy(() => import('./pages/Booking'));
const EventDetail = lazy(() => import('./pages/EventDetail'));
const Forum = lazy(() => import('./pages/Forum'));
const QuestionDetail = lazy(() => import('./pages/QuestionDetail'));
const CampusMap = lazy(() => import('./pages/CampusMap'));
const Teachers = lazy(() => import('./pages/Teachers'));
const FaqPage = lazy(() => import('./pages/FaqPage'));
const Profile = lazy(() => import('./pages/Profile'));
const AdminPanel = lazy(() => import('./pages/AdminPanel'));
const Privacy = lazy(() => import('./pages/Privacy'));

// Route loading placeholder: page-shaped skeleton instead of a spinner
const PageLoader = () => (
  <div className="container" aria-busy="true" aria-label="Загрузка страницы">
    <span className="skeleton" style={{ width: '40%', height: '2.25rem' }} />
    <span className="skeleton" style={{ width: '100%', height: '10rem', marginTop: 'var(--space-8)' }} />
    <span className="skeleton" style={{ width: '100%', height: '6rem', marginTop: 'var(--space-4)' }} />
  </div>
);

import { markStep, ROUTE_STEPS } from './utils/onboarding';
import { useAuth } from './context/AuthContext';

function App() {
  const location = useLocation();
  const { user } = useAuth();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Scroll to top on route change
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [location.pathname]);

  // Opening a section counts towards the dashboard checklist, however the user got there
  useEffect(() => {
    markStep(user?.id, ROUTE_STEPS[location.pathname]);
    if (user) markStep(user.id, 'profile-curator');
  }, [location.pathname, user?.id]);

  // Close the mobile drawer on navigation and with Escape
  useEffect(() => { setIsMobileMenuOpen(false); }, [location.pathname]);
  useEffect(() => {
    if (!isMobileMenuOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setIsMobileMenuOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isMobileMenuOpen]);

  return (
    <div className={`app-container ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <a className="skip-link" href="#main-content">Перейти к содержимому</a>

      {/* MOBILE APP BAR */}
      <header className="mobile-bar">
        <button
          className="btn btn-ghost btn-icon"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? 'Закрыть меню' : 'Открыть меню'}
          aria-expanded={isMobileMenuOpen}
          aria-controls="app-sidebar"
        >
          {isMobileMenuOpen ? <X size={22} strokeWidth={1.75} /> : <Menu size={22} strokeWidth={1.75} />}
        </button>
        <Link to="/" className="mobile-bar-brand">
          <img src="/img/mascot-160.png" alt="" className="mobile-bar-mark" />
          <span className="mobile-bar-title">ИВИТШ Хаб</span>
        </Link>
      </header>

      {isMobileMenuOpen && <div className="drawer-backdrop" onClick={() => setIsMobileMenuOpen(false)} aria-hidden="true" />}

      {/* SIDE NAVIGATION */}
      <Sidebar 
        isCollapsed={isSidebarCollapsed} 
        setIsCollapsed={setIsSidebarCollapsed} 
        isMobileOpen={isMobileMenuOpen}
        setIsMobileOpen={setIsMobileMenuOpen}
      />

      {/* MAIN CONTENT AREA */}
      <main id="main-content" className="app-main" tabIndex={-1}>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/calendar" element={<Calendar />} />
            <Route path="/schedule" element={<Schedule />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/tasks/:id" element={<TaskDetail />} />
            <Route path="/associations" element={<Associations />} />
            <Route path="/associations/:id" element={<AssociationDetail />} />
            <Route path="/events" element={<Events />} />
            <Route path="/booking" element={<Booking />} />
            <Route path="/events/:id" element={<EventDetail />} />
            <Route path="/forum" element={<Forum />} />
            <Route path="/forum/question/:id" element={<QuestionDetail />} />
            <Route path="/map" element={<CampusMap />} />
            <Route path="/teachers" element={<Teachers />} />
            <Route path="/faq" element={<FaqPage />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/admin" element={<AdminPanel />} />
            <Route path="/privacy" element={<Privacy />} />
          </Routes>
        </Suspense>
        <footer className="app-footer">
          <span>ИВИТШ Хаб · КГУ</span>
          <Link to="/privacy">Конфиденциальность и cookie</Link>
        </footer>
      </main>

      <TabBar />
      {/* A new account (or signing out) starts a clean chat: nobody sees or continues someone else's conversation */}
      <ChatWidget key={user?.id ?? 'guest'} />
      <CookieNotice />
    </div>
  );
}

export default App;
