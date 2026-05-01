import { useState, useRef, useEffect } from 'react'
import { LuBrain, LuRefreshCw } from 'react-icons/lu'
import { useSession } from '../context/SessionContext'
import api from '../api/api'
import StatsCards from '../components/StatsCards'
import DifficultySelector from '../components/DifficultySelector'
import QuestionCard from '../components/QuestionCard'
import AnswerCard from '../components/AnswerCard'
import FeedbackPanel from '../components/FeedbackPanel'
import LoadingOverlay from '../components/LoadingOverlay'

const PHASE = {
  IDLE: 'idle',
  LOADING: 'loading',
  ANSWERING: 'answering',
  EVALUATING: 'evaluating',
  FEEDBACK: 'feedback',
}

export default function Practice() {
  const { session, startSession, resetSession, updateFromResult } = useSession()
  const [phase, setPhase] = useState(PHASE.IDLE)
  const [question, setQuestion] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [error, setError] = useState(null)
  const [showDiffMenu, setShowDiffMenu] = useState(false)
  const diffMenuRef = useRef(null)

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (diffMenuRef.current && !diffMenuRef.current.contains(e.target)) {
        setShowDiffMenu(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleChangeDifficulty = (level) => {
    setShowDiffMenu(false)
    session.difficulty = level
    fetchQuestion(level)
  }

  const fetchQuestion = async (difficulty) => {
    setPhase(PHASE.LOADING)
    setError(null)
    try {
      const data = await api.getQuestion(difficulty)
      if (data.success) {
        setQuestion(data)
        setPhase(PHASE.ANSWERING)
      } else {
        setError(data.message || 'Failed to get question.')
        setPhase(PHASE.IDLE)
      }
    } catch (e) {
      setError(e.message)
      setPhase(PHASE.IDLE)
    }
  }

  const handleStartSession = async (difficulty) => {
    setError(null)
    setPhase(PHASE.LOADING)
    try {
      const data = await startSession(difficulty)
      if (data.success) {
        await fetchQuestion(difficulty)
      } else {
        setError(data.message || 'Failed to start session.')
        setPhase(PHASE.IDLE)
      }
    } catch (e) {
      setError(e.message)
      setPhase(PHASE.IDLE)
    }
  }

  const handleSubmitAnswer = async (answer) => {
    setPhase(PHASE.EVALUATING)
    setError(null)
    try {
      const data = await api.submitAnswer({
        answer: answer,
        question: question?.question,
        difficulty: session.difficulty,
        batch_mode: false
      })
      // Backend returns data directly, not with success field
      if (data && data.feedback) {
        setFeedback(data)
        updateFromResult(data)
        setPhase(PHASE.FEEDBACK)
      } else {
        setError('Evaluation failed - invalid response')
        setPhase(PHASE.ANSWERING)
      }
    } catch (e) {
      console.error('Submit answer error:', e)
      setError(e.message || 'Evaluation failed.')
      setPhase(PHASE.ANSWERING)
    }
  }

  const handleNextQuestion = () => {
    setFeedback(null)
    fetchQuestion(session.difficulty)
  }

  const handleSkip = () => {
    setFeedback(null)
    fetchQuestion(session.difficulty)
  }

  const handleReset = async () => {
    await resetSession()
    setPhase(PHASE.IDLE)
    setQuestion(null)
    setFeedback(null)
    setError(null)
  }

  return (
    <div className="practice-page">
      <div className="page-header">
        <h1>
          <LuBrain size={28} /> Practice Session
        </h1>
        {phase !== PHASE.IDLE && (
          <button className="btn btn-outline" onClick={handleReset}>
            <LuRefreshCw size={16} /> Reset Session
          </button>
        )}
      </div>

      {error && (
        <div className="alert alert-error">
          <p>{error}</p>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {phase !== PHASE.IDLE && <StatsCards session={session} />}

      {phase === PHASE.IDLE && (
        <DifficultySelector onSelect={handleStartSession} />
      )}

      {phase === PHASE.LOADING && (
        <LoadingOverlay message="Loading question…" />
      )}

      {phase === PHASE.EVALUATING && (
        <LoadingOverlay message="AI is evaluating your answer…" />
      )}

      {(phase === PHASE.ANSWERING || phase === PHASE.FEEDBACK) &&
        question && (
          <div className="question-section">
            <div className="question-section-header">
              <div />
              <div className="diff-dropdown" ref={diffMenuRef}>
                <button
                  className="btn-text-link"
                  onClick={() => setShowDiffMenu((v) => !v)}
                >
                  Change Difficulty
                </button>
                {showDiffMenu && (
                  <div className="diff-menu">
                    <span className="diff-menu-title">Difficulty</span>
                    {['easy', 'medium', 'hard'].map((lvl) => (
                      <button
                        key={lvl}
                        className={`diff-menu-item${
                          session.difficulty === lvl ? ' active' : ''
                        }`}
                        onClick={() => handleChangeDifficulty(lvl)}
                      >
                        {lvl.charAt(0).toUpperCase() + lvl.slice(1)}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <QuestionCard question={question} />
          </div>
        )}

      {phase === PHASE.ANSWERING && (
        <AnswerCard onSubmit={handleSubmitAnswer} onSkip={handleSkip} />
      )}

      {phase === PHASE.FEEDBACK && feedback && (
        <FeedbackPanel feedback={feedback} onNext={handleNextQuestion} />
      )}

      <style>{`
        /* High-End SaaS Practice Page Standards */
        .practice-page {
          font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
          background: #F8FAFC;
          min-height: 100vh;
          padding: 16px;
        }

        /* Clean White Question Cards */
        .question-section {
          max-width: 800px;
          margin: 0 auto;
          background: white;
          border-radius: 12px;
          padding: 24px;
          border: 1px solid #E2E8F0;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        .question-section-header {
          display: flex;
          justify-content: flex-end;
          align-items: center;
          margin-bottom: 1rem;
        }

        /* Modern Input Fields with 2px Blue Focus Ring */
        textarea:focus, input:focus, select:focus {
          outline: none;
          border-color: #007bff;
          box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
          transition: all 0.3s ease;
        }

        textarea, input, select {
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          padding: 12px 16px;
          font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
          font-size: 1rem;
          line-height: 1.6;
          background: white;
          transition: all 0.3s ease;
        }

        /* Enhanced Typography for Readability */
        .question-section p, .question-section div {
          line-height: 1.6;
          font-size: 1.1rem;
          color: #1a202c;
          font-weight: 400;
        }

        /* Modern Submit Buttons */
        .btn-primary {
          background: #007bff;
          color: white;
          border: none;
          padding: 12px 24px;
          border-radius: 12px;
          font-weight: 600;
          transition: all 0.3s ease;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        .btn-primary:hover {
          background: #0056b3;
          transform: translateY(-2px);
          box-shadow: 0 8px 12px -1px rgba(0, 0, 0, 0.15);
        }

        .diff-dropdown {
          position: relative;
        }

        .btn-text-link {
          background: none;
          border: none;
          color: #64748b;
          font-size: 0.9rem;
          cursor: pointer;
          padding: 8px 12px;
          border-radius: 12px;
          transition: all 0.3s ease;
          font-weight: 500;
        }

        .btn-text-link:hover {
          color: #007bff;
          background: rgba(0, 123, 255, 0.1);
        }

        .diff-menu {
          position: absolute;
          right: 0;
          top: calc(100% + 8px);
          background: white;
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          padding: 8px 0;
          min-width: 150px;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
          z-index: 100;
        }

        .diff-menu-title {
          display: block;
          padding: 8px 16px;
          font-size: 0.75rem;
          text-transform: uppercase;
          color: #6c757d;
          letter-spacing: 0.05em;
          font-weight: 600;
        }

        .diff-menu-item {
          display: block;
          width: 100%;
          text-align: left;
          padding: 10px 16px;
          background: none;
          border: none;
          color: #2c3e50;
          font-size: 0.9rem;
          cursor: pointer;
          transition: all 0.3s ease;
        }

        .diff-menu-item:hover {
          background: rgba(0, 123, 255, 0.1);
          color: #007bff;
        }

        .diff-menu-item.active {
          background: rgba(0, 123, 255, 0.15);
          color: #007bff;
          font-weight: 600;
        }

        /* Responsive Design */
        @media (max-width: 768px) {
          .practice-page {
            padding: 12px;
          }

          .question-section {
            padding: 16px;
            margin: 0 8px;
          }

          .question-section p, .question-section div {
            font-size: 1rem;
          }
        }
      `}</style>
    </div>
  )
}
