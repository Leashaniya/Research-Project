import { NavLink, Link } from 'react-router-dom';
import {
  LuHouse,
  LuBrain,
  LuChartBar,
  LuHistory,
  LuArrowLeft,
} from 'react-icons/lu';

const links = [
  { to: '/essay-support',          label: 'Home',      icon: <LuHouse size={20} /> },
  { to: '/essay-support/practice',  label: 'Practice',  icon: <LuBrain size={20} /> },
  { to: '/essay-support/analytics', label: 'Analytics', icon: <LuChartBar size={20} /> },
  { to: '/essay-support/history',   label: 'History',   icon: <LuHistory size={20} /> },
];

export default function Sidebar() {
  return (
    <>
      {/* Desktop sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="sidebar-logo">AL</span>
          <span className="sidebar-title">Adaptive<br />Learning</span>
        </div>

        <nav className="sidebar-nav">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === '/essay-support'}
              className={({ isActive }) =>
                `sidebar-link ${isActive ? 'active' : ''}`
              }
            >
              {l.icon}
              <span>{l.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <Link to="/" className="sidebar-back-link">
            <LuArrowLeft size={14} /> Back to Dashboard
          </Link>
          <p>AI-Powered Study Companion</p>
        </div>
      </aside>

      {/* Mobile bottom navigation */}
      <nav className="mobile-nav">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.to === '/essay-support'}
            className={({ isActive }) =>
              `mobile-link ${isActive ? 'active' : ''}`
            }
          >
            {l.icon}
            <span>{l.label}</span>
          </NavLink>
        ))}
      </nav>

      <style>{`
        /* ── Desktop Sidebar ── */
        .sidebar {
          position: fixed;
          top: 0; left: 0;
          width: var(--sidebar-w);
          height: 100vh;
          background: var(--bg-sidebar);
          border-right: 1px solid var(--border);
          display: flex;
          flex-direction: column;
          z-index: 100;
        }

        .sidebar-brand {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 1.5rem 1.25rem;
          border-bottom: 1px solid var(--border);
        }

        .sidebar-logo {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 42px;
          height: 42px;
          border-radius: 12px;
          background: linear-gradient(135deg, var(--primary-600), var(--primary-400));
          color: #fff;
          font-weight: 800;
          font-size: 1rem;
          flex-shrink: 0;
        }

        .sidebar-title {
          font-weight: 700;
          font-size: 0.95rem;
          line-height: 1.25;
          color: var(--text);
        }

        .sidebar-nav {
          flex: 1;
          padding: 1rem 0.75rem;
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .sidebar-link {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.7rem 1rem;
          border-radius: var(--radius-sm);
          color: var(--text-muted);
          font-weight: 500;
          font-size: 0.9rem;
          transition: all 0.2s;
          text-decoration: none;
        }
        .sidebar-link:hover {
          background: rgba(139, 92, 246, 0.08);
          color: var(--primary-400);
          text-decoration: none;
        }
        .sidebar-link.active {
          background: linear-gradient(135deg, rgba(124, 58, 237, 0.20), rgba(167, 139, 250, 0.10));
          color: var(--primary-400);
          font-weight: 600;
        }

        .sidebar-footer {
          padding: 1rem 1.25rem;
          border-top: 1px solid var(--border);
          font-size: 0.75rem;
          color: var(--text-muted);
          text-align: center;
        }

        .sidebar-back-link {
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
          color: var(--primary-400);
          font-size: 0.8rem;
          font-weight: 500;
          margin-bottom: 0.5rem;
          text-decoration: none;
          transition: color 0.2s;
        }
        .sidebar-back-link:hover {
          color: var(--primary-300);
          text-decoration: none;
        }

        /* ── Mobile Bottom Nav ── */
        .mobile-nav {
          display: none;
          position: fixed;
          bottom: 0;
          left: 0;
          right: 0;
          background: var(--bg-sidebar);
          border-top: 1px solid var(--border);
          justify-content: space-around;
          padding: 0.5rem 0;
          z-index: 100;
        }

        .mobile-link {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.2rem;
          font-size: 0.65rem;
          color: var(--text-muted);
          text-decoration: none;
          padding: 0.35rem 0.75rem;
        }
        .mobile-link.active {
          color: var(--primary-400);
        }

        @media (max-width: 768px) {
          .sidebar { display: none; }
          .mobile-nav { display: flex; }
        }
      `}</style>
    </>
  );
}
