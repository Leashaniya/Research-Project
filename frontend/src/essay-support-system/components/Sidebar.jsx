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
          background: linear-gradient(180deg, var(--bg-sidebar) 0%, #1a2332 100%);
          border-right: 1px solid rgba(255, 255, 255, 0.1);
          display: flex;
          flex-direction: column;
          z-index: 100;
          backdrop-filter: blur(10px);
          box-shadow: var(--shadow-xl);
        }

        .sidebar-brand {
          display: flex;
          align-items: center;
          gap: 1rem;
          padding: 2.5rem 2rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.15);
          position: relative;
        }

        .sidebar-logo {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 52px;
          height: 52px;
          border-radius: 16px;
          background: linear-gradient(135deg, var(--primary-600), var(--primary-400));
          color: #fff;
          font-weight: 800;
          font-size: 1.2rem;
          flex-shrink: 0;
          box-shadow: var(--shadow-lg);
          position: relative;
          overflow: hidden;
        }
        .sidebar-logo::before {
          content: '';
          position: absolute;
          top: 0;
          left: -100%;
          width: 100%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
          transition: left 0.6s;
        }
        .sidebar-logo:hover::before {
          left: 100%;
        }

        .sidebar-title {
          font-weight: 700;
          font-size: 1.1rem;
          line-height: 1.4;
          color: rgba(255, 255, 255, 0.95);
          letter-spacing: 0.02em;
        }

        .sidebar-nav {
          flex: 1;
          padding: 2rem 1.25rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .sidebar-link {
          display: flex;
          align-items: center;
          gap: 1rem;
          padding: 1rem 1.25rem;
          border-radius: var(--radius);
          color: rgba(255, 255, 255, 0.8);
          font-weight: 500;
          font-size: 0.95rem;
          transition: var(--transition);
          text-decoration: none;
          position: relative;
          overflow: hidden;
        }
        .sidebar-link::before {
          content: '';
          position: absolute;
          top: 0;
          left: -100%;
          width: 100%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
          transition: left 0.5s;
        }
        .sidebar-link:hover {
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(96, 165, 250, 0.1));
          color: #ffffff;
          text-decoration: none;
          transform: translateX(4px);
          box-shadow: var(--shadow-md);
        }
        .sidebar-link:hover::before {
          left: 100%;
        }
        .sidebar-link.active {
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.25), rgba(96, 165, 250, 0.15));
          color: #ffffff;
          font-weight: 600;
          box-shadow: var(--shadow-lg);
          transform: translateX(2px);
        }
        .sidebar-link.active::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
        }

        .sidebar-footer {
          padding: 1.5rem 1.25rem;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
          text-align: center;
        }

        .sidebar-back-link {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          color: rgba(255, 255, 255, 0.8);
          font-size: 0.85rem;
          font-weight: 500;
          margin-bottom: 0.75rem;
          text-decoration: none;
          transition: var(--transition);
        }
        .sidebar-back-link:hover {
          color: #ffffff;
          text-decoration: none;
          transform: translateX(2px);
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
          color: var(--primary-600);
        }

        @media (max-width: 768px) {
          .sidebar { display: none; }
          .mobile-nav { display: flex; }
        }
      `}</style>
    </>
  );
}
