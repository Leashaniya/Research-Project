import React from 'react';



export default function DifficultyCountVisualization({ session }) {

  if (!session || !session.scoreHistory || session.scoreHistory.length === 0) {

    return (

      <div className="difficulty-count-container">

        <div className="empty-state">

          <div className="empty-icon">📊</div>

          <h3>No Practice Data Yet</h3>

          <p>Complete some exercises to see your difficulty distribution.</p>

        </div>

      </div>

    );

  }



  // Calculate difficulty counts from existing session data

  const difficultyCounts = {

    easy: session.scoreHistory.filter(item => item.difficulty === 'easy').length,

    medium: session.scoreHistory.filter(item => item.difficulty === 'medium').length,

    hard: session.scoreHistory.filter(item => item.difficulty === 'hard').length

  };



  const total = difficultyCounts.easy + difficultyCounts.medium + difficultyCounts.hard;

  

  // Calculate percentages

  const percentages = {

    easy: total > 0 ? Math.round((difficultyCounts.easy / total) * 100) : 0,

    medium: total > 0 ? Math.round((difficultyCounts.medium / total) * 100) : 0,

    hard: total > 0 ? Math.round((difficultyCounts.hard / total) * 100) : 0

  };



  // Difficulty colors and gradients

  const difficultyConfig = {

    easy: {

      color: '#22c55e',

      gradient: 'linear-gradient(135deg, #22c55e, #16a34a)',

      bgColor: 'rgba(34, 197, 94, 0.1)',

      borderColor: 'rgba(34, 197, 94, 0.3)',

      label: 'Easy',

      icon: '🟢'

    },

    medium: {

      color: '#2a5a94',

      gradient: 'linear-gradient(135deg, #2a5a94, #234a7a)',

      bgColor: 'rgba(42, 90, 148, 0.1)',

      borderColor: 'rgba(42, 90, 148, 0.3)',

      label: 'Medium',

      icon: '🔵'

    },

    hard: {

      color: '#f59e0b',

      gradient: 'linear-gradient(135deg, #f59e0b, #d97706)',

      bgColor: 'rgba(245, 158, 11, 0.1)',

      borderColor: 'rgba(245, 158, 11, 0.3)',

      label: 'Hard',

      icon: '🟡'

    }

  };



  return (

    <div className="difficulty-count-container">

      <h3 className="chart-title">Question Distribution by Difficulty</h3>



      {/* Summary Cards */}

      <div className="difficulty-summary-grid">

        {Object.entries(difficultyCounts).map(([difficulty, count]) => {

          const config = difficultyConfig[difficulty];

          return (

            <div 

              key={difficulty}

              className="difficulty-summary-card"

              style={{

                background: config.bgColor,

                borderColor: config.borderColor

              }}

            >

              <div className="difficulty-card-header">

                <span className="difficulty-icon">{config.icon}</span>

                <span className="difficulty-label">{config.label}</span>

              </div>

              <div className="difficulty-stats">

                <div className="difficulty-count" style={{ color: config.color }}>

                  {count}

                </div>

                <div className="difficulty-percentage">

                  {percentages[difficulty]}%

                </div>

              </div>

              <div className="difficulty-progress">

                <div 

                  className="difficulty-progress-bar"

                  style={{

                    width: `${percentages[difficulty]}%`,

                    background: config.gradient

                  }}

                />

              </div>

            </div>

          );

        })}

      </div>



      {/* Visual Distribution */}

      <div className="difficulty-visual-distribution">

        <h4>Visual Distribution</h4>

        <div className="distribution-bars">

          {Object.entries(difficultyCounts).map(([difficulty, count]) => {

            const config = difficultyConfig[difficulty];

            const maxHeight = 150;

            const height = total > 0 ? (count / Math.max(...Object.values(difficultyCounts))) * maxHeight : 0;

            

            return (

              <div key={difficulty} className="distribution-bar-container">

                <div className="distribution-bar-wrapper">

                  <div 

                    className="distribution-bar"

                    style={{

                      height: `${height}px`,

                      background: config.gradient

                    }}

                  />

                </div>

                <div className="bar-label">

                  <span className="bar-icon">{config.icon}</span>

                  <span className="bar-text">{config.label}</span>

                  <span className="bar-count">{count}</span>

                </div>

              </div>

            );

          })}

        </div>

      </div>



      <style>{`

        .difficulty-count-container {

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



        .difficulty-summary-grid {

          display: grid;

          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));

          gap: 1.5rem;

          margin-bottom: 2rem;

        }



        .difficulty-summary-card {

          border: 2px solid;

          border-radius: 12px;

          padding: 1.5rem;

          background: white;

          transition: all 0.3s ease;

          position: relative;

          overflow: hidden;

        }



        .difficulty-summary-card:hover {

          transform: translateY(-2px);

          box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);

        }



        .difficulty-card-header {

          display: flex;

          align-items: center;

          gap: 0.75rem;

          margin-bottom: 1rem;

        }



        .difficulty-icon {

          font-size: 1.5rem;

        }



        .difficulty-label {

          font-weight: 600;

          font-size: 0.875rem;

          color: #64748b;

          text-transform: uppercase;

          letter-spacing: 0.05em;

        }



        .difficulty-stats {

          display: flex;

          align-items: baseline;

          gap: 0.75rem;

          margin-bottom: 1rem;

        }



        .difficulty-count {

          font-size: 2.25rem;

          font-weight: 800;

          line-height: 1.2;

        }



        .difficulty-percentage {

          font-size: 0.875rem;

          color: #64748b;

          font-weight: 600;

        }



        .difficulty-progress {

          height: 6px;

          background: rgba(0, 0, 0, 0.1);

          border-radius: 3px;

          overflow: hidden;

        }



        .difficulty-progress-bar {

          height: 100%;

          border-radius: 3px;

          transition: width 0.8s ease;

        }



        .difficulty-total-summary {

          display: flex;

          justify-content: space-around;

          padding: 1.5rem;

          background: #f9fafb;

          border-radius: 12px;

          margin-bottom: 2rem;

          border: 1px solid #e5e7eb;

        }



        .total-item {

          text-align: center;

        }



        .total-label {

          display: block;

          font-size: 0.9rem;

          color: #6b7280;

          margin-bottom: 0.5rem;

          font-weight: 600;

        }



        .total-value {

          display: block;

          font-size: 1.8rem;

          font-weight: 800;

          color: #1f2937;

        }



        .difficulty-visual-distribution h4 {

          margin: 0 0 1.5rem 0;

          font-size: 1.1rem;

          font-weight: 600;

          color: #001A35;

        }



        .distribution-bars {

          display: flex;

          justify-content: space-around;

          align-items: flex-end;

          height: 200px;

          padding: 0 1rem;

        }



        .distribution-bar-container {

          display: flex;

          flex-direction: column;

          align-items: center;

          flex: 1;

          max-width: 100px;

        }



        .distribution-bar-wrapper {

          height: 150px;

          display: flex;

          align-items: flex-end;

          justify-content: center;

          width: 100%;

          margin-bottom: 1rem;

        }



        .distribution-bar {

          width: 60px;

          border-radius: 8px 8px 0 0;

          transition: height 0.8s ease;

          min-height: 4px;

          position: relative;

        }



        .distribution-bar::after {

          content: '';

          position: absolute;

          top: 0;

          left: 0;

          right: 0;

          height: 4px;

          background: rgba(255, 255, 255, 0.3);

          border-radius: 8px 8px 0 0;

        }



        .bar-label {

          display: flex;

          flex-direction: column;

          align-items: center;

          text-align: center;

        }



        .bar-icon {

          font-size: 1.2rem;

          margin-bottom: 0.25rem;

        }



        .bar-text {

          font-weight: 600;

          color: #001A35;

          font-size: 0.875rem;

          margin-bottom: 0.25rem;

        }



        .bar-count {

          font-size: 0.875rem;

          color: #64748b;

          font-weight: 600;

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

          .difficulty-count-container {

            padding: 1.5rem;

          }



          .difficulty-summary-grid {

            grid-template-columns: 1fr;

            gap: 1rem;

          }



          .difficulty-total-summary {

            flex-direction: column;

            gap: 1rem;

          }



          .distribution-bars {

            height: 150px;

          }



          .distribution-bar-wrapper {

            height: 100px;

          }



          .distribution-bar {

            width: 40px;

          }

        }

      `}</style>

    </div>

  );

}

