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
  const [batchSubmitted, setBatchSubmitted] = useState(false);
  const [batchResult, setBatchResult] = useState(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [additionalPracticeAnswers, setAdditionalPracticeAnswers] = useState({});
  const [additionalBatchSubmitted, setAdditionalBatchSubmitted] = useState(false);
  const [additionalBatchResult, setAdditionalBatchResult] = useState(null);
  const [showAdditionalQuestions, setShowAdditionalQuestions] = useState(false);

  if (!feedback) return null;

  const fb = feedback.feedback || {};
  const recs = feedback.study_recommendations || [];
  const nextDiff = feedback.next_difficulty;
  const practiceQuestions = feedback.practice_questions || [];

  const handlePracticeAnswerChange = (questionIndex, answer) => {
    console.log(`🔄 [FRONTEND] Answer change for Question ${questionIndex + 1}:`, answer);
    console.log(`   - Previous state:`, practiceAnswers);
    
    setPracticeAnswers(prev => {
      const newState = {
        ...prev,
        [questionIndex]: answer
      };
      console.log(`   - New state:`, newState);
      console.log(`   - New state keys:`, Object.keys(newState));
      console.log(`   - New state values:`, Object.values(newState));
      return newState;
    });
  };

  const handleAdditionalPracticeAnswerChange = (questionIndex, answer) => {
    console.log(`🔄 [FRONTEND] Additional answer change for Question ${questionIndex + 1}:`, answer);
    
    setAdditionalPracticeAnswers(prev => ({
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

  const handleBatchSubmit = async () => {
    // Check if all questions have answers
    const unansweredQuestions = practiceQuestions.filter((_, index) => {
      const answer = practiceAnswers[index];
      return !answer || answer.trim().length === 0;
    });
    
    if (unansweredQuestions.length > 0) {
      alert(`Please answer all questions before submitting. You have ${unansweredQuestions.length} unanswered question(s).`);
      return;
    }
    
    setIsEvaluating(true);
    
    try {
      // Prepare batch submission payload
      console.log('🔍 [FRONTEND BATCH] Preparing payload with current state:');
      console.log('   - practiceAnswers type:', typeof practiceAnswers);
      console.log('   - practiceAnswers:', practiceAnswers);
      console.log('   - practiceAnswers keys:', Object.keys(practiceAnswers));
      console.log('   - practiceAnswers values:', Object.values(practiceAnswers));
      console.log('   - practiceQuestions type:', typeof practiceQuestions);
      console.log('   - practiceQuestions:', practiceQuestions);
      console.log('   - practiceQuestions length:', practiceQuestions.length);
      
      const batchPayload = {
        answers: practiceAnswers,
        questions: practiceQuestions,
        topic: feedback.topic || 'General',
        difficulty: feedback.difficulty || 'easy',
        batch_mode: true
      };
      
      // Frontend debugging logs
      console.log('� [FRONTEND BATCH] Starting batch submission...');
      console.log('📥 [FRONTEND BATCH] INPUT PAYLOAD:');
      console.log('   - Answers:', practiceAnswers);
      console.log('   - Questions:', practiceQuestions);
      console.log('   - Topic:', feedback.topic || 'General');
      console.log('   - Difficulty:', feedback.difficulty || 'easy');
      console.log('   - Batch Mode:', true);
      console.log('   - Full Payload:', batchPayload);
      
      // Call batch submit API
      console.log('🌐 [FRONTEND BATCH] Calling API.submitAnswer...');
      const response = await api.submitAnswer(batchPayload);
      
      // Frontend response debugging logs
      console.log('📤 [FRONTEND BATCH] API RESPONSE:');
      console.log('   - Full Response:', response);
      console.log('   - Status:', response.status);
      console.log('   - Correct Answers:', response.correct_answers);
      console.log('   - Total Answers:', response.total_answers);
      console.log('   - Score:', response.score);
      console.log('   - Is Correct:', response.is_correct);
      console.log('   - Feedback:', response.feedback);
      console.log('   - Next Difficulty:', response.next_difficulty);
      console.log('   - Question Results:', response.question_results);
      console.log('   - Batch Mode:', response.batch_mode);
      
      setBatchResult(response);
      setBatchSubmitted(true);
      
      // If student failed and there are additional questions, show them
      if (response.status === 'FAILED' && response.additional_questions && response.additional_questions.length > 0) {
        console.log('📚 [FRONTEND] Student failed, showing additional practice questions');
        setShowAdditionalQuestions(true);
      }
      
    } catch (error) {
      console.error('❌ [FRONTEND BATCH] Batch submission failed:', error);
      console.error('   - Error Message:', error.message);
      console.error('   - Error Stack:', error.stack);
      alert('Failed to submit answers. Please try again.');
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleAdditionalBatchSubmit = async () => {
    const additionalQuestions = batchResult?.additional_questions || [];
    
    // Check if all additional questions have answers
    const unansweredQuestions = additionalQuestions.filter((_, index) => {
      const answer = additionalPracticeAnswers[index];
      return !answer || answer.trim().length === 0;
    });
    
    if (unansweredQuestions.length > 0) {
      alert(`Please answer all additional questions before submitting. You have ${unansweredQuestions.length} unanswered question(s).`);
      return;
    }
    
    setIsEvaluating(true);
    
    try {
      // Prepare additional batch submission payload
      const additionalBatchPayload = {
        answers: additionalPracticeAnswers,
        questions: additionalQuestions,
        topic: feedback.topic || 'General',
        difficulty: feedback.difficulty || 'easy',
        batch_mode: true,
        additional_round: true  // Flag to indicate this is additional practice round
      };
      
      console.log('🔍 [FRONTEND ADDITIONAL BATCH] Submitting additional practice answers...');
      
      // Call batch submit API
      const response = await api.submitAnswer(additionalBatchPayload);
      
      console.log('📤 [FRONTEND ADDITIONAL BATCH] API RESPONSE:', response);
      
      setAdditionalBatchResult(response);
      setAdditionalBatchSubmitted(true);
      
    } catch (error) {
      console.error('❌ [FRONTEND ADDITIONAL BATCH] Submission failed:', error);
      alert('Failed to submit additional answers. Please try again.');
    } finally {
      setIsEvaluating(false);
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

          {/* Practice Questions List */}
          <div className="practice-questions-list">
            {practiceQuestions.map((question, index) => {
              console.log(`📝 [FRONTEND] Rendering Question ${index + 1}:`, question);
              console.log(`   - Current answer for index ${index}:`, practiceAnswers[index]);
              console.log(`   - All practiceAnswers:`, practiceAnswers);
              
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
                      disabled={batchSubmitted}
                    />
                  </div>

                  {/* Individual Result after Batch Submission */}
                  {batchSubmitted && batchResult && batchResult.question_results && batchResult.question_results[index] && (
                    <div className={`individual-result ${batchResult.question_results[index].correct ? 'correct' : 'wrong'}`}>
                      <div className="result-header">
                        <span className="result-badge">
                          {batchResult.question_results[index].correct ? '✅ Correct' : '❌ Wrong'}
                        </span>
                      </div>
                      
                      <div className="student-answer">
                        <strong>Your answer:</strong> {practiceAnswers[index] || 'No answer provided'}
                      </div>
                      
                      {batchResult.question_results[index].feedback && (
                        <div className="answer-feedback">
                          <strong>Feedback:</strong> {batchResult.question_results[index].feedback}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Submit All Button */}
          {!batchSubmitted && (
            <div className="submit-all-section">
              <button 
                className="btn btn-primary submit-all-btn"
                onClick={handleBatchSubmit}
                disabled={isEvaluating || Object.keys(practiceAnswers).length < practiceQuestions.length || Object.values(practiceAnswers).some(answer => !answer || answer.trim().length === 0)}
              >
                {isEvaluating ? '⏳ Evaluating...' : '🚀 Submit All Answers'}
              </button>
              <p className="submit-all-hint">
                Complete all questions to submit for evaluation
              </p>
            </div>
          )}

          {/* Final Summary after Batch Submission */}
          {batchSubmitted && batchResult && (
            <div className="final-summary">
              <div className={`final-result ${batchResult.status === 'PASSED' ? 'passed' : 'failed'}`}>
                <div className="result-header">
                  {batchResult.status === 'PASSED' ? (
                    <div className="result-status passed">
                      <LuCircleCheck size={20} />
                      <h4>Excellent Work! 🎉</h4>
                    </div>
                  ) : (
                    <div className="result-status failed">
                      <LuTriangleAlert size={20} />
                      <h4>Needs More Practice ⚠️</h4>
                    </div>
                  )}
                </div>
                
                <div className="score-display">
                  <div className="score-numbers">
                    <span className="score-correct">{batchResult.correct_answers}</span>
                    <span className="score-divider">out of</span>
                    <span className="score-total">{batchResult.total_answers}</span>
                  </div>
                  <div className="score-label">questions answered correctly</div>
                  <div className="progress-bar-container">
                    <div className="progress-bar">
                      <div 
                        className="progress-fill" 
                        style={{ width: `${(batchResult.correct_answers / batchResult.total_answers) * 100}%` }}
                      ></div>
                    </div>
                    <div className="progress-text">
                      {Math.round((batchResult.correct_answers / batchResult.total_answers) * 100)}% Complete
                    </div>
                  </div>
                </div>
                
                <div className="result-message">
                  {batchResult.status === 'PASSED' ? (
                    <p>
                      Fantastic progress! You've mastered this level and are ready to move on to more challenging content. Your dedication is paying off!
                    </p>
                  ) : (
                    <p>
                      You answered {batchResult.correct_answers} out of {batchResult.total_answers} questions correctly. Keep practicing to strengthen your understanding and improve your performance. Every attempt brings you closer to mastery!
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Additional Practice Questions Section */}
          {showAdditionalQuestions && batchResult && batchResult.additional_questions && (
            <div className="additional-practice-section">
              <h4><LuBrain size={16} /> Additional Practice Questions</h4>
              <p>Here are 5 more practice questions to help you improve:</p>
              
              {/* Additional Practice Questions List */}
              <div className="practice-questions-list">
                {batchResult.additional_questions.map((question, index) => {
                  return (
                    <div key={index} className="practice-question-item">
                      <div className="practice-question-text">
                        <span className="question-number">{index + 1}.</span>
                        {question}
                      </div>
                      
                      <div className="practice-answer-area">
                        <textarea
                          value={additionalPracticeAnswers[index] || ''}
                          onChange={(e) => handleAdditionalPracticeAnswerChange(index, e.target.value)}
                          placeholder="Enter your answer here..."
                          rows={3}
                          disabled={additionalBatchSubmitted}
                        />
                      </div>

                      {/* Additional Individual Result after Batch Submission */}
                      {additionalBatchSubmitted && additionalBatchResult && additionalBatchResult.question_results && additionalBatchResult.question_results[index] && (
                        <div className={`individual-result ${additionalBatchResult.question_results[index].correct ? 'correct' : 'wrong'}`}>
                          <div className="result-header">
                            <span className="result-badge">
                              {additionalBatchResult.question_results[index].correct ? '✅ Correct' : '❌ Wrong'}
                            </span>
                          </div>
                          
                          <div className="student-answer">
                            <strong>Your answer:</strong> {additionalPracticeAnswers[index] || 'No answer provided'}
                          </div>
                          
                          {additionalBatchResult.question_results[index].feedback && (
                            <div className="answer-feedback">
                              <strong>Feedback:</strong> {additionalBatchResult.question_results[index].feedback}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Additional Submit All Button */}
              {!additionalBatchSubmitted && (
                <div className="submit-all-section">
                  <button 
                    className="btn btn-primary submit-all-btn"
                    onClick={handleAdditionalBatchSubmit}
                    disabled={isEvaluating || Object.keys(additionalPracticeAnswers).length < batchResult.additional_questions.length || Object.values(additionalPracticeAnswers).some(answer => !answer || answer.trim().length === 0)}
                  >
                    {isEvaluating ? '⏳ Evaluating...' : '🚀 Submit Additional Answers'}
                  </button>
                  <p className="submit-all-hint">
                    Complete all questions to submit for evaluation
                  </p>
                </div>
              )}

              {/* Additional Final Summary */}
              {additionalBatchSubmitted && additionalBatchResult && (
                <div className="final-summary">
                  <h6>Additional Practice Evaluation Summary:</h6>
                  <div className={`final-result ${additionalBatchResult.status === 'PASSED' ? 'passed' : 'failed'}`}>
                    <h5>
                      {additionalBatchResult.status === 'PASSED' ? (
                        <><LuCircleCheck size={16} /> Additional Practice Passed!</>
                      ) : (
                        <><LuTriangleAlert size={16} /> Keep Practicing!</>
                      )}
                    </h5>
                    <p>
                      You got {additionalBatchResult.correct_answers} out of {additionalBatchResult.total_answers} correct in the additional practice.
                      {additionalBatchResult.status === 'PASSED' 
                        ? ' Excellent improvement!' 
                        : ' Continue practicing to strengthen your understanding.'
                      }
                    </p>
                  </div>
                </div>
              )}
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
        }
        .final-result {
          padding: 2rem;
          border-radius: 16px;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
          backdrop-filter: blur(10px);
          border: 1px solid rgba(255, 255, 255, 0.1);
          text-align: center;
          position: relative;
          overflow: hidden;
        }
        .final-result::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          background: linear-gradient(90deg, rgba(255,255,255,0.3) 0%, rgba(255,255,255,0.1) 100%);
        }
        .final-result.passed {
          background: linear-gradient(135deg, #10b981 0%, #059669 100%);
          color: white;
        }
        .final-result.failed {
          background: linear-gradient(135deg, #60A5FA 0%, #3B82F6 100%);
          color: white;
        }
        
        .result-header {
          margin-bottom: 1.5rem;
        }
        .result-status {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0.75rem;
          margin-bottom: 0.5rem;
        }
        .result-status h4 {
          font-size: 1.5rem;
          font-weight: 700;
          margin: 0;
          letter-spacing: -0.025em;
        }
        
        .score-display {
          margin: 2rem 0;
          padding: 1.5rem;
          background: #EFF6FF;
          border-radius: 12px;
          border: 1px solid #BFDBFE;
        }
        .score-numbers {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          font-size: 2.5rem;
          font-weight: 800;
          margin-bottom: 0.5rem;
          line-height: 1;
        }
        .score-correct {
          color: #3B82F6;
          text-shadow: none;
        }
        .score-divider {
          font-size: 1.2rem;
          color: #374151;
          font-weight: 400;
        }
        .score-total {
          color: #374151;
        }
        .score-label {
          font-size: 0.9rem;
          color: #374151;
          margin-bottom: 0.5rem;
          font-weight: 500;
        }
        
        .progress-bar-container {
          margin-top: 1rem;
        }
        .progress-bar {
          width: 100%;
          height: 8px;
          background: #E5E7EB;
          border-radius: 4px;
          overflow: hidden;
          margin-bottom: 0.5rem;
        }
        .progress-fill {
          height: 100%;
          background: #3B82F6;
          border-radius: 4px;
          transition: width 0.3s ease;
        }
        .progress-text {
          font-size: 0.85rem;
          color: #374151;
          text-align: center;
          font-weight: 500;
        }
        
        .result-message {
          margin-top: 1.5rem;
        }
        .result-message p {
          font-size: 1rem;
          line-height: 1.7;
          margin: 0;
          opacity: 0.95;
          font-weight: 400;
        }
        .final-result p {
          font-size: 0.9rem;
          line-height: 1.4;
          margin: 0;
        }

        .submit-all-section {
          margin: 2rem 0;
          padding: 2rem;
          background: linear-gradient(135deg, rgba(37, 99, 235, 0.03), rgba(30, 64, 175, 0.02));
          border: 1px solid var(--primary-200);
          border-radius: 16px;
          text-align: center;
          position: relative;
          box-shadow: 0 4px 20px rgba(37, 99, 235, 0.08);
        }

        .submit-all-section::before {
          content: '';
          position: absolute;
          top: 0;
          left: 50%;
          transform: translateX(-50%);
          width: 60px;
          height: 3px;
          background: linear-gradient(90deg, var(--primary), var(--primary-600));
          border-radius: 0 0 3px 3px;
        }

        .submit-all-btn {
          padding: 1rem 2.5rem;
          font-size: 1.1rem;
          font-weight: 700;
          background: linear-gradient(135deg, var(--primary), var(--primary-600));
          color: white;
          border: none;
          border-radius: 12px;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          margin-bottom: 1rem;
          box-shadow: 0 4px 16px rgba(37, 99, 235, 0.3);
          letter-spacing: 0.02em;
        }

        .submit-all-btn:hover:not(:disabled) {
          background: linear-gradient(135deg, var(--primary-600), var(--primary-700));
          transform: translateY(-3px);
          box-shadow: 0 8px 24px rgba(37, 99, 235, 0.4);
        }

        .submit-all-btn:disabled {
          background: var(--border);
          color: var(--text-muted);
          cursor: not-allowed;
          transform: none;
          box-shadow: none;
        }

        .submit-all-hint {
          font-size: 0.9rem;
          color: var(--text-muted);
          margin: 0;
          line-height: 1.5;
          font-weight: 400;
        }

        .additional-practice-section {
          margin-top: 2rem;
          padding: 1rem;
          background: rgba(245,158,11,0.08);
          border-radius: var(--radius-sm);
          border-left: 3px solid var(--warning);
        }
        
        .additional-practice-section h4 {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.85rem;
          color: var(--warning);
          margin-bottom: 0.5rem;
        }
        
        .additional-practice-section p {
          font-size: 0.88rem;
          color: var(--text-muted);
          margin-bottom: 1rem;
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
