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
      <div className="answer-header">
        <h3 className="answer-heading">Your Answer</h3>
        <div className="answer-hint">
          <span className="keyboard-shortcut">Ctrl + Enter</span> to submit
        </div>
      </div>

      <div className="answer-textarea-wrapper">
        <textarea
          ref={textareaRef}
          className="answer-textarea"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your answer here…"
          rows={8}
        />
        <div className="char-counter">
          {answer.length} characters
        </div>
      </div>

      <div className="answer-footer">
        <div className="word-count-container">
          <span className="word-count">{wordCount} word{wordCount !== 1 ? 's' : ''}</span>
          <span className="word-count-divider">•</span>
          <span className="word-hint">Minimum 5 words recommended</span>
        </div>

        <div className="answer-actions">
          {onSkip && (
            <button className="btn btn-secondary btn-sm" onClick={onSkip}>
              <LuSkipForward size={14} /> Skip
            </button>
          )}
          <button
            className={`btn btn-primary ${!answer.trim() ? 'btn-disabled' : ''}`}
            onClick={handleSubmit}
            disabled={!answer.trim()}
          >
            <LuSend size={16} /> Submit Answer
          </button>
        </div>
      </div>

      <style>{`
        .answer-card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 1.5rem;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
          transition: all 0.3s ease;
        }

        .answer-card:hover {
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
        }

        .answer-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }

        .answer-heading {
          font-size: 1.25rem;
          font-weight: 700;
          color: var(--text);
          margin: 0;
          letter-spacing: -0.01em;
        }

        .answer-hint {
          font-size: 0.8rem;
          color: var(--text-muted);
          font-weight: 500;
        }

        .keyboard-shortcut {
          background: var(--primary-50);
          color: var(--primary);
          padding: 0.25rem 0.5rem;
          border-radius: 4px;
          font-family: monospace;
          font-weight: 600;
        }

        .answer-textarea-wrapper {
          position: relative;
          margin-bottom: 1rem;
        }

        .answer-textarea {
          width: 100%;
          background: var(--bg);
          color: var(--text);
          border: 2px solid var(--border);
          border-radius: 12px;
          padding: 1rem 1rem 2.5rem 1rem;
          resize: vertical;
          font-size: 1rem;
          line-height: 1.6;
          font-family: inherit;
          transition: all 0.3s ease;
        }

        .answer-textarea:focus {
          outline: none;
          border-color: var(--primary);
          box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.1);
        }

        .answer-textarea::placeholder {
          color: var(--text-muted);
          font-style: italic;
        }

        .char-counter {
          position: absolute;
          bottom: 0.75rem;
          right: 1rem;
          font-size: 0.75rem;
          color: var(--text-muted);
          font-weight: 500;
          background: var(--bg);
          padding: 0.25rem 0.5rem;
          border-radius: 4px;
        }

        .answer-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-top: 0.5rem;
          padding-top: 1rem;
          border-top: 1px solid var(--border);
        }

        .word-count-container {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        .word-count {
          font-size: 0.85rem;
          color: var(--text);
          font-weight: 600;
        }

        .word-count-divider {
          color: var(--border);
          font-size: 0.75rem;
        }

        .word-hint {
          font-size: 0.8rem;
          color: var(--text-muted);
        }

        .answer-actions {
          display: flex;
          gap: 0.75rem;
        }

        .answer-actions .btn {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.75rem 1.25rem;
          border-radius: 10px;
          font-weight: 600;
          font-size: 0.9rem;
          transition: all 0.3s ease;
        }

        .answer-actions .btn:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }

        .answer-actions .btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          transform: none;
        }

        .answer-actions .btn-secondary {
          background: var(--surface);
          border: 1px solid var(--border);
          color: var(--text);
        }

        .answer-actions .btn-secondary:hover {
          background: var(--primary-50);
          border-color: var(--primary-200);
          color: var(--primary);
        }

        .answer-actions .btn-primary {
          background: linear-gradient(135deg, var(--primary), var(--primary-600));
          border: none;
          color: white;
          box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }

        .answer-actions .btn-primary:hover:not(:disabled) {
          background: linear-gradient(135deg, var(--primary-600), var(--primary-700));
          box-shadow: 0 6px 16px rgba(37, 99, 235, 0.4);
        }

        .btn-disabled {
          background: var(--border) !important;
          box-shadow: none !important;
        }

        /* Responsive Design */
        @media (max-width: 768px) {
          .answer-card {
            padding: 1.25rem;
          }

          .answer-header {
            flex-direction: column;
            align-items: flex-start;
            gap: 0.5rem;
          }

          .answer-heading {
            font-size: 1.1rem;
          }

          .answer-textarea {
            padding: 0.875rem 0.875rem 2.25rem 0.875rem;
            font-size: 0.95rem;
          }

          .answer-footer {
            flex-direction: column;
            gap: 1rem;
            align-items: stretch;
          }

          .word-count-container {
            justify-content: center;
          }

          .answer-actions {
            justify-content: stretch;
          }

          .answer-actions .btn {
            flex: 1;
            justify-content: center;
          }
        }

        @media (max-width: 480px) {
          .answer-card {
            padding: 1rem;
          }

          .answer-textarea {
            rows: 6;
          }

          .answer-actions {
            flex-direction: column;
          }
        }
      `}</style>
    </div>
  );
}
