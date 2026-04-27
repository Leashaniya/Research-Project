import { LuChevronRight } from 'react-icons/lu';

const levels = [
  {
    key: 'easy',
    title: 'Easy',
    description: 'Foundational concepts and basic recall questions.',
    color: 'var(--success)',
    gradient: 'linear-gradient(135deg, rgba(16,185,129,0.18), rgba(16,185,129,0.05))',
    border: 'rgba(16,185,129,0.35)',
  },
  {
    key: 'medium',
    title: 'Medium',
    description: 'Application and analysis of database theories.',
    color: 'var(--warning)',
    gradient: 'linear-gradient(135deg, rgba(245,158,11,0.18), rgba(245,158,11,0.05))',
    border: 'rgba(245,158,11,0.35)',
  },
  {
    key: 'hard',
    title: 'Hard',
    description: 'Complex synthesis and evaluation-level problems.',
    color: 'var(--danger)',
    gradient: 'linear-gradient(135deg, rgba(239,68,68,0.18), rgba(239,68,68,0.05))',
    border: 'rgba(239,68,68,0.35)',
  },
];

export default function DifficultySelector({ onSelect }) {
  return (
    <div className="difficulty-selector">
      <h2 className="ds-heading">Choose Difficulty Level</h2>
      <p className="ds-sub">Pick a level to begin your practice session.</p>

      <div className="ds-grid">
        {levels.map((l) => (
          <button
            key={l.key}
            className="ds-card"
            style={{
              background: l.gradient,
              borderColor: l.border,
            }}
            onClick={() => onSelect(l.key)}
          >
            <span className="ds-title" style={{ color: l.color }}>
              {l.title}
            </span>
            <p className="ds-desc">{l.description}</p>
            <span className="ds-action" style={{ color: l.color }}>
              Start <LuChevronRight size={14} />
            </span>
          </button>
        ))}
      </div>

      <style>{`
        .difficulty-selector {
          text-align: center;
          padding: 1rem 0;
        }
        .ds-heading { font-size: 1.4rem; font-weight: 700; margin-bottom: 0.25rem; }
        .ds-sub { color: var(--text-muted); margin-bottom: 1.5rem; }

        .ds-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1.25rem;
          max-width: 800px;
          margin: 0 auto;
        }

        .ds-card {
          border: 1px solid;
          border-radius: var(--radius);
          padding: 1.25rem 1rem;
          text-align: left;
          transition: transform 0.2s, box-shadow 0.2s;
          display: flex;
          flex-direction: column;
          gap: 0.4rem;
        }
        .ds-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 8px 24px rgba(0,0,0,0.25);
        }

        .ds-title { font-size: 1.15rem; font-weight: 700; }
        .ds-desc  { font-size: 0.85rem; color: var(--text-muted); flex: 1; }
        .ds-action {
          display: inline-flex;
          align-items: center;
          gap: 0.25rem;
          font-size: 0.85rem;
          font-weight: 600;
          margin-top: 0.25rem;
        }

        @media (max-width: 640px) {
          .ds-grid { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}
