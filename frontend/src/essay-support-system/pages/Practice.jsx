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
        .question-section-header {
          display: flex;
          justify-content: flex-end;
          align-items: center;
          margin-bottom: 0.25rem;
        }
        .diff-dropdown {
          position: relative;
        }
        .btn-text-link {
          background: none;
          border: none;
          color: var(--text-muted);
          font-size: 0.82rem;
          cursor: pointer;
          padding: 4px 0;
          transition: color 0.15s;
        }
        .btn-text-link:hover {
          color: var(--primary);
        }
        .diff-menu {
          position: absolute;
          right: 0;
          top: calc(100% + 6px);
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          padding: 6px 0;
          min-width: 150px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.35);
          z-index: 100;
        }
        .diff-menu-title {
          display: block;
          padding: 6px 14px;
          font-size: 0.7rem;
          text-transform: uppercase;
          color: var(--text-muted);
          letter-spacing: 0.05em;
        }
        .diff-menu-item {
          display: block;
          width: 100%;
          text-align: left;
          padding: 8px 14px;
          background: none;
          border: none;
          color: var(--text);
          font-size: 0.88rem;
          cursor: pointer;
          transition: background 0.12s;
        }
        .diff-menu-item:hover {
          background: var(--primary-50);
          color: var(--primary);
        }
        .diff-menu-item.active {
          color: var(--primary);
          font-weight: 600;
        }
      `}</style>
    </div>
  )
}
