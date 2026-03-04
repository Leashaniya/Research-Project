import { LuTarget, LuHash } from 'react-icons/lu';
import { getDifficultyColor } from '../utils/helpers';

export default function StatsCards({ session }) {
  if (!session) return null;

  const cards = [
    {
      icon: <LuHash size={22} />,
      label: 'Attempts',
      value: session.attempts || 0,
      gradient: 'linear-gradient(135deg, #7c3aed33, #a78bfa22)',
      color: 'var(--primary-400)',
    },
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
          grid-template-columns: repeat(2, 1fr);
          gap: 1rem;
          margin-bottom: 1.5rem;
        }
        .stat-card {
          border: 1px solid var(--border);
          border-radius: var(--radius);
          padding: 1rem 1.25rem;
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }
        .stat-icon {
          width: 42px;
          height: 42px;
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(0,0,0,0.18);
        }
        .stat-info {
          display: flex;
          flex-direction: column;
        }
        .stat-value {
          font-size: 1.25rem;
          font-weight: 700;
        }
        .stat-label {
          font-size: 0.75rem;
          color: var(--text-muted);
        }
        @media (max-width: 480px) {
          .stats-grid { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}
