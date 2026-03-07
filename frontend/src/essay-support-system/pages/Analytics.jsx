import { useState, useEffect } from 'react'
import { LuChartBar, LuRefreshCw, LuTrendingUp, LuTarget } from 'react-icons/lu'
import api from '../api/api'
import LoadingOverlay from '../components/LoadingOverlay'

// Helper function to convert difficulty to numeric value
const difficultyToNumber = (difficulty) => {
  const map = { easy: 1, medium: 2, hard: 3 }
  return map[difficulty] || 2
}

// Helper function to convert number back to difficulty
const numberToDifficulty = (num) => {
  const map = { 1: 'easy', 2: 'medium', 3: 'hard' }
  return map[num] || 'medium'
}

export default function Analytics() {
  const [sessionData, setSessionData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadData = () => {
    setLoading(true)
    setError(null)
    
    // Fetch only session data for consistency
    api.getStats()
      .then(stats => {
        setSessionData(stats)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(loadData, [])

  if (loading) return <LoadingOverlay message="Loading analytics…" />

  if (error) {
    return (
      <div>
        <div className="page-header">
          <h1><LuChartBar size={28} /> Analytics</h1>
        </div>
        <div className="alert alert-error">
          <p>{error}</p>
          <button onClick={loadData}>Retry</button>
        </div>
      </div>
    )
  }

  // Process session flow data from session history
  const sessionFlowData = sessionData?.score_history?.map((item, index) => ({
    x: index + 1,
    y: difficultyToNumber(item.difficulty),
    question: `Q${index + 1}`,
    difficulty: item.difficulty,
    score: item.score
  })) || []

  // Process difficulty distribution from SESSION data (not analytics data)
  const difficultyDistribution = {}
  sessionData?.score_history?.forEach(item => {
    const diff = item.difficulty || 'medium'
    difficultyDistribution[diff] = (difficultyDistribution[diff] || 0) + 1
  })

  const totalSessionAttempts = sessionData?.attempts || 0

  // Calculate statistics
  const avgScore = sessionData?.average_score || 0
  const currentDifficulty = sessionData?.difficulty || 'medium'

  return (
    <div className="analytics-page">
      <div className="page-header">
        <h1><LuChartBar size={28} /> Analytics Dashboard</h1>
        <button className="btn btn-outline" onClick={loadData}>
          <LuRefreshCw size={16} /> Refresh
        </button>
      </div>

      {/* Summary Statistics */}
      <div className="analytics-summary">
        <div className="summary-item">
          <span className="summary-value">{totalSessionAttempts}</span>
          <span className="summary-label">Total Attempts</span>
        </div>
        <div className="summary-item">
          <span className="summary-value">{avgScore}</span>
          <span className="summary-label">Average Score</span>
        </div>
        <div className="summary-item">
          <span className="summary-value">{currentDifficulty.charAt(0).toUpperCase() + currentDifficulty.slice(1)}</span>
          <span className="summary-label">Current Difficulty</span>
        </div>
      </div>

      {/* Session Flow Chart */}
      <div className="card">
        <div className="card-header">
          <h3><LuTrendingUp size={20} /> Session Difficulty Flow</h3>
        </div>
        <div className="card-body">
          {sessionFlowData.length > 0 ? (
            <SessionFlowChart data={sessionFlowData} />
          ) : (
            <div className="empty-state">
              <div className="empty-icon">📈</div>
              <h3>No Session Data</h3>
              <p>Complete some practice questions to see your session flow here.</p>
            </div>
          )}
        </div>
      </div>

      {/* Difficulty Distribution */}
      <div className="card">
        <div className="card-header">
          <h3><LuTarget size={20} /> Difficulty Distribution</h3>
        </div>
        <div className="card-body">
          {totalSessionAttempts > 0 ? (
            <DifficultyDistribution data={difficultyDistribution} total={totalSessionAttempts} />
          ) : (
            <div className="empty-state">
              <p>No difficulty data available</p>
            </div>
          )}
        </div>
      </div>

      <style>{`
        .analytics-summary {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 16px;
          margin-bottom: 24px;
        }

        .summary-item {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          padding: 20px;
          text-align: center;
        }

        .summary-value {
          display: block;
          font-size: 2rem;
          font-weight: 800;
          color: var(--primary);
          line-height: 1.2;
        }

        .summary-label {
          font-size: 0.8rem;
          color: var(--text-muted);
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .card {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          margin-bottom: 20px;
          overflow: hidden;
        }

        .card-header {
          padding: 20px;
          border-bottom: 1px solid var(--border);
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .card-header h3 {
          margin: 0;
          font-size: 1.1rem;
          font-weight: 600;
          color: var(--text);
        }

        .card-body {
          padding: 20px;
        }

        .empty-state {
          text-align: center;
          padding: 40px 20px;
          color: var(--text-muted);
        }

        .empty-icon {
          font-size: 3rem;
          margin-bottom: 16px;
        }

        .empty-state h3 {
          margin: 0 0 8px 0;
          color: var(--text);
        }

        @media (max-width: 768px) {
          .analytics-summary {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  )
}

// Session Flow Chart Component
function SessionFlowChart({ data }) {
  const maxValue = Math.max(...data.map(d => d.y), 3)
  const minValue = Math.min(...data.map(d => d.y), 1)
  
  return (
    <div className="session-flow-chart">
      <div className="chart-container">
        {/* Y-axis labels */}
        <div className="y-axis">
          <div className="y-label" style={{ top: '0%' }}>Hard</div>
          <div className="y-label" style={{ top: '50%' }}>Medium</div>
          <div className="y-label" style={{ top: '100%' }}>Easy</div>
        </div>
        
        {/* Chart area */}
        <div className="chart-area">
          {/* Grid lines */}
          <div className="grid-line" style={{ top: '0%' }}></div>
          <div className="grid-line" style={{ top: '50%' }}></div>
          <div className="grid-line" style={{ top: '100%' }}></div>
          
          {/* Line chart */}
          {data.length > 1 && (
            <svg className="chart-line" viewBox="0 0 100 60" preserveAspectRatio="none">
              <polyline
                fill="none"
                stroke="var(--primary)"
                strokeWidth="2"
                points={data.map((d, i) => {
                  const x = (i / (data.length - 1)) * 100
                  const y = ((maxValue - d.y) / (maxValue - minValue)) * 60
                  return `${x},${y}`
                }).join(' ')}
              />
            </svg>
          )}
          
          {/* Data points */}
          {data.map((point, index) => (
            <div
              key={index}
              className="data-point"
              style={{
                left: `${(index / (data.length - 1)) * 100}%`,
                top: `${((maxValue - point.y) / (maxValue - minValue)) * 100}%`
              }}
              title={`${point.question}: ${point.difficulty} (Score: ${point.score})`}
            >
              <span className="point-label" style={{ top: '-20px' }}>{point.question}</span>
            </div>
          ))}
        </div>
        
        {/* X-axis */}
        <div className="x-axis">
          {data.map((point, index) => (
            <div key={index} className="x-label">
              {point.question}
            </div>
          ))}
        </div>
      </div>
      
      <style>{`
        .session-flow-chart {
          width: 100%;
          height: 300px;
          position: relative;
        }
        
        .chart-container {
          width: 100%;
          height: 100%;
          position: relative;
          display: flex;
        }
        
        .y-axis {
          width: 60px;
          position: relative;
          padding-right: 10px;
        }
        
        .y-label {
          position: absolute;
          right: 0;
          font-size: 0.8rem;
          color: var(--text-muted);
          transform: translateY(-50%);
        }
        
        .chart-area {
          flex: 1;
          position: relative;
          height: 240px;
          border-left: 1px solid var(--border);
          border-bottom: 1px solid var(--border);
        }
        
        .grid-line {
          position: absolute;
          left: 0;
          right: 0;
          height: 1px;
          background: var(--border);
          opacity: 0.5;
        }
        
        .chart-line {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
        }
        
        .data-point {
          position: absolute;
          width: 12px;
          height: 12px;
          background: var(--primary);
          border: 2px solid white;
          border-radius: 50%;
          transform: translate(-50%, -50%);
          cursor: pointer;
          z-index: 2;
        }
        
        .data-point:hover {
          transform: translate(-50%, 50%) scale(1.2);
        }
        
        .point-label {
          position: absolute;
          top: -20px;
          left: 50%;
          transform: translateX(-50%);
          font-size: 0.7rem;
          color: var(--text-muted);
          white-space: nowrap;
        }
        
        .x-axis {
          position: absolute;
          bottom: -30px;
          left: 60px;
          right: 0;
          display: flex;
          justify-content: space-between;
          padding: 0 10px;
        }
        
        .x-label {
          font-size: 0.8rem;
          color: var(--text-muted);
          text-align: center;
        }
      `}</style>
    </div>
  )
}

// Difficulty Distribution Component
function DifficultyDistribution({ data, total }) {
  const difficulties = ['easy', 'medium', 'hard']
  const colors = {
    easy: '#10b981',    // Green
    medium: '#f59e0b',  // Orange/Yellow
    hard: '#ef4444'     // Red
  }
  
  return (
    <div className="difficulty-distribution">
      <div className="distribution-bars">
        {difficulties.map(level => {
          const count = data[level] || 0
          const percentage = total > 0 ? (count / total) * 100 : 0
          
          return (
            <div key={level} className="difficulty-item">
              <div className="difficulty-label">{level.charAt(0).toUpperCase() + level.slice(1)}</div>
              <div className="difficulty-bar-container">
                <div 
                  className="difficulty-bar"
                  style={{
                    width: `${percentage}%`,
                    backgroundColor: colors[level]
                  }}
                />
              </div>
              <div className="difficulty-count">{count}</div>
            </div>
          )
        })}
      </div>
      
      <style>{`
        .difficulty-distribution {
          width: 100%;
        }
        
        .distribution-bars {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        
        .difficulty-item {
          display: flex;
          align-items: center;
          gap: 16px;
        }
        
        .difficulty-label {
          width: 80px;
          font-size: 0.9rem;
          font-weight: 500;
          color: var(--text);
        }
        
        .difficulty-bar-container {
          flex: 1;
          height: 32px;
          background: var(--border);
          border-radius: var(--radius-lg);
          position: relative;
          overflow: hidden;
        }
        
        .difficulty-bar {
          height: 100%;
          border-radius: var(--radius-lg);
          transition: width 0.3s ease;
          min-width: 8px;
        }
        
        .difficulty-count {
          width: 40px;
          text-align: right;
          font-size: 0.9rem;
          font-weight: 600;
          color: var(--text);
        }
      `}</style>
    </div>
  )
}
