import { useState, useEffect } from 'react'
import { LuChartBar, LuRefreshCw } from 'react-icons/lu'
import api from '../api/api'
import LoadingOverlay from '../components/LoadingOverlay'
import ScoreLineChart from '../components/charts/ScoreLineChart'
import DifficultyBarChart from '../components/charts/DifficultyBarChart'
import { capitalize } from '../utils/helpers'

export default function Analytics() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadData = () => {
    setLoading(true)
    setError(null)
    api
      .getAnalytics()
      .then(setData)
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

  if (!data || data.total_attempts === 0) {
    return (
      <div>
        <div className="page-header">
          <h1><LuChartBar size={28} /> Analytics</h1>
        </div>
        <div className="card">
          <div className="empty-state">
            <div className="empty-icon">📊</div>
            <h3>No Analytics Yet</h3>
            <p>Complete some practice questions to see your performance analytics here.</p>
          </div>
        </div>
      </div>
    )
  }

  const engagementSeries = Array.from({ length: data.total_attempts }, (_, i) => i + 1)
  const difficultyEntries = Object.entries(data.difficulties || {})
  const topDifficulty = difficultyEntries.sort((a, b) => (b[1] || 0) - (a[1] || 0))[0]?.[0] || '—'
  const difficultySeries = (data.difficulty_over_time || []).map((d) => {
    if (d === 'easy') return 1
    if (d === 'medium') return 2
    if (d === 'hard') return 3
    return 0
  })
  const recentDifficulty = capitalize((data.difficulty_over_time || []).slice(-1)[0] || '—')

  return (
    <div className="analytics-page">
      <div className="page-header">
        <h1><LuChartBar size={28} /> Analytics Dashboard</h1>
        <button className="btn btn-outline" onClick={loadData}>
          <LuRefreshCw size={16} /> Refresh
        </button>
      </div>

      {/* Summary stat */}
      <div className="analytics-summary fade-in">
        <div className="summary-item">
          <span className="summary-value">{data.total_attempts}</span>
          <span className="summary-label">Total Sessions</span>
        </div>
        <div className="summary-item">
          <span className="summary-value">{capitalize(topDifficulty)}</span>
          <span className="summary-label">Most Practiced Difficulty</span>
        </div>
        <div className="summary-item">
          <span className="summary-value">{recentDifficulty}</span>
          <span className="summary-label">Most Recent Difficulty</span>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="charts-grid">
        <div className="card fade-in-up" style={{ animationDelay: '0s' }}>
          <div className="card-header">
            <h3>Engagement Over Sessions</h3>
          </div>
          <div className="card-body">
            <ScoreLineChart values={engagementSeries} label="Sessions" />
          </div>
        </div>

        <div className="card fade-in-up" style={{ animationDelay: '0.1s' }}>
          <div className="card-header">
            <h3>Difficulty Mix & Adaptation</h3>
          </div>
          <div className="card-body">
            <DifficultyBarChart difficulties={data.difficulties || {}} />
          </div>
        </div>

        <div className="card fade-in-up" style={{ animationDelay: '0.2s' }}>
          <div className="card-header">
            <h3>Difficulty Over Time</h3>
          </div>
          <div className="card-body">
            <ScoreLineChart values={difficultySeries} label="Difficulty Level" yMax={3} />
          </div>
        </div>

        <div className="card fade-in-up" style={{ animationDelay: '0.3s' }}>
          <div className="card-header">
            <h3>Insights</h3>
          </div>
          <div className="card-body insights">
            <div className="insight-row">
              <span className="insight-label">Most practiced difficulty</span>
              <span className="insight-value">{capitalize(topDifficulty)}</span>
            </div>
            <div className="insight-row">
              <span className="insight-label">Adaptation signal</span>
              <span className="insight-value">Adaptive mix based on recent sessions</span>
            </div>
          </div>
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

        .charts-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 20px;
        }

        .insights {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .insight-row {
          display: flex;
          justify-content: space-between;
          padding: 10px 0;
          border-bottom: 1px solid var(--border);
        }
        .insight-row:last-child { border-bottom: none; }
        .insight-label { color: var(--text-muted); font-size: 0.9rem; }
        .insight-value { font-weight: 700; }

        @media (max-width: 768px) {
          .analytics-summary { grid-template-columns: 1fr; }
          .charts-grid { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  )
}
