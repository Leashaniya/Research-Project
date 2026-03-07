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
<<<<<<< HEAD
          background: linear-gradient(180deg, var(--bg-sidebar) 0%, #1a2332 100%);
=======
          background: linear-gradient(180deg, var(--bg-sidebar) 0%, #0f172a 100%);
>>>>>>> e360af11 (Updated project files)
          border-right: 1px solid rgba(255, 255, 255, 0.1);
          display: flex;
          flex-direction: column;
          z-index: 100;
<<<<<<< HEAD
          backdrop-filter: blur(10px);
=======
>>>>>>> e360af11 (Updated project files)
          box-shadow: var(--shadow-xl);
        }

        .sidebar-brand {
          display: flex;
          align-items: center;
<<<<<<< HEAD
          gap: 1rem;
          padding: 2.5rem 2rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.15);
          position: relative;
=======
          gap: 0.75rem;
          padding: 1.75rem 1.5rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(255, 255, 255, 0.02);
>>>>>>> e360af11 (Updated project files)
        }

        .sidebar-logo {
          display: flex;
          align-items: center;
          justify-content: center;
<<<<<<< HEAD
          width: 52px;
          height: 52px;
          border-radius: 16px;
          background: linear-gradient(135deg, var(--primary-600), var(--primary-400));
          color: #fff;
          font-weight: 800;
          font-size: 1.2rem;
=======
          width: 48px;
          height: 48px;
          border-radius: var(--radius-lg);
          background: linear-gradient(135deg, var(--primary-500), var(--primary-600));
          color: #fff;
          font-weight: 800;
          font-size: 1.1rem;
>>>>>>> e360af11 (Updated project files)
          flex-shrink: 0;
          box-shadow: var(--shadow-lg);
          position: relative;
          overflow: hidden;
        }
<<<<<<< HEAD
=======

>>>>>>> e360af11 (Updated project files)
        .sidebar-logo::before {
          content: '';
          position: absolute;
          top: 0;
          left: -100%;
          width: 100%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
<<<<<<< HEAD
          transition: left 0.6s;
        }
=======
          transition: left 0.5s;
        }

>>>>>>> e360af11 (Updated project files)
        .sidebar-logo:hover::before {
          left: 100%;
        }

        .sidebar-title {
          font-size: 1.1rem;
          font-weight: 700;
<<<<<<< HEAD
          font-size: 1.1rem;
          line-height: 1.4;
          color: rgba(255, 255, 255, 0.95);
          letter-spacing: 0.02em;
=======
          color: #fff;
          line-height: 1.2;
>>>>>>> e360af11 (Updated project files)
        }

        .sidebar-nav {
          flex: 1;
<<<<<<< HEAD
          padding: 2rem 1.25rem;
=======
          padding: 1.5rem 0.75rem;
>>>>>>> e360af11 (Updated project files)
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .sidebar-link {
          display: flex;
          align-items: center;
<<<<<<< HEAD
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
=======
          gap: 0.75rem;
          padding: 0.875rem 1rem;
          border-radius: var(--radius);
          color: rgba(255, 255, 255, 0.7);
          text-decoration: none;
          font-weight: 500;
          font-size: 0.9rem;
          transition: var(--transition);
          position: relative;
          overflow: hidden;
>>>>>>> e360af11 (Updated project files)
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

        .sidebar-link:hover::before {
          left: 100%;
        }

        .sidebar-link:hover {
<<<<<<< HEAD
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(96, 165, 250, 0.1));
          color: #ffffff;
          text-decoration: none;
          transform: translateX(4px);
          box-shadow: var(--shadow-md);
        }
        .sidebar-link:hover::before {
          left: 100%;
=======
          background: rgba(255, 255, 255, 0.1);
          color: #fff;
          transform: translateX(4px);
>>>>>>> e360af11 (Updated project files)
        }

        .sidebar-link.active {
<<<<<<< HEAD
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.25), rgba(96, 165, 250, 0.15));
          color: #ffffff;
=======
          background: linear-gradient(135deg, var(--primary-600), var(--primary-700));
          color: #fff;
          box-shadow: var(--shadow-md);
>>>>>>> e360af11 (Updated project files)
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

        .sidebar-link.active::after {
          content: '';
          position: absolute;
          right: -1px;
          top: 50%;
          transform: translateY(-50%);
          width: 4px;
          height: 70%;
          background: linear-gradient(180deg, var(--primary-400), var(--primary-600));
          border-radius: 2px;
        }

        .sidebar-footer {
<<<<<<< HEAD
          padding: 1.5rem 1.25rem;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.6);
          text-align: center;
=======
          padding: 1.5rem;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(0, 0, 0, 0.1);
>>>>>>> e360af11 (Updated project files)
        }

        .sidebar-back-link {
          display: flex;
          align-items: center;
          gap: 0.5rem;
<<<<<<< HEAD
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
=======
          padding: 0.75rem 1rem;
          border-radius: var(--radius-sm);
          color: rgba(255, 255, 255, 0.6);
          text-decoration: none;
          font-size: 0.85rem;
          font-weight: 500;
          transition: var(--transition);
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(255, 255, 255, 0.05);
>>>>>>> e360af11 (Updated project files)
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
          gap: 0.25rem;
          padding: 0.5rem;
          color: rgba(255, 255, 255, 0.6);
          text-decoration: none;
          font-size: 0.7rem;
          font-weight: 500;
          transition: var(--transition);
          flex: 1;
        }

        .mobile-link:hover {
          color: #fff;
        }

        .mobile-link.active {
          color: var(--primary-600);
        }

        .mobile-link svg {
          width: 20px;
          height: 20px;
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
