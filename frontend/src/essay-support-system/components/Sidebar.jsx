import { NavLink, Link } from 'react-router-dom';
import {
  LuHouse,
  LuBrain,
  LuChartBar,
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
        /* ── Enhanced Desktop Sidebar ── */
        .sidebar {
          position: fixed;
          top: 0; left: 0;
          width: var(--sidebar-w);
          height: 100vh;
          background: linear-gradient(180deg, var(--bg-sidebar) 0%, #0f172a 100%);
          border-right: 1px solid rgba(255, 255, 255, 0.1);
          display: flex;
          flex-direction: column;
          z-index: 100;
          box-shadow: var(--shadow-xl);
        }

        .sidebar-brand {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 1.75rem 1.5rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(255, 255, 255, 0.02);
        }

        .sidebar-logo {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 48px;
          height: 48px;
          border-radius: var(--radius-lg);
          background: linear-gradient(135deg, var(--primary-500), var(--primary-600));
          color: #fff;
          font-weight: 800;
          font-size: 1.1rem;
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
          transition: left 0.5s;
        }

        .sidebar-logo:hover::before {
          left: 100%;
        }

        .sidebar-title {
          font-size: 1.1rem;
          font-weight: 700;
          color: #fff;
          line-height: 1.2;
        }

        .sidebar-nav {
          flex: 1;
          padding: 1.5rem 0.75rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .sidebar-link {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.85rem 1rem;
          border-radius: 12px;
          color: rgba(255, 255, 255, 0.8);
          font-weight: 500;
          font-size: 0.9rem;
          transition: all 0.3s ease;
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
          transition: left 0.5s ease;
        }

        .sidebar-link:hover::before {
          left: 100%;
        }

        .sidebar-link:hover {
          background: rgba(255, 255, 255, 0.1);
          color: #fff;
          transform: translateX(4px);
        }

        .sidebar-link.active {
          background: linear-gradient(135deg, var(--primary-500), var(--primary-600));
          color: #fff;
          font-weight: 600;
          box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3);
          transform: translateX(4px);
        }

        .sidebar-footer {
          padding: 1.5rem;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(0, 0, 0, 0.1);
        }

        .sidebar-back-link {
          display: flex;
          align-items: center;
          padding: 0.75rem 1rem;
          border-radius: var(--radius-sm);
          color: rgba(255, 255, 255, 0.6);
          text-decoration: none;
          font-size: 0.85rem;
          font-weight: 500;
          transition: var(--transition);
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(255, 255, 255, 0.05);
        }

        .sidebar-back-link:hover {
          background: rgba(255, 255, 255, 0.1);
          color: #fff;
          transform: translateY(-1px);
          box-shadow: var(--shadow-sm);
        }

        .sidebar-footer p {
          margin-top: 1rem;
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.4);
          text-align: center;
          font-weight: 500;
        }

        /* ── Enhanced Mobile Navigation ── */
        .mobile-nav {
          display: none;
          position: fixed;
          bottom: 0;
          left: 0;
          right: 0;
          background: linear-gradient(180deg, var(--bg-sidebar) 0%, #0f172a 100%);
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          padding: 0.5rem 0;
          z-index: 100;
          box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.1);
        }

        .mobile-link {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.3rem;
          font-size: 0.65rem;
          color: rgba(255, 255, 255, 0.8);
          text-decoration: none;
          padding: 0.5rem 0.75rem;
          border-radius: 12px;
          transition: all 0.3s ease;
        }

        .mobile-link:hover {
          background: rgba(255, 255, 255, 0.15);
          color: #fff;
        }

        .mobile-link.active {
          color: #fff;
          background: linear-gradient(135deg, var(--primary-500), var(--primary-600));
        }

        @media (max-width: 768px) {
          .sidebar { display: none; }
          .mobile-nav { 
            display: flex; 
            justify-content: space-around;
          }
          .app-content {
            margin-left: 0 !important;
            padding-bottom: 5rem !important;
          }
        }
      `}</style>
    </>
  );
}
