import { useState, useRef, useEffect } from 'react';
import { LuSend, LuSkipForward } from 'react-icons/lu';

export default function AnswerCard({ onSubmit, onSkip }) {
  const [answer, setAnswer] = useState('');
  const textareaRef = useRef(null);
  const wordCount = answer.trim() ? answer.trim().split(/\s+/).length : 0;

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleKeyDown = (e) => {
    if (e.ctrlKey && e.key === 'Enter' && answer.trim()) {
      onSubmit(answer.trim());
    }
  };

  const handleSubmit = () => {
    if (answer.trim()) {
      onSubmit(answer.trim());
    }
  };

  return (
    <div className="answer-card card">
      <h3 className="answer-heading">Your Answer</h3>

      <textarea
        ref={textareaRef}
        className="answer-textarea"
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type your answer here… (Ctrl + Enter to submit)"
        rows={8}
      />

      <div className="answer-footer">
        <span className="word-count">{wordCount} word{wordCount !== 1 ? 's' : ''}</span>

        <div className="answer-actions">
          {onSkip && (
            <button className="btn btn-secondary btn-sm" onClick={onSkip}>
              <LuSkipForward size={14} /> Skip
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={!answer.trim()}
          >
            <LuSend size={16} /> Submit Answer
          </button>
        </div>
      </div>

      <style>{`
        .answer-heading {
          font-size: 1rem;
          font-weight: 600;
          margin-bottom: 0.75rem;
        }
        .answer-textarea {
          width: 100%;
          background: var(--bg);
          color: var(--text);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          padding: 1rem;
          resize: vertical;
          font-size: 0.95rem;
          line-height: 1.6;
          transition: border-color 0.2s;
        }
        .answer-textarea:focus {
          outline: none;
          border-color: var(--primary-500);
          box-shadow: 0 0 0 3px rgba(139,92,246,0.15);
        }
        .answer-textarea::placeholder {
          color: var(--text-muted);
        }
        .answer-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-top: 0.75rem;
        }
        .word-count {
          font-size: 0.8rem;
          color: var(--text-muted);
        }
        .answer-actions {
          display: flex;
          gap: 0.5rem;
        }
      `}</style>
    </div>
  );
}
