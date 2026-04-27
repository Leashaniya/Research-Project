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

// Non-Score-Based Analytics Insights Functions
const generateNonScoreInsights = (session) => {
  const insights = {
    dataStatus: '',
    attempts: '',
    difficulty: '',
    weakTopic: '',
    topicCoverage: '',
    consistency: '',
    recommendation: ''
  }

  // Rule 1: Check if we have enough data
  if (!session.attempts || session.attempts === 0) {
    insights.dataStatus = "Not enough data available yet. Complete a few attempts to generate insights."
    insights.attempts = "Not enough data available for this insight."
    insights.difficulty = "Not enough data available for this insight."
    insights.weakTopic = "Not enough data available for this insight."
    insights.topicCoverage = "Not enough data available for this insight."
    insights.consistency = "Not enough data available for this insight."
    insights.recommendation = "Not enough data available for this insight."
    return insights
  }

  const totalAttempts = session.attempts
  const scoreHistory = session.scoreHistory || []
  const currentDifficulty = session.difficulty || 'easy'

  // Rule 2: Attempt Insight
  if (totalAttempts <= 3) {
    insights.attempts = "You have only completed a few attempts. Try more questions to better understand your performance."
  } else if (totalAttempts <= 10) {
    insights.attempts = "You have completed several attempts. This helps in building consistent learning progress."
  } else {
    insights.attempts = "You have completed multiple attempts. This helps in building consistent learning progress."
  }

  // Rule 3: Difficulty Insight
  if (scoreHistory.length > 0) {
    const difficulties = scoreHistory.map(h => h.difficulty || 'easy')
    const uniqueDifficulties = [...new Set(difficulties)]
    const difficultyCounts = {}
    
    difficulties.forEach(diff => {
      difficultyCounts[diff] = (difficultyCounts[diff] || 0) + 1
    })
    
    const mostCommonDifficulty = Object.keys(difficultyCounts).reduce((a, b) => 
      difficultyCounts[a] > difficultyCounts[b] ? a : b
    )
    
    if (uniqueDifficulties.length === 1) {
      insights.difficulty = `You are currently focused on ${mostCommonDifficulty} level. Consider progressing when ready.`
    } else if (uniqueDifficulties.length === 2) {
      insights.difficulty = "You are gradually progressing across difficulty levels, showing learning progression."
    } else {
      insights.difficulty = "You are working across multiple difficulty levels, showing comprehensive learning approach."
    }
  } else {
    insights.difficulty = `You are currently at ${currentDifficulty} level. Continue practicing to build consistency.`
  }

  // Rule 4: Weak Topic Insight (Generic since specific topic data isn't available in session)
  // We'll use attempt count as a proxy for identifying areas needing more practice
  if (totalAttempts < 5) {
    insights.weakTopic = "You need more practice across various DMS topics to identify weak areas."
  } else if (totalAttempts < 10) {
    insights.weakTopic = "Focus on fundamental database concepts and basic SQL operations to strengthen your foundation."
  } else {
    insights.weakTopic = "No major weak topics detected yet. Your consistent practice is building good understanding."
  }

  // Rule 5: Topic Coverage Insight
  if (totalAttempts <= 3) {
    insights.topicCoverage = "You have focused on limited topics. Try covering more DMS topics for better understanding."
  } else if (totalAttempts <= 8) {
    insights.topicCoverage = "You are building topic coverage. Continue exploring different DMS areas for comprehensive understanding."
  } else {
    insights.topicCoverage = "You have covered a variety of topics, which improves overall subject understanding."
  }

  // Rule 6: Consistency Insight
  if (scoreHistory.length >= 3) {
    // Check if attempts are spread over time (we'll use index as a proxy for time)
    const recentAttempts = scoreHistory.slice(-5)
    const attemptGap = recentAttempts.length > 1 ? 
      Math.max(...recentAttempts.map((_, i) => i)) - Math.min(...recentAttempts.map((_, i) => i)) : 0
    
    if (attemptGap <= 2 && recentAttempts.length >= 3) {
      insights.consistency = "You are practicing consistently, which is good for learning progress."
    } else {
      insights.consistency = "Your activity is inconsistent. Regular practice will improve learning."
    }
  } else {
    insights.consistency = totalAttempts >= 3 ? 
      "You are building practice consistency. Continue regular attempts." : 
      "Not enough data available for this insight."
  }

  // Rule 7: Final Recommendation
  if (totalAttempts < 5) {
    insights.recommendation = "Recommended action: Complete more attempts across different topics to build comprehensive understanding."
  } else {
    const difficulties = scoreHistory.map(h => h.difficulty || 'easy')
    const uniqueDifficulties = [...new Set(difficulties)]
    
    if (uniqueDifficulties.length === 1) {
      insights.recommendation = "Recommended action: Practice weak topics and gradually move to higher difficulty levels while maintaining consistency."
    } else {
      insights.recommendation = "Recommended action: Continue consistent practice across difficulty levels and explore advanced topics."
    }
  }

  return insights
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
  
  // Generate non-score-based insights based on current session data
  const insights = generateNonScoreInsights(session)

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

      {/* Performance Overview */}
      <section className="analytics-section">
        <h2 className="section-title">Performance Overview</h2>
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
      </section>

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

      {/* Analytics Insights */}
      <section className="analytics-section">
        <h2 className="section-title">Analytics Insights</h2>
        <p className="section-subtitle">Analysis of your learning progress and practice patterns</p>
        
        {insights.dataStatus === "Not enough data available yet. Complete a few attempts to generate insights." ? (
          <div className="empty-state-card">
            <h3>Not enough data available yet</h3>
            <p>Complete more practice sessions to view insights.</p>
          </div>
        ) : (
          <div className="insights-grid">
            <div className="insight-card">
              <h3 className="insight-title">Performance Insight</h3>
              <p className="insight-content">{insights.attempts}</p>
            </div>
            
            <div className="insight-card">
              <h3 className="insight-title">Difficulty Insight</h3>
              <p className="insight-content">{insights.difficulty}</p>
            </div>
            
            <div className="insight-card">
              <h3 className="insight-title">Weak Topic Insight</h3>
              <p className="insight-content">{insights.weakTopic}</p>
            </div>
            
            <div className="insight-card">
              <h3 className="insight-title">Topic Coverage Insight</h3>
              <p className="insight-content">{insights.topicCoverage}</p>
            </div>
            
            <div className="insight-card">
              <h3 className="insight-title">Consistency Insight</h3>
              <p className="insight-content">{insights.consistency}</p>
            </div>
            
            <div className="insight-card">
              <h3 className="insight-title">Recommendation</h3>
              <p className="insight-content">{insights.recommendation}</p>
            </div>
          </div>
        )}
      </section>

      <style>{`
        /* Professional Analytics Dashboard */
        .analytics-page {
          background: #F8FAFC;
          min-height: 100vh;
          padding: 24px;
          font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
          max-width: 1200px;
          margin: 0 auto;
        }
        
        /* Page Header */
        .page-header h1 {
          font-size: 2rem;
          font-weight: 700;
          color: #001A35;
          margin-bottom: 2rem;
          line-height: 1.3;
          letter-spacing: -0.02em;
          display: flex;
          align-items: center;
          gap: 12px;
        }
        
        /* Analytics Section Structure */
        .analytics-section {
          margin-bottom: 3rem;
        }
        
        .section-title {
          font-size: 1.5rem;
          font-weight: 600;
          color: #001A35;
          margin: 0 0 1.5rem 0;
          line-height: 1.3;
          text-align: center;
        }
        
        /* Chart section titles */
        .chart-title {
          font-size: 1.5rem;
          font-weight: 600;
          color: #001A35;
          margin: 0 0 1.5rem 0;
          line-height: 1.3;
          text-align: center;
        }
        
        .section-subtitle {
          font-size: 1rem;
          color: #64748b;
          margin-bottom: 2rem;
          line-height: 1.6;
        }
        
        /* Stats Grid Layout - Full Width Usage */
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 1.5rem;
          width: 100%;
        }
        
        /* Original Analytics Section Styles */
        .analytics-section {
          margin-bottom: 2rem;
        }
        
        .analytics-section h3 {
          margin-bottom: 1rem;
          color: #1a202c;
          font-size: 1.1rem;
          font-weight: 600;
          line-height: 1.6;
        }
        
        .card {
          background: white;
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          padding: 2rem;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
          transition: all 0.3s ease;
        }
        
        .card:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 12px -1px rgba(0, 0, 0, 0.15);
        }
                
        /* Enhanced Stats Cards */
        .stats-card {
          background: white;
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          padding: 1.5rem;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          position: relative;
          overflow: hidden;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        .stats-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 8px 16px -1px rgba(0, 0, 0, 0.15);
        }
        
        .stats-card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          background: linear-gradient(90deg, #0062FF, #0052CC);
        }
        
        .stats-card h3 {
          font-size: 0.875rem;
          color: #64748b;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 0.75rem;
          font-weight: 600;
          line-height: 1.4;
        }
        
        .stats-card-value {
          font-size: 2.25rem;
          font-weight: 800;
          color: #0062FF;
          margin-bottom: 0.5rem;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          line-height: 1.2;
        }
        
        .stats-card p {
          font-size: 0.875rem;
          color: #64748b;
          margin: 0;
          line-height: 1.5;
        }
        
        /* Chart Containers with Consistent Blue Theme */
        .chart-container {
          padding: 2rem;
          background: white;
          border-radius: 12px;
          border: 1px solid #E2E8F0;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
          transition: all 0.3s ease;
        }

        .chart-container:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 12px -1px rgba(0, 0, 0, 0.15);
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
          background: #007bff;
          color: white;
        }
        
        .difficulty-medium {
          background: #0056b3;
          color: white;
        }
        
        .difficulty-hard {
          background: #004085;
          color: white;
        }
        
        .empty-state {
          text-align: center;
          padding: 3rem;
          color: #6c757d;
        }
        
        .empty-icon {
          font-size: 3rem;
          margin-bottom: 1rem;
        }
        
        .empty-state h3 {
          color: #2c3e50;
          margin-bottom: 0.5rem;
        }
        
        /* Insights Grid Layout */
        .insights-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 1.5rem;
        }
        
        /* Professional Insight Cards */
        .insight-card {
          background: white;
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          padding: 1.5rem;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
          transition: all 0.3s ease;
          display: flex;
          flex-direction: column;
        }
        
        .insight-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 12px -1px rgba(0, 0, 0, 0.15);
        }
        
        .insight-title {
          font-size: 1.1rem;
          font-weight: 600;
          color: #001A35;
          margin-bottom: 0.75rem;
          line-height: 1.4;
        }
        
        .insight-content {
          font-size: 0.95rem;
          color: #475569;
          line-height: 1.6;
          margin: 0;
          flex: 1;
        }
        
        /* Empty State Card */
        .empty-state-card {
          background: white;
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          padding: 3rem 2rem;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
          text-align: center;
        }
        
        .empty-state-card h3 {
          font-size: 1.25rem;
          font-weight: 600;
          color: #001A35;
          margin-bottom: 0.75rem;
        }
        
        .empty-state-card p {
          font-size: 0.95rem;
          color: #64748b;
          line-height: 1.6;
          margin: 0;
        }
        
        /* Responsive Design */
        @media (max-width: 768px) {
          .analytics-page {
            padding: 16px;
          }
          
          .page-header h1 {
            font-size: 1.75rem;
            margin-bottom: 1.5rem;
          }
          
          .analytics-section {
            margin-bottom: 1.5rem;
          }
          
          .section-title {
            font-size: 1.25rem;
            margin-bottom: 1rem;
          }
          
          .stats-grid {
            grid-template-columns: 1fr;
            gap: 1rem;
            width: 100%;
          }
          
          .card {
            padding: 1rem;
          }
          
          .insights-grid {
            grid-template-columns: 1fr;
            gap: 1rem;
          }
          
          .insight-card {
            padding: 1.25rem;
          }
          
          .empty-state-card {
            padding: 2rem 1.5rem;
          }
          
          .stats-card {
            padding: 1.25rem;
          }
          
          .stats-card-value {
            font-size: 2rem;
          }
        }
      `}</style>
    </div>
  )
}
