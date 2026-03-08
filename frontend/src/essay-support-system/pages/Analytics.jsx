import { useState, useEffect } from 'react'
import { LuChartBar, LuTrendingUp } from 'react-icons/lu'
import { useSession } from '../context/SessionContext'
import api from '../api/api'
import LoadingOverlay from '../components/LoadingOverlay'
import DifficultyCountVisualization from '../components/DifficultyCountVisualization'
import SessionProgressComparison from '../components/SessionProgressComparison'

// Helper function to convert reward numbers to simple evaluation terms
const getRewardMessage = (reward) => {
  if (reward > 10) return 'Excellent Work'
  if (reward > 5) return 'Very Good Attempt'
  if (reward > 0) return 'Good Attempt'
  if (reward === 0) return 'Satisfactory Attempt'
  if (reward > -5) return 'Needs Improvement'
  return 'Poor Attempt'
}

// Adaptive Difficulty Timeline Chart Component
const DifficultyTimeline = ({ data }) => {
  if (!data || data.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📊</div>
        <h3>Awaiting Practice Session Data</h3>
        <p>Engage in practice exercises to generate your adaptive learning analytics.</p>
      </div>
    )
  }

  const difficultyLevels = { easy: 1, medium: 2, hard: 3 }
  const width = 700
  const height = 250
  const padding = 50
  const chartWidth = width - 2 * padding
  const chartHeight = height - 2 * padding
  
  // Calculate positions
  const xStep = chartWidth / Math.max(data.length - 1, 1)
  const yScale = chartHeight / 2.5 // Scale for 3 difficulty levels
  
  const points = data.map((item, index) => {
    const x = padding + index * xStep
    const y = padding + chartHeight - (difficultyLevels[item.difficulty] * yScale)
    return { x, y, ...item }
  })

  const pathData = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')

  return (
    <div className="chart-container">
      <h3 className="chart-title">Adaptive Learning Progression</h3>
      <svg width={width} height={height} className="difficulty-chart">
        {/* Grid lines */}
        {[1, 2, 3].map((level, i) => (
          <line
            key={level}
            x1={padding}
            y1={padding + chartHeight - (level * yScale)}
            x2={width - padding}
            y2={padding + chartHeight - (level * yScale)}
            stroke="#e5e7eb"
            strokeWidth="1"
            strokeDasharray="3,3"
          />
        ))}
        
        {/* Difficulty labels */}
        <text x={padding - 20} y={padding + chartHeight - (1 * yScale) + 6} textAnchor="end" fill="#374151" fontSize="15" fontWeight="600">Easy</text>
        <text x={padding - 20} y={padding + chartHeight - (2 * yScale) + 6} textAnchor="end" fill="#374151" fontSize="15" fontWeight="600">Medium</text>
        <text x={padding - 20} y={padding + chartHeight - (3 * yScale) + 6} textAnchor="end" fill="#374151" fontSize="15" fontWeight="600">Hard</text>
        
        {/* Axes */}
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="#374151" strokeWidth="2"/>
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#374151" strokeWidth="2"/>
        
        {/* Timeline line */}
        <path
          d={pathData}
          fill="none"
          stroke="#2a5a94"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        
        {/* Data points */}
        {points.map((point, i) => (
          <g key={i}>
            <circle
              cx={point.x}
              cy={point.y}
              r="8"
              fill="#2a5a94"
              stroke="white"
              strokeWidth="3"
            />
            <text
              x={point.x}
              y={height - padding + 25}
              textAnchor="middle"
              fill="#374151"
              fontSize="14"
              fontWeight="600"
            >
              Exercise {i + 1}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

// Stats Card Component
const StatsCard = ({ title, value, subtitle, color = "primary", trend = null }) => (
  <div className={`stats-card stats-card-${color}`}>
    <div className="stats-card-content">
      <h3>{title}</h3>
      <div className="stats-card-value">
        {value}
        {trend && <span className={`trend ${trend > 0 ? 'positive' : trend < 0 ? 'negative' : 'neutral'}`}>
          {trend > 0 ? '↑' : trend < 0 ? '↓' : '→'} {Math.abs(trend)}%
        </span>}
      </div>
      <p>{subtitle}</p>
    </div>
  </div>
)

export default function Analytics() {
  const { session } = useSession()
  const [analyticsData, setAnalyticsData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      // Try to get analytics overview if available
      const data = await api.getAnalytics()
      setAnalyticsData(data)
    } catch (e) {
      // If analytics endpoint fails, we'll still show session-based data
      console.log('Analytics endpoint not available, using session data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  if (loading) return <LoadingOverlay message="Initializing performance analytics…" />

  return (
    <div className="analytics-page">
      <div className="page-header">
        <h1>
          <LuChartBar size={28} /> Performance Analytics Dashboard
        </h1>
      </div>

      {error && (
        <div className="alert alert-error">
          <p>{error}</p>
          <button onClick={loadData}>Reattempt Data Retrieval</button>
        </div>
      )}

      {/* Performance Metrics Overview */}
      <div className="analytics-section fade-in">
        <div className="stats-grid">
          <StatsCard
            title="Total Attempts"
            value={session.attempts}
            subtitle="Completed exercises"
            color="primary"
          />
          <StatsCard
            title="Current Mastery Level"
            value={session.difficulty.charAt(0).toUpperCase() + session.difficulty.slice(1)}
            subtitle="Adaptive learning progression"
            color="primary"
          />
        </div>
      </div>

      {/* Learning Progression Visualization */}
      <div className="analytics-section fade-in-up">
        <div className="card interactive">
          <DifficultyTimeline data={session.scoreHistory} />
        </div>
      </div>

      {/* Session Progress Comparison */}
      <div className="analytics-section fade-in-up">
        <div className="card interactive">
          <SessionProgressComparison session={session} />
        </div>
      </div>

      {/* Question Distribution Analysis */}
      <div className="analytics-section fade-in-up">
        <div className="card interactive">
          <DifficultyCountVisualization session={session} />
        </div>
      </div>

      <style>{`
        .analytics-page {
          padding: 1rem;
          max-width: 1200px;
          margin: 0 auto;
        }
        
        .analytics-section {
          margin-bottom: 2rem;
        }
        
        .analytics-section h3 {
          margin-bottom: 1rem;
          color: var(--text);
          font-size: 1.1rem;
          font-weight: 600;
        }
        
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 1rem;
          margin-bottom: 2rem;
        }
        
        .stats-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          padding: 1.5rem;
          transition: transform 0.2s, box-shadow 0.2s;
          position: relative;
          overflow: hidden;
        }
        
        .stats-card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          background: var(--primary);
        }
        
        .stats-card-success::before {
          background: var(--success);
        }
        
        .stats-card-warning::before {
          background: var(--warning);
        }
        
        .stats-card-danger::before {
          background: var(--danger);
        }
        
        .stats-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 24px rgba(0,0,0,0.1);
        }
        
        .stats-card h3 {
          font-size: 0.85rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 0.5rem;
          font-weight: 600;
        }
        
        .stats-card-value {
          font-size: 2rem;
          font-weight: 700;
          color: var(--text);
          margin-bottom: 0.25rem;
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        
        .trend {
          font-size: 0.9rem;
          font-weight: 500;
        }
        
        .trend.positive {
          color: var(--success);
        }
        
        .trend.negative {
          color: var(--danger);
        }
        
        .trend.neutral {
          color: var(--text-muted);
        }
        
        .stats-card p {
          font-size: 0.8rem;
          color: var(--text-muted);
          margin: 0;
        }
        
        .chart-container {
          padding: 2rem;
          background: white;
          border-radius: var(--radius);
          border: 1px solid var(--border);
        }
        
        .chart-title {
          text-align: center;
          margin-bottom: 2rem;
          color: var(--text);
          font-size: 1.3rem;
          font-weight: 600;
        }
        
        .difficulty-chart {
          max-width: 100%;
          height: auto;
          display: block;
          margin: 0 auto;
        }
        
        .difficulty-badge {
          padding: 0.25rem 0.75rem;
          border-radius: 12px;
          font-size: 0.9rem;
          font-weight: 600;
        }
        
        .difficulty-easy {
          background: var(--success);
          color: white;
        }
        
        .difficulty-medium {
          background: var(--warning);
          color: white;
        }
        
        .difficulty-hard {
          background: var(--danger);
          color: white;
        }
        
        .empty-state {
          text-align: center;
          padding: 3rem;
          color: var(--text-muted);
        }
        
        .empty-icon {
          font-size: 3rem;
          margin-bottom: 1rem;
        }
        
        .empty-state h3 {
          color: var(--text);
          margin-bottom: 0.5rem;
        }
        
        @media (max-width: 768px) {
          .analytics-page {
            padding: 0.5rem;
          }
          
          .stats-grid {
            grid-template-columns: 1fr;
          }
          
          .chart-container {
            padding: 1rem;
          }
          
          .difficulty-chart {
            width: 100%;
            height: auto;
          }
        }
      `}</style>
    </div>
  )
}
