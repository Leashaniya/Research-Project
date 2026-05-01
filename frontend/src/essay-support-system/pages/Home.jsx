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
    description: 'Intelligently extracts relevant questions from your content based on meaning and context',
    color: 'var(--primary)',
    bg: 'var(--primary-50)',
  },
  {
    icon: <LuBrain size={28} />,
    title: 'AI-Powered Evaluation',
    description: 'Get instant, accurate feedback with our sophisticated AI evaluation system',
    color: 'var(--success)',
    bg: 'var(--success-light)',
  },
  {
    icon: <LuTrendingUp size={28} />,
    title: 'Adaptive Difficulty',
    description: 'Questions automatically adjust to your skill level for optimal learning',
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
        
        {/* Decorative background elements */}
        <div className="hero-decoration">
          <div className="decoration-circle decoration-circle-1"></div>
          <div className="decoration-circle decoration-circle-2"></div>
          <div className="decoration-circle decoration-circle-3"></div>
          <div className="decoration-grid"></div>
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
              <p className="feature-description">{feat.description}</p>
            </div>
          ))}
        </div>
      </section>

      <style>{`
        /* Global High-End SaaS Standards */
        .home-page {
          max-width: 1100px;
          margin: 0 auto;
          padding: 16px 0 40px;
          font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
          background: #F8FAFC;
        }

        /* Glassmorphism Hero Card */
        .hero {
          position: relative;
          text-align: center;
          padding: 40px 48px;
          background: rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.2);
          border-radius: 12px;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
          overflow: hidden;
          margin-bottom: 2.5rem;
        }

        .hero::before {
          content: '';
          position: absolute;
          inset: 0;
          background: 
            radial-gradient(circle at 20% 30%, rgba(147, 197, 253, 0.4) 0%, transparent 50%),
            radial-gradient(circle at 80% 70%, rgba(96, 165, 250, 0.3) 0%, transparent 50%),
            radial-gradient(circle at 40% 90%, rgba(219, 234, 254, 0.25) 0%, transparent 50%);
          opacity: 1;
        }

        .hero::after {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(135deg, rgba(37, 99, 235, 0.1), rgba(30, 64, 175, 0.05));
          opacity: 1;
        }

        .hero-content {
          position: relative;
          z-index: 2;
        }

        .hero-badge {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          padding: 12px 24px;
          background: linear-gradient(135deg, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0.08));
          color: #ffffff;
          border: 1px solid rgba(255, 255, 255, 0.25);
          border-radius: 50px;
          font-size: 0.95rem;
          font-weight: 600;
          letter-spacing: 0.04em;
          margin-bottom: 24px;
          backdrop-filter: blur(16px);
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
          text-transform: uppercase;
          transition: all 0.3s ease;
        }

        .hero-badge:hover {
          background: linear-gradient(135deg, rgba(255, 255, 255, 0.25), rgba(255, 255, 255, 0.12));
          transform: translateY(-2px);
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
        }

        .hero h1 {
          font-size: 3.5rem;
          font-weight: 900;
          line-height: 1.05;
          letter-spacing: -0.04em;
          margin-bottom: 24px;
          color: #ffffff;
          text-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        .hero-highlight {
          background: linear-gradient(135deg, #ffffff 0%, #e0f2fe 50%, #dbeafe 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
          position: relative;
        }

        .hero-actions {
          display: flex;
          gap: 24px;
          justify-content: center;
          flex-wrap: wrap;
          margin-top: 32px;
        }

        .hero-actions .btn {
          min-width: 180px;
          padding: 16px 28px;
          font-size: 1rem;
          font-weight: 700;
          border-radius: 12px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          position: relative;
          overflow: hidden;
        }

        .hero-actions .btn::before {
          content: '';
          position: absolute;
          top: 0;
          left: -100%;
          width: 100%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
          transition: left 0.5s;
        }

        .hero-actions .btn:hover::before {
          left: 100%;
        }

        /* Custom Primary Button Styling */
        .hero-actions .btn-primary {
          background: #007bff;
          color: white;
          border: none;
          transition: all 0.3s ease;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        .hero-actions .btn-primary:hover {
          background: #0056b3;
          transform: translateY(-2px);
          box-shadow: 0 8px 12px -1px rgba(0, 0, 0, 0.15);
        }

        .hero-actions .btn-outline {
          background: transparent;
          color: white;
          border: 2px solid rgba(255, 255, 255, 0.8);
          transition: all 0.3s ease;
        }

        .hero-actions .btn-outline:hover {
          background: rgba(255, 255, 255, 0.1);
          border-color: white;
          transform: translateY(-2px);
        }

        /* Decorative Elements */
        .hero-decoration {
          position: absolute;
          inset: 0;
          pointer-events: none;
          z-index: 1;
        }

        .decoration-circle {
          position: absolute;
          border-radius: 50%;
          filter: blur(40px);
        }

        .decoration-circle-1 {
          width: 300px;
          height: 300px;
          background: radial-gradient(circle, rgba(147, 197, 253, 0.4), transparent);
          top: -100px;
          left: -100px;
        }

        .decoration-circle-2 {
          width: 250px;
          height: 250px;
          background: radial-gradient(circle, rgba(96, 165, 250, 0.3), transparent);
          bottom: -80px;
          right: -80px;
        }

        .decoration-circle-3 {
          width: 200px;
          height: 200px;
          background: radial-gradient(circle, rgba(219, 234, 254, 0.25), transparent);
          top: 50%;
          left: 60%;
        }

        .decoration-grid {
          position: absolute;
          inset: 0;
          background-image: 
            linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
          background-size: 50px 50px;
          opacity: 0.5;
        }

        /* Features Section */
        .features-section {
          margin-bottom: 2rem;
        }

        .section-title {
          font-size: 2rem;
          font-weight: 600;
          color: #1a202c;
          text-align: center;
          margin-bottom: 2rem;
          letter-spacing: -0.02em;
          line-height: 1.6;
        }

        .features-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 2rem;
        }

        .feature-card {
          background: white;
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          padding: 2rem 1.5rem;
          text-align: center;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
          position: relative;
          overflow: hidden;
        }

        .feature-card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          background: linear-gradient(90deg, var(--primary), var(--primary-600));
          opacity: 0;
          transition: opacity 0.3s ease;
        }

        .feature-card:hover {
          transform: translateY(-8px);
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.12);
          border-color: var(--primary-200);
        }

        .feature-card:hover::before {
          opacity: 1;
        }

        .feature-icon {
          width: 80px;
          height: 80px;
          border-radius: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 1.5rem;
          background: linear-gradient(135deg, var(--primary-50), var(--primary-100));
          border: 1px solid var(--primary-200);
          box-shadow: 0 4px 20px rgba(37, 99, 235, 0.15);
          transition: all 0.3s ease;
        }

        .feature-card:hover .feature-icon {
          transform: scale(1.05);
          box-shadow: 0 8px 30px rgba(37, 99, 235, 0.25);
        }

        .feature-card h3 {
          font-size: 1.3rem;
          font-weight: 600;
          color: #1a202c;
          margin: 0 0 1rem 0;
          line-height: 1.4;
        }

        .feature-description {
          font-size: 0.95rem;
          color: #64748b;
          line-height: 1.6;
          margin: 0;
        }

        /* Animations */
        @keyframes fade-in {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes fade-in-up {
          from {
            opacity: 0;
            transform: translateY(30px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .fade-in {
          animation: fade-in 0.8s ease-out;
        }

        .fade-in-up {
          animation: fade-in-up 0.8s ease-out;
        }

        /* Responsive Design */
        @media (max-width: 768px) {
          .home-page {
            padding: 8px 0 30px;
          }

          .hero {
            padding: 50px 24px 40px;
            border-radius: 16px;
            margin-bottom: 2rem;
          }

          .hero h1 {
            font-size: 2.8rem;
            line-height: 1.1;
            margin-bottom: 24px;
          }

          .hero-badge {
            padding: 12px 20px;
            font-size: 0.85rem;
            margin-bottom: 24px;
          }

          .hero-actions {
            gap: 16px;
            margin-top: 32px;
          }

          .hero-actions .btn {
            min-width: 160px;
            padding: 16px 24px;
            font-size: 1rem;
          }

          .section-title {
            font-size: 1.8rem;
            margin-bottom: 2rem;
          }

          .features-grid {
            grid-template-columns: 1fr;
            gap: 1.5rem;
          }

          .feature-card {
            padding: 2rem 1.5rem;
          }

          .feature-icon {
            width: 70px;
            height: 70px;
            margin-bottom: 1.2rem;
          }

          .feature-card h3 {
            font-size: 1.2rem;
            margin-bottom: 0.8rem;
          }

          .feature-description {
            font-size: 0.9rem;
          }
        }

        @media (max-width: 480px) {
          .hero h1 {
            font-size: 2.4rem;
          }

          .hero-actions {
            flex-direction: column;
            align-items: center;
          }

          .hero-actions .btn {
            width: 100%;
            max-width: 280px;
          }
        }
      `}</style>
    </div>
  )
}