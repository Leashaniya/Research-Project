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
    description:
      'Automatically extracts and formats questions from your lecture notes and past papers using OCR and AI enhancement.',
    color: 'var(--primary)',
    bg: 'var(--primary-50)',
  },
  {
    icon: <LuBrain size={28} />,
    title: 'AI-Powered Evaluation',
    description:
      'Your answers are evaluated by GPT with detailed feedback on strengths, weaknesses, and specific improvements.',
    color: 'var(--success)',
    bg: 'var(--success-light)',
  },
  {
    icon: <LuTrendingUp size={28} />,
    title: 'Adaptive Difficulty',
    description:
      'Reinforcement learning adjusts question difficulty based on your performance, concepts covered, and mistakes.',
    color: 'var(--secondary)',
    bg: '#ede9fe',
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
          <p>
            Practice with questions automatically extracted from your course PDFs.
            Get instant AI-powered feedback, track your progress, and let the
            system adapt to your learning pace using reinforcement learning.
          </p>
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
              <p>{feat.description}</p>
            </div>
          ))}
        </div>
      </section>

      <style>{`
        .home-page {
          max-width: 960px;
          margin: 0 auto;
        }

        /* Hero */
        .hero {
          text-align: center;
          padding: 60px 20px 48px;
        }

        .hero-badge {
          display: inline-block;
          padding: 6px 16px;
          background: var(--primary-50);
          color: var(--primary);
          border-radius: var(--radius-full);
          font-size: 0.8rem;
          font-weight: 600;
          margin-bottom: 20px;
        }

        .hero h1 {
          font-size: 2.6rem;
          font-weight: 800;
          line-height: 1.2;
          letter-spacing: -0.03em;
          margin-bottom: 16px;
          color: var(--text);
        }

        .hero-highlight {
          background: linear-gradient(135deg, var(--primary), var(--secondary));
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .hero p {
          font-size: 1.1rem;
          color: var(--text-secondary);
          max-width: 600px;
          margin: 0 auto 32px;
          line-height: 1.7;
        }

        .hero-actions {
          display: flex;
          gap: 12px;
          justify-content: center;
          flex-wrap: wrap;
        }

        /* Features */
        .features-section {
          padding: 20px 0 40px;
        }

        .section-title {
          font-size: 1.4rem;
          font-weight: 700;
          text-align: center;
          margin-bottom: 28px;
          color: var(--text);
        }

        .features-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 20px;
        }

        .feature-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          padding: 28px 24px;
          text-align: center;
          transition: var(--transition);
        }

        .feature-card:hover {
          transform: translateY(-3px);
          box-shadow: var(--shadow-lg);
        }

        .feature-icon {
          width: 56px;
          height: 56px;
          border-radius: var(--radius-lg);
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 16px;
        }

        .feature-card h3 {
          font-size: 1rem;
          font-weight: 700;
          margin-bottom: 8px;
        }

        .feature-card p {
          font-size: 0.85rem;
          color: var(--text-secondary);
          line-height: 1.6;
        }

        @media (max-width: 768px) {
          .hero h1 { font-size: 1.8rem; }
          .features-grid { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  )
}
