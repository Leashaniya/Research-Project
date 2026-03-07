import { LuLoaderCircle } from 'react-icons/lu';

export default function LoadingOverlay({ message = 'Loading…' }) {
  return (
    <div className="loading-overlay">
      <div className="loading-spinner">
        <LuLoaderCircle className="spin-icon" size={36} />
      </div>
      <p className="loading-text">{message}</p>

      <style>{`
        .loading-overlay {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 4rem 1rem;
        }
        .loading-spinner {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 72px;
          height: 72px;
          border-radius: 50%;
          background: linear-gradient(135deg, var(--primary-600)22, var(--primary-400)11);
          margin-bottom: 1rem;
        }
        .spin-icon {
          color: var(--primary-400);
          animation: spin 1s linear infinite;
        }
        .loading-text {
          color: var(--text-muted);
          font-size: 0.95rem;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
