import { LuTarget } from 'react-icons/lu';
import { getDifficultyColor } from '../utils/helpers';

export default function StatsCards({ session }) {
  if (!session) return null;

  const cards = [
    {
      icon: <LuTarget size={22} />,
      label: 'Difficulty',
      value: (session.difficulty || 'easy').toUpperCase(),
      gradient: `linear-gradient(135deg, ${getDifficultyColor(session.difficulty)}33, ${getDifficultyColor(session.difficulty)}11)`,
      color: getDifficultyColor(session.difficulty),
    },
  ];

  return (
    <div className="stats-grid">
      {cards.map((c) => (
        <div key={c.label} className="stat-card" style={{ background: c.gradient }}>
          <div className="stat-icon" style={{ color: c.color }}>{c.icon}</div>
          <div className="stat-info">
            <span className="stat-value" style={{ color: c.color }}>{c.value}</span>
            <span className="stat-label">{c.label}</span>
          </div>
        </div>
      ))}

      <style>{`
        .stats-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 1.5rem;
          margin-bottom: 2rem;
        }
        
        .stat-card {
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          padding: 1.5rem 1.25rem;
          display: flex;
          align-items: center;
          gap: 1rem;
          background: var(--bg-card);
          box-shadow: var(--shadow-sm);
          transition: var(--transition);
          position: relative;
          overflow: hidden;
        }

        .stat-card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 3px;
          background: linear-gradient(90deg, var(--primary-500), var(--primary-600));
          opacity: 0;
          transition: var(--transition);
        }

        .stat-card:hover {
          box-shadow: var(--shadow-md);
          transform: translateY(-2px);
        }

        .stat-card:hover::before {
          opacity: 1;
        }
        
        .stat-icon {
          width: 48px;
          height: 48px;
          border-radius: var(--radius-lg);
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(255, 255, 255, 0.9);
          box-shadow: var(--shadow-sm);
          flex-shrink: 0;
        }
        
        .stat-info {
          display: flex;
          flex-direction: column;
          flex: 1;
        }
        
        .stat-value {
          font-size: 1.5rem;
          font-weight: 800;
          line-height: 1.2;
          margin-bottom: 0.25rem;
        }
        
        .stat-label {
          font-size: 0.8rem;
          color: var(--text-muted);
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        @media (max-width: 480px) {
          .stats-grid { 
            grid-template-columns: 1fr; 
          }
          
          .stat-card {
            padding: 1.25rem 1rem;
          }
          
          .stat-icon {
            width: 42px;
            height: 42px;
          }
          
          .stat-value {
            font-size: 1.25rem;
          }
        }
      `}</style>
    </div>
  );
}
