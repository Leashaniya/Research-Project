import { useNavigate } from 'react-router-dom'
import {
  LuBrain,
  LuFileText,
  LuTrendingUp,
  LuChevronRight,
} from 'react-icons/lu'

const features = [
  {
    icon: <LuFileText size={28} />,
    title: 'Smart Question Extraction',
    color: 'var(--primary)',
    bg: 'var(--primary-50)',
  },
  {
    icon: <LuBrain size={28} />,
    title: 'AI-Powered Evaluation',
    color: 'var(--success)',
    bg: 'var(--success-light)',
  },
  {
    icon: <LuTrendingUp size={28} />,
    title: 'Adaptive Difficulty',
    color: 'var(--secondary)',
    bg: 'var(--primary-50)',
  },
]

export default function Home() {
  const navigate = useNavigate()

  return (
    <div className="home-page">
      {/* Hero */}
      <section className="hero fade-in">
        <div className="hero-content">
          <span className="hero-badge">AI-Powered Adaptive Learning</span>
          <h1>
            Master Your Subjects with{' '}
            <span className="hero-highlight">Intelligent Practice</span>
          </h1>

          <div className="hero-actions">
            <button
              className="btn btn-primary btn-lg"
              onClick={() => navigate('/essay-support/practice')}
            >
              Start Practicing <LuChevronRight size={20} />
            </button>
            <button
              className="btn btn-outline btn-lg"
              onClick={() => navigate('/essay-support/analytics')}
            >
              View Analytics
            </button>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="features-section">
        <h2 className="section-title">How It Works</h2>
        <div className="features-grid">
          {features.map((feat, idx) => (
            <div
              key={idx}
              className="feature-card fade-in-up"
              style={{ animationDelay: `${idx * 0.1}s` }}
            >
              <div
                className="feature-icon"
                style={{ background: feat.bg, color: feat.color }}
              >
                {feat.icon}
              </div>
              <h3>{feat.title}</h3>
            </div>
          ))}
        </div>
      </section>

      <style>{`
        .home-page {
          max-width: 1100px;
          margin: 0 auto;
          padding: 8px 0 72px;
        }

        /* Hero */
        .hero {
          position: relative;
          text-align: center;
          padding: 120px 48px 100px;
          background: linear-gradient(135deg, var(--primary-900) 0%, var(--primary-800) 50%, var(--primary-700) 100%);
          border: none;
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-xl);
          overflow: hidden;
          margin-bottom: 4rem;
        }

        .hero::before {
          content: '';
          position: absolute;
          inset: 0;
          background: 
            radial-gradient(circle at 20% 30%, rgba(59, 130, 246, 0.3) 0%, transparent 50%),
            radial-gradient(circle at 80% 70%, rgba(96, 165, 250, 0.2) 0%, transparent 50%),
            radial-gradient(circle at 40% 90%, rgba(147, 197, 253, 0.15) 0%, transparent 50%);
          opacity: 1;
        }
        .hero::after {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(135deg, rgba(30, 64, 175, 0.1), rgba(30, 58, 138, 0.05));
          opacity: 1;
        }

        .hero-content {
          position: relative;
          z-index: 1;
        }

        .hero-badge {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          padding: 12px 24px;
          background: linear-gradient(135deg, rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0.05));
          color: #ffffff;
          border: 1px solid rgba(255, 255, 255, 0.2);
          border-radius: var(--radius-full);
          font-size: 0.95rem;
          font-weight: 600;
          letter-spacing: 0.03em;
          margin-bottom: 36px;
          backdrop-filter: blur(12px);
          box-shadow: var(--shadow-md);
          text-transform: uppercase;
        }

        .hero h1 {
          font-size: 4rem;
          font-weight: 900;
          line-height: 1.05;
          letter-spacing: -0.04em;
          margin-bottom: 28px;
          color: #ffffff;
          text-shadow: 0 6px 24px rgba(0, 0, 0, 0.4);
        }

        .hero-highlight {
          background: linear-gradient(135deg, #ffffff 0%, #e0f2fe 50%, #dbeafe 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
          position: relative;
        }
        .hero-highlight::after {
          content: '';
          position: absolute;
          bottom: -2px;
          left: 0;
          width: 100%;
          height: 2px;
          background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.6), transparent);
          border-radius: 2px;
        }

        .hero-actions {
          display: flex;
          gap: 20px;
          justify-content: center;
          flex-wrap: wrap;
          margin-top: 40px;
        }

        .hero-actions .btn {
          min-width: 200px;
          padding: 18px 28px;
          font-size: 1.1rem;
          font-weight: 700;
          border-radius: var(--radius);
        }

        /* Features */
        .features-section {
          padding: 36px 0 0;
        }

        .section-title {
          font-size: 2rem;
          font-weight: 800;
          text-align: center;
          margin-bottom: 3rem;
          color: var(--text);
          letter-spacing: -0.02em;
        }

        .features-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 24px;
        }

        .feature-card {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 20px;
          padding: 32px 24px;
          text-align: center;
          transition: var(--transition);
          box-shadow: var(--shadow-sm);
        }

        .feature-card:hover {
          transform: translateY(-8px);
          border-color: var(--primary-300);
          box-shadow: var(--shadow-lg);
        }

        .feature-icon {
          width: 70px;
          height: 70px;
          border-radius: var(--radius-lg);
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 20px;
          background: var(--primary-50);
          border: 1px solid var(--primary-200);
          box-shadow: var(--shadow-sm);
        }

        .feature-card h3 {
          font-size: 1.1rem;
          font-weight: 700;
          margin: 0;
          color: var(--text);
          letter-spacing: -0.01em;
        }

        @media (max-width: 768px) {
          .hero { padding: 56px 20px 48px; }
          .hero h1 { font-size: 2.2rem; }
          .features-grid { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  )
}