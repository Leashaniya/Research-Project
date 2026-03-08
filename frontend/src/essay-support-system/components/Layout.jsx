import { Outlet, NavLink } from 'react-router-dom';
import CommonHeader from '../../components/CommonHeader';

const tabs = [
  { to: '/essay-support', end: true, label: 'Home' },
  { to: '/essay-support/practice', end: false, label: 'Practice' },
  { to: '/essay-support/analytics', end: false, label: 'Analytics' },
];

export default function Layout() {
  return (
    <div className="app-layout essay-layout-with-tabs">
      <CommonHeader />
      <div className="essay-tabs-wrap">
        <nav className="essay-tabs">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              className={({ isActive }) => `essay-tab-btn ${isActive ? 'active' : ''}`}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}
