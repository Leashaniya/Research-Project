import { useNavigate } from 'react-router-dom'
import { LuHouse, LuSearch } from 'react-icons/lu'

export default function NotFound() {
  const navigate = useNavigate()

  return (
    <div className="not-found-page">
      <div className="not-found-content fade-in">
        <div className="not-found-icon">
          <LuSearch size={64} />
        </div>
        <h1>404</h1>
        <p>The page you&apos;re looking for doesn&apos;t exist.</p>
        <button className="btn btn-primary btn-lg" onClick={() => navigate('/essay-support')}>
          <LuHouse size={18} /> Back to Home
        </button>
      </div>

      <style>{`
        .not-found-page {
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 60vh;
        }

        .not-found-content {
          text-align: center;
        }

        .not-found-icon {
          color: var(--text-muted);
          margin-bottom: 16px;
          opacity: 0.4;
        }

        .not-found-content h1 {
          font-size: 5rem;
          font-weight: 800;
          color: var(--text);
          line-height: 1;
          margin-bottom: 8px;
          letter-spacing: -0.04em;
        }

        .not-found-content p {
          font-size: 1.1rem;
          color: var(--text-secondary);
          margin-bottom: 28px;
        }
      `}</style>
    </div>
  )
}
