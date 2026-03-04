import { useState, useEffect } from 'react'
import { LuHistory, LuRefreshCw } from 'react-icons/lu'
import api from '../api/api'
import { formatDate, capitalize } from '../utils/helpers'
import LoadingOverlay from '../components/LoadingOverlay'

export default function History() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ topic: 'all', difficulty: 'all' })

  const loadData = () => {
    setLoading(true)
    setError(null)
    api
      .getHistory()
      .then((data) => setHistory(data.history || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(loadData, [])

  // Extract unique topics
  const topics = [...new Set(history.map((h) => h.topic))].filter(Boolean)

  // Filter
  const filtered = history.filter((entry) => {
    if (filters.topic !== 'all' && entry.topic !== filters.topic) return false
    if (filters.difficulty !== 'all' && entry.difficulty !== filters.difficulty) return false
    return true
  })

  if (loading) return <LoadingOverlay message="Loading history…" />

  return (
    <div className="history-page">
      <div className="page-header">
        <h1>
          <LuHistory size={28} /> Attempt History
        </h1>
        <button className="btn btn-outline" onClick={loadData}>
          <LuRefreshCw size={16} /> Refresh
        </button>
      </div>

      {error && (
        <div className="alert alert-error">
          <p>{error}</p>
          <button onClick={loadData}>Retry</button>
        </div>
      )}

      {/* Filters */}
      <div className="history-filters fade-in">
        <select
          className="select"
          value={filters.topic}
          onChange={(e) => setFilters((f) => ({ ...f, topic: e.target.value }))}
        >
          <option value="all">All Topics</option>
          {topics.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <select
          className="select"
          value={filters.difficulty}
          onChange={(e) => setFilters((f) => ({ ...f, difficulty: e.target.value }))}
        >
          <option value="all">All Difficulties</option>
          <option value="easy">Easy</option>
          <option value="medium">Medium</option>
          <option value="hard">Hard</option>
        </select>

        <span className="filter-count">
          {filtered.length} of {history.length} entries
        </span>
      </div>

      {/* Table */}
      <div className="card fade-in">
        {filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <h3>No Attempts Yet</h3>
            <p>
              {history.length === 0
                ? 'Complete some practice questions to see your history here.'
                : 'No entries match the selected filters.'}
            </p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Date</th>
                  <th>Topic</th>
                  <th>Difficulty</th>
                  <th>Score</th>
                  <th>Reward</th>
                  <th>Concepts</th>
                  <th>Mistakes</th>
                  <th>Words</th>
                </tr>
              </thead>
              <tbody>
                {filtered
                  .slice()
                  .reverse()
                  .map((entry, i) => {
                    const score = parseFloat(entry.score) || 0
                    const reward = parseFloat(entry.reward) || 0
                    return (
                      <tr key={i}>
                        <td style={{ fontWeight: 600 }}>{entry.attempt}</td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                          {formatDate(entry.timestamp)}
                        </td>
                        <td>
                          <span className="badge badge-topic">{entry.topic}</span>
                        </td>
                        <td>
                          <span className={`badge badge-${entry.difficulty}`}>
                            {capitalize(entry.difficulty)}
                          </span>
                        </td>
                        <td>
                          <span
                            style={{
                              fontWeight: 700,
                              color:
                                score >= 80
                                  ? 'var(--success)'
                                  : score >= 50
                                    ? 'var(--warning)'
                                    : 'var(--danger)',
                            }}
                          >
                            {score}%
                          </span>
                        </td>
                        <td>
                          <span
                            style={{
                              fontWeight: 600,
                              color:
                                reward > 0
                                  ? 'var(--success)'
                                  : reward < 0
                                    ? 'var(--danger)'
                                    : 'var(--text-muted)',
                            }}
                          >
                            {reward > 0 ? '+' : ''}
                            {reward}
                          </span>
                        </td>
                        <td>{entry.concepts}</td>
                        <td>{entry.mistakes}</td>
                        <td>{entry.answer_length}</td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <style>{`
        .history-filters {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 20px;
          flex-wrap: wrap;
        }

        .filter-count {
          margin-left: auto;
          font-size: 0.85rem;
          color: var(--text-muted);
          font-weight: 500;
        }
      `}</style>
    </div>
  )
}
