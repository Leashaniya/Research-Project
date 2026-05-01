import React from 'react';

export default function SessionProgressComparison({ session }) {
  if (!session || !session.scoreHistory || session.scoreHistory.length < 5) {
    return (
      <div className="session-comparison-container">
        <div className="empty-state">
          <div className="empty-icon">📈</div>
          <h3>Building Progress Data</h3>
          <p>Complete at least 5 exercises to see progress comparison.</p>
        </div>
      </div>
    );
  }

  // Calculate rolling window comparison (frontend-only logic)
  const calculateProgressComparison = (scoreHistory) => {
    const totalAttempts = scoreHistory.length;
    
    // Define window sizes for comparison
    const recentWindowSize = Math.min(5, Math.floor(totalAttempts / 2));
    const historicalWindowSize = Math.min(10, totalAttempts - recentWindowSize);
    
    if (totalAttempts < recentWindowSize + historicalWindowSize) {
      // Not enough data for comparison, use what we have
      const allData = scoreHistory.slice(-totalAttempts);
      return {
        recent: calculateProgressMetrics(allData),
        historical: null,
        comparison: null,
        trend: calculateTrend(allData)
      };
    }
    
    // Recent progress (last N attempts)
    const recentData = scoreHistory.slice(-recentWindowSize);
    // Historical progress (previous N attempts)
    const historicalData = scoreHistory.slice(-recentWindowSize - historicalWindowSize, -recentWindowSize);
    
    const recentMetrics = calculateProgressMetrics(recentData);
    const historicalMetrics = calculateProgressMetrics(historicalData);
    
    return {
      recent: recentMetrics,
      historical: historicalMetrics,
      comparison: {
        progressRate: {
          recent: recentMetrics.difficultyProgressionRate,
          historical: historicalMetrics.difficultyProgressionRate,
          improvement: recentMetrics.difficultyProgressionRate > historicalMetrics.difficultyProgressionRate
        },
        consistency: {
          recent: recentMetrics.consistencyScore,
          historical: historicalMetrics.consistencyScore,
          improvement: recentMetrics.consistencyScore > historicalMetrics.consistencyScore
        },
        velocity: {
          recent: recentMetrics.learningVelocity,
          historical: historicalMetrics.learningVelocity,
          improvement: recentMetrics.learningVelocity > historicalMetrics.learningVelocity
        }
      },
      trend: calculateTrend(scoreHistory)
    };
  };

  // Calculate progress metrics for a data set
  const calculateProgressMetrics = (data) => {
    if (!data || data.length === 0) {
      return {
        difficultyProgressionRate: 0,
        consistencyScore: 0,
        learningVelocity: 0,
        avgDifficulty: 'easy'
      };
    }

    // Difficulty progression rate
    const difficultyChanges = data.filter((item, index) => 
      index > 0 && item.difficulty !== data[index - 1].difficulty
    ).length;
    const difficultyProgressionRate = (difficultyChanges / (data.length - 1)) * 100;

    // Consistency score (how stable performance is)
    const difficultyValues = data.map(item => {
      const levels = { easy: 1, medium: 2, hard: 3 };
      return levels[item.difficulty] || 1;
    });
    const avgDifficultyValue = difficultyValues.reduce((sum, val) => sum + val, 0) / difficultyValues.length;
    const variance = difficultyValues.reduce((sum, val) => sum + Math.pow(val - avgDifficultyValue, 2), 0) / difficultyValues.length;
    const consistencyScore = Math.max(0, 100 - (variance * 25));

    // Learning velocity (difficulty advancement per attempt)
    const firstDifficulty = difficultyValues[0];
    const lastDifficulty = difficultyValues[difficultyValues.length - 1];
    const learningVelocity = (lastDifficulty - firstDifficulty) / data.length;

    // Average difficulty
    const avgDifficultyNum = Math.round(avgDifficultyValue);
    const avgDifficulty = avgDifficultyNum === 1 ? 'easy' : avgDifficultyNum === 2 ? 'medium' : 'hard';

    return {
      difficultyProgressionRate: Math.round(difficultyProgressionRate),
      consistencyScore: Math.round(consistencyScore),
      learningVelocity: Math.round(learningVelocity * 100) / 100,
      avgDifficulty,
      dataPoints: data.length
    };
  };

  // Calculate overall trend
  const calculateTrend = (scoreHistory) => {
    if (scoreHistory.length < 3) return 'insufficient';
    
    const difficultyValues = scoreHistory.map(item => {
      const levels = { easy: 1, medium: 2, hard: 3 };
      return levels[item.difficulty] || 1;
    });
    
    const firstHalf = difficultyValues.slice(0, Math.floor(difficultyValues.length / 2));
    const secondHalf = difficultyValues.slice(Math.floor(difficultyValues.length / 2));
    
    const firstAvg = firstHalf.reduce((sum, val) => sum + val, 0) / firstHalf.length;
    const secondAvg = secondHalf.reduce((sum, val) => sum + val, 0) / secondHalf.length;
    
    if (secondAvg > firstAvg + 0.3) return 'improving';
    if (secondAvg < firstAvg - 0.3) return 'declining';
    return 'stable';
  };

  const comparison = calculateProgressComparison(session.scoreHistory);

  const getTrendIcon = (trend) => {
    switch (trend) {
      case 'improving': return '📈';
      case 'declining': return '📉';
      case 'stable': return '➡️';
      default: return '❓';
    }
  };

  const getTrendColor = (trend) => {
    switch (trend) {
      case 'improving': return '#22c55e';
      case 'declining': return '#ef4444';
      case 'stable': return '#2a5a94';
      default: return '#6b7280';
    }
  };

  const getImprovementIcon = (improvement) => {
    return improvement ? '✅' : '❌';
  };

  const getImprovementColor = (improvement) => {
    return improvement ? '#22c55e' : '#ef4444';
  };

  return (
    <div className="session-comparison-container">
      <h3 className="chart-title">Session Progress Comparison</h3>

      {/* Overall Trend */}
      <div className="overall-trend">
        <div className="trend-card">
          <div className="trend-header">
            <span className="trend-icon">{getTrendIcon(comparison.trend)}</span>
            <span className="trend-label">Overall Trend</span>
          </div>
          <div className="trend-value" style={{ color: getTrendColor(comparison.trend) }}>
            {comparison.trend.charAt(0).toUpperCase() + comparison.trend.slice(1)}
          </div>
        </div>
      </div>

      <style>{`
        .session-comparison-container {
          background: white;
          border-radius: 16px;
          padding: 2rem;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        }

        .chart-title {
          font-size: 1.5rem;
          font-weight: 600;
          color: #001A35;
          margin: 0 0 1.5rem 0;
          line-height: 1.3;
          text-align: center;
        }

        .overall-trend {
          margin-bottom: 2rem;
        }

        .trend-card {
          background: linear-gradient(135deg, #f8fafc, #f1f5f9);
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          padding: 1.5rem;
          text-align: center;
          transition: all 0.3s ease;
        }

        .trend-icon {
          font-size: 2rem;
        }

        .trend-label {
          font-weight: 600;
          color: #374151;
          font-size: 1.1rem;
        }

        .trend-value {
          font-size: 1.8rem;
          font-weight: 800;
          margin-top: 0.5rem;
        }

        .comparison-metrics {
          margin-bottom: 2rem;
        }

        .metric-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 1.5rem;
        }

        .metric-card {
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
          padding: 1.5rem;
          transition: all 0.3s ease;
        }

        .metric-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
          border-color: #d1d5db;
        }

        .metric-header {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          margin-bottom: 1.5rem;
        }

        .metric-icon {
          font-size: 1.5rem;
        }

        .metric-title {
          font-weight: 600;
          color: #374151;
          font-size: 1.1rem;
        }

        .metric-comparison {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1rem;
          margin-bottom: 1.5rem;
        }

        .metric-value {
          text-align: center;
          padding: 1rem;
          border-radius: 8px;
          background: #f9fafb;
        }

        .metric-value.recent {
          border: 2px solid #2a5a94;
        }

        .metric-value.historical {
          border: 2px solid #6b7280;
        }

        .value-label {
          display: block;
          font-size: 0.8rem;
          color: #6b7280;
          margin-bottom: 0.5rem;
          font-weight: 600;
        }

        .value {
          display: block;
          font-size: 1.5rem;
          font-weight: 700;
          color: #1f2937;
        }

        .improvement-indicator {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.75rem;
          background: #f9fafb;
          border-radius: 8px;
          border: 1px solid #e5e7eb;
        }

        .improvement-icon {
          font-size: 1.2rem;
        }

        .improvement-text {
          font-weight: 600;
          color: #374151;
        }

        .current-session-summary {
          background: #f8fafc;
          border-radius: 12px;
          padding: 1.5rem;
          border: 1px solid #e2e8f0;
        }

        .current-session-summary h4 {
          margin: 0 0 1rem 0;
          font-size: 1.2rem;
          font-weight: 600;
          color: #1f2937;
        }

        .summary-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 1rem;
        }

        .summary-item {
          text-align: center;
          padding: 1rem;
          background: white;
          border-radius: 8px;
          border: 1px solid #e5e7eb;
        }

        .summary-label {
          display: block;
          font-size: 0.85rem;
          color: #6b7280;
          margin-bottom: 0.5rem;
          font-weight: 600;
        }

        .summary-value {
          display: block;
          font-size: 1.3rem;
          font-weight: 700;
          color: #1f2937;
        }

        .empty-state {
          text-align: center;
          padding: 3rem 2rem;
          color: #6b7280;
        }

        .empty-icon {
          font-size: 3rem;
          margin-bottom: 1rem;
        }

        .empty-state h3 {
          margin: 0 0 0.5rem 0;
          color: #374151;
        }

        .empty-state p {
          margin: 0;
          font-size: 0.95rem;
        }

        @media (max-width: 768px) {
          .session-comparison-container {
            padding: 1.5rem;
          }

          .metric-grid {
            grid-template-columns: 1fr;
            gap: 1rem;
          }

          .metric-comparison {
            grid-template-columns: 1fr;
            gap: 0.75rem;
          }

          .summary-grid {
            grid-template-columns: 1fr;
          }

          .trend-value {
            font-size: 1.5rem;
          }
        }
      `}</style>
    </div>
  );
}
