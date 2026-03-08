import {
  LuChevronRight,
  LuCircleCheck,
  LuTriangleAlert,
  LuLightbulb,
  LuBookOpen,
} from 'react-icons/lu';
import { capitalize } from '../utils/helpers';

export default function FeedbackPanel({ feedback, onNext }) {
  if (!feedback) return null;

  const fb = feedback.feedback || {};
  const recs = feedback.study_recommendations || [];
  const nextDiff = feedback.next_difficulty;

  return (
    <div className="feedback-panel card">
      {/* Feedback sections */}
      <div className="fb-sections">
        {fb.strengths && (
          <div className="fb-section fb-strengths">
            <h4><LuCircleCheck size={16} /> Strengths</h4>
            <p>{fb.strengths}</p>
          </div>
        )}
        {fb.weaknesses && (
          <div className="fb-section fb-weaknesses">
            <h4><LuTriangleAlert size={16} /> Weaknesses</h4>
            <p>{fb.weaknesses}</p>
          </div>
        )}
        {fb.improvements && (
          <div className="fb-section fb-improvements">
            <h4><LuLightbulb size={16} /> Improvements</h4>
            <p>{fb.improvements}</p>
          </div>
        )}
      </div>

      {/* Study recommendations */}
      {recs.length > 0 && (
        <div className="fb-recs">
          <h4><LuBookOpen size={16} /> Study Recommendations</h4>
          <ul>
            {recs.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Next difficulty & continue */}
      <div className="fb-actions">
        {nextDiff && (
          <span className="fb-next-badge">
            Next: <strong>{capitalize(nextDiff)}</strong>
          </span>
        )}
        <button className="btn btn-primary" onClick={onNext}>
          Next Question <LuChevronRight size={16} />
        </button>
      </div>

      <style>{`
        .feedback-panel { margin-top: 1.25rem; }

        .fb-sections {
          display: flex;
          flex-direction: column;
          gap: 1rem;
          margin-bottom: 1.25rem;
        }
        .fb-section {
          padding: 0.85rem 1rem;
          border-radius: var(--radius-sm);
          border-left: 3px solid;
        }
        .fb-section h4 {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.85rem;
          font-weight: 600;
          margin-bottom: 0.35rem;
        }
        .fb-section p { font-size: 0.9rem; line-height: 1.5; }

        .fb-strengths     { background: rgba(16,185,129,0.08); border-color: var(--success); }
        .fb-strengths h4  { color: var(--success); }
        .fb-weaknesses    { background: rgba(239,68,68,0.08); border-color: var(--danger); }
        .fb-weaknesses h4 { color: var(--danger); }
        .fb-improvements    { background: rgba(245,158,11,0.08); border-color: var(--warning); }
        .fb-improvements h4 { color: var(--warning); }

        .fb-recs {
          padding: 1rem;
          background: rgba(42,90,148,0.06);
          border-radius: var(--radius-sm);
          margin-bottom: 1.25rem;
        }
        .fb-recs h4 {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.85rem;
          color: var(--info);
          margin-bottom: 0.5rem;
        }
        .fb-recs ul { list-style: disc; padding-left: 1.25rem; }
        .fb-recs li { font-size: 0.88rem; margin-bottom: 0.25rem; }

        .fb-actions {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .fb-next-badge {
          font-size: 0.85rem;
          color: var(--text-muted);
        }
      `}</style>
    </div>
  );
}
