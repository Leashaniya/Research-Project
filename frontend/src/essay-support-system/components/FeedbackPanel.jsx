import { useState } from 'react';
import {
  LuChevronRight,
  LuCircleCheck,
  LuTriangleAlert,
  LuLightbulb,
  LuBookOpen,
  LuBrain,
} from 'react-icons/lu';
import { capitalize } from '../utils/helpers';
import api from '../api/api';

export default function FeedbackPanel({ feedback, onNext }) {
  const [practiceAnswers, setPracticeAnswers] = useState({});
  const [submittedQuestions, setSubmittedQuestions] = useState(new Set());
  const [individualResults, setIndividualResults] = useState({});
  const [isEvaluating, setIsEvaluating] = useState(false);

  if (!feedback) return null;

  const fb = feedback.feedback || {};
  const recs = feedback.study_recommendations || [];
  const nextDiff = feedback.next_difficulty;
  const practiceQuestions = feedback.practice_questions || [];

  const handlePracticeAnswerChange = (questionIndex, answer) => {
    setPracticeAnswers(prev => ({
      ...prev,
      [questionIndex]: answer
    }));
  };

  const evaluateIndividualAnswer = async (questionIndex) => {
    setIsEvaluating(true);
    
    try {
      // Prepare evaluation payload for single answer
      const evaluationPayload = {
        practice_answers: { 0: practiceAnswers[questionIndex] },
        practice_questions: [practiceQuestions[questionIndex]],
        original_feedback: feedback,
        topic: feedback.topic || 'General'
      };
      
      console.log(`🔍 Evaluating answer ${questionIndex + 1}:`, evaluationPayload);
      
      // Call evaluation API
      const response = await api.evaluatePracticeAnswers(evaluationPayload);
      
      console.log(`✅ Evaluation result for answer ${questionIndex + 1}:`, response);
      
      // Store individual result
      setIndividualResults(prev => ({
        ...prev,
        [questionIndex]: response
      }));
      
    } catch (error) {
      console.error(`❌ Evaluation failed for answer ${questionIndex + 1}:`, error);
      // Set fallback result
      setIndividualResults(prev => ({
        ...prev,
        [questionIndex]: {
          correct_answers: 0,
          total_answers: 1,
          question_results: [{
            question_number: questionIndex + 1,
            correct: false,
            feedback: "Evaluation failed. Please try again."
          }]
        }
      }));
    } finally {
      setIsEvaluating(false);
    }
  };

  const handlePracticeSubmit = async (questionIndex) => {
    setSubmittedQuestions(prev => new Set([...prev, questionIndex]));
    
    // Evaluate this answer immediately
    await evaluateIndividualAnswer(questionIndex);
    
    // Check if all questions have been submitted for overall evaluation
    const totalQuestions = practiceQuestions.length;
    const submittedCount = submittedQuestions.size + 1;
    
    if (submittedCount === totalQuestions) {
      await evaluateAllAnswers();
    }
  };

  const evaluateAllAnswers = async () => {
    setIsEvaluating(true);
    
    try {
      // Prepare evaluation payload for all answers
      const evaluationPayload = {
        practice_answers: practiceAnswers,
        practice_questions: practiceQuestions,
        original_feedback: feedback,
        topic: feedback.topic || 'General'
      };
      
      console.log('� Evaluating all answers for final result:', evaluationPayload);
      
      // Call evaluation API
      const response = await api.evaluatePracticeAnswers(evaluationPayload);
      
      console.log('✅ Final evaluation result:', response);
      
      // Update individual results with final evaluation
      setIndividualResults(prev => {
        const updated = { ...prev };
        response.question_results?.forEach((result, index) => {
          updated[index] = {
            ...updated[index],
            ...response,
            question_results: [result]
          };
        });
        return updated;
      });
      
    } catch (error) {
      console.error('❌ Final evaluation failed:', error);
    } finally {
      setIsEvaluating(false);
    }
  };

  return (
    <div className="feedback-panel card">
      {/* Feedback sections */}
      <div className="fb-sections">
        {fb.strengths && (
          <div className="fb-section fb-strengths">
            <h4><LuCircleCheck size={16} /> Strengths</h4>
            <p>{fb.strengths}</p>
          </div>
        )}
        {fb.weaknesses && (
          <div className="fb-section fb-weaknesses">
            <h4><LuTriangleAlert size={16} /> Weaknesses</h4>
            <p>{fb.weaknesses}</p>
          </div>
        )}
        {fb.improvements && (
          <div className="fb-section fb-improvements">
            <h4><LuLightbulb size={16} /> Improvements</h4>
            <p>{fb.improvements}</p>
          </div>
        )}
      </div>

      {/* Study recommendations */}
      {recs.length > 0 && (
        <div className="fb-recs">
          <h4><LuBookOpen size={16} /> Study Recommendations</h4>
          <ul>
            {recs.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Practice questions from n8n */}
      {practiceQuestions.length > 0 && (
        <div className="fb-practice">
          <h4><LuBrain size={16} /> Practice Questions</h4>
          <p>Based on your answer, try these practice questions to improve:</p>
          
          {/* Overall Progress Summary */}
          {Object.keys(individualResults).length > 0 && (
            <div className="overall-progress">
              <h6>Overall Progress:</h6>
              <div className="progress-summary">
                <span className="submitted-count">
                  Submitted: {Object.keys(individualResults).length}/{practiceQuestions.length}
                </span>
                <span className="correct-count">
                  Correct: {Object.values(individualResults).filter(r => r.question_results?.[0]?.correct).length}
                </span>
                <span className="wrong-count">
                  Wrong: {Object.values(individualResults).filter(r => !r.question_results?.[0]?.correct).length}
                </span>
              </div>
            </div>
          )}

          {/* Practice Questions List */}
          <div className="practice-questions-list">
            {practiceQuestions.map((question, index) => {
              const result = individualResults[index];
              const questionResult = result?.question_results?.[0];
              const isCorrect = questionResult?.correct || false;
              const isSubmitted = submittedQuestions.has(index);
              const isEvaluatingThis = isEvaluating && !result && isSubmitted;
              
              return (
                <div key={index} className="practice-question-item">
                  <div className="practice-question-text">
                    <span className="question-number">{index + 1}.</span>
                    {question}
                  </div>
                  
                  <div className="practice-answer-area">
                    <textarea
                      value={practiceAnswers[index] || ''}
                      onChange={(e) => handlePracticeAnswerChange(index, e.target.value)}
                      placeholder="Enter your answer here..."
                      rows={3}
                      disabled={isSubmitted}
                    />
                    
                    {!isSubmitted ? (
                      <button 
                        className="btn btn-primary btn-sm"
                        onClick={() => handlePracticeSubmit(index)}
                        disabled={!practiceAnswers[index] || practiceAnswers[index].trim().length === 0}
                      >
                        Submit
                      </button>
                    ) : (
                      <div className="submitted-indicator">
                        <LuCircleCheck size={16} /> Submitted
                      </div>
                    )}
                  </div>

                  {/* Individual Evaluation Result */}
                  {isEvaluatingThis && (
                    <div className="evaluation-indicator">
                      <p>⏳ Evaluating your answer...</p>
                    </div>
                  )}

                  {result && questionResult && (
                    <div className={`individual-result ${isCorrect ? 'correct' : 'wrong'}`}>
                      <div className="result-header">
                        <span className="result-badge">
                          {isCorrect ? '✅ Correct' : '❌ Wrong'}
                        </span>
                      </div>
                      
                      <div className="student-answer">
                        <strong>Your answer:</strong> {practiceAnswers[index] || 'No answer provided'}
                      </div>
                      
                      {questionResult.feedback && (
                        <div className="answer-feedback">
                          <strong>Feedback:</strong> {questionResult.feedback}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Final Summary when all questions are submitted */}
          {Object.keys(individualResults).length === practiceQuestions.length && practiceQuestions.length > 0 && (
            <div className="final-summary">
              <h6>Final Evaluation Summary:</h6>
              {(() => {
                const totalCorrect = Object.values(individualResults).filter(r => r.question_results?.[0]?.correct).length;
                const passed = totalCorrect >= 3;
                const firstResult = Object.values(individualResults)[0];
                
                return (
                  <>
                    <div className={`final-result ${passed ? 'passed' : 'failed'}`}>
                      <h5>
                        {passed ? (
                          <><LuCircleCheck size={16} /> Evaluation Passed!</>
                        ) : (
                          <><LuTriangleAlert size={16} /> Needs More Practice</>
                        )}
                      </h5>
                      <p>
                        You got {totalCorrect} out of {practiceQuestions.length} correct.
                        {passed 
                          ? ' Great job! Moving to next difficulty level.' 
                          : ' Keep practicing to improve your understanding.'
                        }
                      </p>
                    </div>
                    
                    {!passed && firstResult?.additional_questions && (
                      <div className="additional-questions">
                        <h6>Additional Practice Questions:</h6>
                        <ul>
                          {firstResult.additional_questions.map((q, i) => (
                            <li key={i}>{q}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}
        </div>
      )}

      {/* Next difficulty & continue */}
      <div className="fb-actions">
        {nextDiff && (
          <span className="fb-next-badge">
            Next: <strong>{capitalize(nextDiff)}</strong>
          </span>
        )}
        <button className="btn btn-primary" onClick={onNext}>
          Next Question <LuChevronRight size={16} />
        </button>
      </div>

      <style>{`
        .feedback-panel { margin-top: 1.25rem; }

        .fb-sections {
          display: flex;
          flex-direction: column;
          gap: 1rem;
          margin-bottom: 1.25rem;
        }
        .fb-section {
          padding: 0.85rem 1rem;
          border-radius: var(--radius-sm);
          border-left: 3px solid;
        }
        .fb-section h4 {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.85rem;
          font-weight: 600;
          margin-bottom: 0.35rem;
        }
        .fb-section p { font-size: 0.9rem; line-height: 1.5; }

        .fb-strengths     { background: rgba(16,185,129,0.08); border-color: var(--success); }
        .fb-strengths h4  { color: var(--success); }
        .fb-weaknesses    { background: rgba(239,68,68,0.08); border-color: var(--danger); }
        .fb-weaknesses h4 { color: var(--danger); }
        .fb-improvements    { background: rgba(245,158,11,0.08); border-color: var(--warning); }
        .fb-improvements h4 { color: var(--warning); }

        .fb-recs {
          padding: 1rem;
          background: rgba(42,90,148,0.06);
          border-radius: var(--radius-sm);
          margin-bottom: 1.25rem;
        }
        .fb-recs h4 {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.85rem;
          color: var(--info);
          margin-bottom: 0.5rem;
        }
        .fb-recs ul { list-style: disc; padding-left: 1.25rem; }
        .fb-recs li { font-size: 0.88rem; margin-bottom: 0.25rem; }

        .fb-practice {
          padding: 1rem;
          background: rgba(139,92,246,0.08);
          border-radius: var(--radius-sm);
          margin-bottom: 1.25rem;
          border-left: 3px solid var(--primary);
        }
        .fb-practice h4 {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.85rem;
          color: var(--primary);
          margin-bottom: 0.5rem;
        }
        .fb-practice p {
          font-size: 0.88rem;
          color: var(--text-muted);
          margin-bottom: 1rem;
        }
        .practice-questions-list {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }
        .practice-question-item {
          background: var(--surface);
          border-radius: var(--radius-sm);
          padding: 1rem;
          border: 1px solid var(--border);
        }
        .practice-question-text {
          font-size: 0.9rem;
          line-height: 1.5;
          margin-bottom: 0.75rem;
          color: var(--text);
        }
        .question-number {
          font-weight: 600;
          color: var(--primary);
          margin-right: 0.5rem;
        }
        .practice-answer-area {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .practice-answer-area textarea {
          width: 100%;
          background: var(--bg);
          color: var(--text);
          border: 1px solid var(--border);
          border-radius: var(--radius-sm);
          padding: 0.75rem;
          resize: vertical;
          font-size: 0.85rem;
          line-height: 1.4;
          font-family: inherit;
        }
        .practice-answer-area textarea:focus {
          outline: none;
          border-color: var(--primary);
          box-shadow: 0 0 0 2px rgba(139,92,246,0.15);
        }
        .practice-answer-area textarea:disabled {
          background: var(--border);
          color: var(--text-muted);
          cursor: not-allowed;
        }
        .btn-sm {
          padding: 0.5rem 1rem;
          font-size: 0.85rem;
          align-self: flex-start;
        }
        .submitted-indicator {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          color: #10b981;
          font-size: 0.85rem;
          font-weight: 500;
          align-self: flex-start;
        }

        .evaluation-result {
          padding: 1rem;
          border-radius: var(--radius-sm);
          margin-bottom: 1rem;
          border-left: 3px solid;
        }
        .evaluation-result.passed {
          background: rgba(16,185,129,0.08);
          border-color: var(--success);
        }
        .evaluation-result.failed {
          background: rgba(239,68,68,0.08);
          border-color: var(--danger);
        }
        .evaluation-result h5 {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.9rem;
          font-weight: 600;
          margin-bottom: 0.5rem;
        }
        .evaluation-result.passed h5 {
          color: var(--success);
        }
        .evaluation-result.failed h5 {
          color: var(--danger);
        }
        .evaluation-result p {
          font-size: 0.85rem;
          line-height: 1.4;
          margin-bottom: 0.75rem;
        }
        .additional-questions {
          margin-top: 1rem;
        }
        .additional-questions h6 {
          font-size: 0.85rem;
          font-weight: 600;
          color: var(--text);
          margin-bottom: 0.5rem;
        }
        .additional-questions ul {
          list-style: decimal;
          padding-left: 1.25rem;
        }
        .additional-questions li {
          font-size: 0.85rem;
          margin-bottom: 0.25rem;
          line-height: 1.4;
        }
        .evaluation-loading {
          text-align: center;
          padding: 2rem;
          color: var(--text-muted);
        }
        .evaluation-loading p {
          font-size: 0.9rem;
        }

        .answer-results {
          margin-top: 1rem;
        }
        .answer-results h6 {
          font-size: 0.9rem;
          font-weight: 600;
          color: var(--text);
          margin-bottom: 0.75rem;
        }
        .results-summary {
          display: flex;
          gap: 1rem;
          margin-bottom: 1rem;
          padding: 0.75rem;
          background: var(--bg);
          border-radius: var(--radius-sm);
          border: 1px solid var(--border);
        }
        .correct-count {
          color: #10b981;
          font-weight: 600;
          font-size: 0.9rem;
        }
        .wrong-count {
          color: #ef4444;
          font-weight: 600;
          font-size: 0.9rem;
        }
        .question-result {
          margin-bottom: 1rem;
          padding: 1rem;
          border-radius: var(--radius-sm);
          border-left: 4px solid;
        }
        .question-result.correct {
          background: rgba(16,185,129,0.08);
          border-left-color: #10b981;
        }
        .question-result.wrong {
          background: rgba(239,68,68,0.08);
          border-left-color: #ef4444;
        }
        .question-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.5rem;
        }
        .question-number {
          font-weight: 600;
          color: var(--text);
        }
        .result-badge {
          font-size: 0.85rem;
          font-weight: 600;
          padding: 0.25rem 0.5rem;
          border-radius: var(--radius-sm);
        }
        .question-result.correct .result-badge {
          background: #10b981;
          color: white;
        }
        .question-result.wrong .result-badge {
          background: #ef4444;
          color: white;
        }
        .question-text {
          font-size: 0.9rem;
          line-height: 1.4;
          margin-bottom: 0.5rem;
          color: var(--text);
        }
        .student-answer {
          font-size: 0.85rem;
          margin-bottom: 0.5rem;
          padding: 0.5rem;
          background: var(--surface);
          border-radius: var(--radius-sm);
          border: 1px solid var(--border);
        }
        .answer-feedback {
          font-size: 0.85rem;
          padding: 0.5rem;
          background: var(--bg);
          border-radius: var(--radius-sm);
          border-left: 3px solid var(--primary);
        }
        .answer-feedback strong {
          color: var(--primary);
        }

        .overall-progress {
          margin-bottom: 1.5rem;
          padding: 1rem;
          background: var(--surface);
          border-radius: var(--radius-sm);
          border: 1px solid var(--border);
        }
        .overall-progress h6 {
          font-size: 0.9rem;
          font-weight: 600;
          color: var(--text);
          margin-bottom: 0.75rem;
        }
        .progress-summary {
          display: flex;
          gap: 1.5rem;
          flex-wrap: wrap;
        }
        .progress-summary span {
          font-size: 0.85rem;
          font-weight: 500;
        }
        .submitted-count {
          color: var(--text-muted);
        }
        .correct-count {
          color: #10b981;
        }
        .wrong-count {
          color: #ef4444;
        }

        .individual-result {
          margin-top: 1rem;
          padding: 1rem;
          border-radius: var(--radius-sm);
          border-left: 4px solid;
        }
        .individual-result.correct {
          background: rgba(16,185,129,0.08);
          border-left-color: #10b981;
        }
        .individual-result.wrong {
          background: rgba(239,68,68,0.08);
          border-left-color: #ef4444;
        }
        .result-header {
          margin-bottom: 0.75rem;
        }
        .result-badge {
          font-size: 0.85rem;
          font-weight: 600;
          padding: 0.25rem 0.5rem;
          border-radius: var(--radius-sm);
        }
        .individual-result.correct .result-badge {
          background: #10b981;
          color: white;
        }
        .individual-result.wrong .result-badge {
          background: #ef4444;
          color: white;
        }

        .evaluation-indicator {
          margin-top: 0.75rem;
          padding: 0.75rem;
          text-align: center;
          background: var(--surface);
          border-radius: var(--radius-sm);
          border: 1px solid var(--border);
        }
        .evaluation-indicator p {
          font-size: 0.85rem;
          color: var(--text-muted);
          margin: 0;
        }

        .final-summary {
          margin-top: 2rem;
          padding: 1.5rem;
          background: var(--surface);
          border-radius: var(--radius-sm);
          border: 2px solid var(--border);
        }
        .final-summary h6 {
          font-size: 1rem;
          font-weight: 600;
          color: var(--text);
          margin-bottom: 1rem;
        }
        .final-result {
          padding: 1rem;
          border-radius: var(--radius-sm);
          margin-bottom: 1rem;
        }
        .final-result.passed {
          background: rgba(16,185,129,0.08);
          border-left: 4px solid #10b981;
        }
        .final-result.failed {
          background: rgba(239,68,68,0.08);
          border-left: 4px solid #ef4444;
        }
        .final-result h5 {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.95rem;
          font-weight: 600;
          margin-bottom: 0.5rem;
        }
        .final-result.passed h5 {
          color: #10b981;
        }
        .final-result.failed h5 {
          color: #ef4444;
        }
        .final-result p {
          font-size: 0.9rem;
          line-height: 1.4;
          margin: 0;
        }

        .fb-actions {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .fb-next-badge {
          font-size: 0.85rem;
          color: var(--text-muted);
        }
      `}</style>
    </div>
  );
}
