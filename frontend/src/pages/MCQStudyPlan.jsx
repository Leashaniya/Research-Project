import React, { useState, useEffect } from 'react';
import CommonHeader from '../components/CommonHeader';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import {
  checkBackendHealth,
  getDashboardStats,
  runAnalysis,
  getStudyPlan,
  getPriorityQuestions,
  submitQuiz,
  generateAdaptivePlan,
  getGraphUrl,
  getStudyPlanPdfUrl,
  getLectureDistribution,
} from '../services/mcqApi';
import './MCQStudyPlan.css';

const COLORS = ['#a8c7fa', '#b8e6b8', '#b3e5e5', '#f4e4a1', '#f8b4b4', '#d8b4fe'];
const PRIORITY_COLORS = { 1: 'danger', 2: 'warning', 3: 'info', 4: 'secondary' };
const PRIORITY_ICONS = { 1: 'fire', 2: 'exclamation-triangle', 3: 'chart-line', 4: 'clock' };

const MCQStudyPlan = () => {
  const [stats, setStats] = useState(null);
  const [percentageDf, setPercentageDf] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('dashboard');
  const [studyPlanData, setStudyPlanData] = useState(null);
  const [totalHours, setTotalHours] = useState(20);
  const [studyDays, setStudyDays] = useState(7);
  const [priorityQuestions, setPriorityQuestions] = useState([]);
  const [quizAnswers, setQuizAnswers] = useState({});
  const [quizResults, setQuizResults] = useState(null);
  const [adaptivePlan, setAdaptivePlan] = useState(null);
  const [graphUrl, setGraphUrl] = useState(null);
  const [backendConnected, setBackendConnected] = useState(false);
  const [showAdaptiveModal, setShowAdaptiveModal] = useState(false);
  const [adaptiveParams, setAdaptiveParams] = useState({
    total_hours: 20,
    study_days: 7,
    alpha: 0.5,
    max_increase: 30,
    max_decrease: 15,
  });

  useEffect(() => {
    checkBackendConnection();
  }, []);

  const checkBackendConnection = async () => {
    const isHealthy = await checkBackendHealth();
    setBackendConnected(isHealthy);
    if (isHealthy) {
      loadDashboardStats();
      loadGraphUrl();
      loadLectureDistribution();
    }
  };

  const loadDashboardStats = async () => {
    try {
      const data = await getDashboardStats();
      setStats(data);
    } catch (err) {
      setError('Failed to load dashboard stats');
    }
  };

  const loadLectureDistribution = async () => {
    try {
      const data = await getLectureDistribution();
      setPercentageDf(data);
    } catch {
      setPercentageDf([]);
    }
  };

  const loadGraphUrl = async () => {
    try {
      const url = await getGraphUrl();
      setGraphUrl(url);
    } catch {
      setGraphUrl(null);
    }
  };

  const handleRunAnalysis = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await runAnalysis();
      setStats(result.stats);
      setPercentageDf(result.percentage_df || []);
      setActiveTab('dashboard');
    } catch (err) {
      setError('Failed to run analysis: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const validateStudyPlan = () => {
    const errors = [];
    
    // Validate minimum and maximum values
    if (totalHours < 1) {
      errors.push('Total study hours must be at least 1 hour');
    }
    if (totalHours > 200) {
      errors.push('Total study hours cannot exceed 200 hours (reasonable limit)');
    }
    if (studyDays < 1) {
      errors.push('Study days must be at least 1 day');
    }
    if (studyDays > 60) {
      errors.push('Study days cannot exceed 60 days');
    }
    
    // Validate realistic daily study hours
    const dailyHours = totalHours / studyDays;
    if (dailyHours > 16) {
      errors.push(`Daily study hours (${dailyHours.toFixed(1)}) is unrealistic. Please reduce total hours or increase study days. Maximum recommended is 12 hours/day.`);
    }
    if (dailyHours < 0.5) {
      errors.push(`Daily study hours (${dailyHours.toFixed(1)}) is too low. Please increase total hours or reduce study days. Minimum recommended is 0.5 hours/day.`);
    }
    
    return errors;
  };

  const handleGenerateStudyPlan = async () => {
    const validationErrors = validateStudyPlan();
    if (validationErrors.length > 0) {
      setError('Study Plan Validation Error: ' + validationErrors.join(' '));
      return;
    }
    
    setLoading(true);
    setError('');
    try {
      const result = await getStudyPlan(totalHours, studyDays);
      setStudyPlanData(result);
      setActiveTab('study-plan');
    } catch (err) {
      setError('Failed to generate study plan: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLoadPriorityQuestions = async () => {
    setLoading(true);
    setError('');
    setQuizAnswers({});
    setQuizResults(null);
    try {
      const questions = await getPriorityQuestions();
      setPriorityQuestions(questions);
      setActiveTab('priority-questions');
    } catch (err) {
      setError('Failed to load priority questions: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleQuizAnswerChange = (questionId, value) => {
    setQuizAnswers((prev) => ({ ...prev, [questionId]: value }));
  };

  const handleSubmitQuiz = async () => {
    const totalQuestions = priorityQuestions.length;
    const answeredCount = Object.keys(quizAnswers).length;
    if (answeredCount !== totalQuestions) {
      setError(`Please answer all ${totalQuestions} questions. You have answered ${answeredCount}.`);
      if (unansweredRef.current) unansweredRef.current.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    if (!window.confirm('Are you sure you want to submit your quiz? You cannot change your answers after submission.')) {
      return;
    }
    setLoading(true);
    setError('');
    try {
      const correctAnswers = {};
      priorityQuestions.forEach((q) => {
        correctAnswers[q.id] = q.answer;
      });
      const results = await submitQuiz(quizAnswers, correctAnswers);
      setQuizResults(results);
      setActiveTab('progress');
    } catch (err) {
      setError('Failed to submit quiz: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateAdaptivePlan = async () => {
    if (!quizResults) return;
    setLoading(true);
    setError('');
    setShowAdaptiveModal(false);
    try {
      const result = await generateAdaptivePlan(
        quizResults,
        adaptiveParams.total_hours,
        adaptiveParams.study_days,
        adaptiveParams.alpha,
        adaptiveParams.max_increase / 100,
        adaptiveParams.max_decrease / 100
      );
      setAdaptivePlan(result);
      setActiveTab('adaptive-plan');
    } catch (err) {
      setError('Failed to generate adaptive plan: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const getProgressPercent = () => {
    if (!priorityQuestions.length) return 0;
    const answered = Object.keys(quizAnswers).length;
    return Math.round((answered / priorityQuestions.length) * 100);
  };

  const canSubmitQuiz = Object.keys(quizAnswers).length === priorityQuestions.length && priorityQuestions.length > 0;

  const scrollToFirstUnanswered = () => {
    const firstUnanswered = priorityQuestions.find((q) => !quizAnswers[q.id]);
    if (firstUnanswered) {
      const el = document.getElementById(`mcq-question-${firstUnanswered.id}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  const questionsByPriority = React.useMemo(() => {
    const byP = { 1: [], 2: [], 3: [], 4: [] };
    priorityQuestions.forEach((q) => {
      const p = Math.min(q.priority || 1, 4);
      if (byP[p]) byP[p].push(q);
    });
    return byP;
  }, [priorityQuestions]);

  const chartData = percentageDf.map((r) => ({
    name: r.Lecture_File || r.Lecture_Title || 'Lecture',
    questions: r.Questions_In_Lecture || 0,
    percentage: r.Percentage_of_Total || 0,
  }));

  const pieData = chartData.map((d, i) => ({
    name: d.name,
    value: d.percentage,
    fill: COLORS[i % COLORS.length],
  }));

  const comparisonChartData = adaptivePlan?.adaptive_plan?.map((row, i) => ({
    lecture: row.Lecture,
    baseline: row.Baseline_Hours,
    adaptive: row.Adaptive_Hours,
    fill: COLORS[i % COLORS.length],
  })) || [];

  if (!backendConnected) {
    return (
      <div className="mcq-page">
        <CommonHeader />
        <div className="mcq-container">
          <div className="mcq-error-card">
            <h2><i className="fas fa-unlink me-2"></i>Backend Connection Error</h2>
            <p>Cannot connect to the MCQ Study Plan backend.</p>
            <p>Ensure the FastAPI backend is running: <code>python run.py</code> from <code>backend/services/mcq-studyplan-generation</code></p>
            <button onClick={checkBackendConnection} className="btn btn-primary">
              <i className="fas fa-sync-alt me-2"></i>Retry Connection
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mcq-page">
      <CommonHeader />
      <div className="mcq-container">
        <div className="mcq-header-card mcq-header-primary">
          <div className="mcq-header-content">
            <div>
              <h2><i className="fas fa-chart-pie me-2"></i>MCQ Study Plan Generation</h2>
              <p className="mb-0">Analyze lecture materials, generate personalized study plans, and take priority quizzes</p>
            </div>
            <button
              type="button"
              className="btn btn-light"
              onClick={handleRunAnalysis}
              disabled={loading}
            >
              <i className="fas fa-play me-2"></i>{loading ? 'Running...' : 'Run Analysis'}
            </button>
          </div>
        </div>

        {error && (
          <div className="mcq-alert mcq-alert-danger">
            <strong>Error:</strong> {error}
            <button onClick={() => setError('')} className="mcq-alert-close" aria-label="Close">×</button>
          </div>
        )}

        <div className="mcq-tabs">
          {['dashboard', 'study-plan', 'priority-questions', 'progress', 'graph', 'adaptive-plan'].map((tab) => (
            <button
              key={tab}
              className={`mcq-tab-btn ${activeTab === tab ? 'active' : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === 'dashboard' && 'Dashboard'}
              {tab === 'study-plan' && 'Study Plan'}
              {tab === 'priority-questions' && 'Priority Quiz'}
              {tab === 'progress' && 'Progress'}
              {tab === 'graph' && 'Graph View'}
              {tab === 'adaptive-plan' && 'Adaptive Plan'}
            </button>
          ))}
        </div>

        <div className="mcq-content">
          {/* Dashboard Tab */}
          {activeTab === 'dashboard' && (
            <div className="mcq-dashboard">
              <div className="mcq-stats-row">
                <div className="mcq-stats-card bg-gradient-primary">
                  <div className="mcq-stats-body">
                    <div>
                      <h6>Total Lectures</h6>
                      <h2>{stats?.total_lectures ?? 0}</h2>
                    </div>
                    <div className="mcq-stats-icon"><i className="fas fa-book fa-3x"></i></div>
                  </div>
                </div>
                <div className="mcq-stats-card bg-gradient-success">
                  <div className="mcq-stats-body">
                    <div>
                      <h6>Total Questions</h6>
                      <h2>{stats?.total_questions ?? 0}</h2>
                    </div>
                    <div className="mcq-stats-icon"><i className="fas fa-question-circle fa-3x"></i></div>
                  </div>
                </div>
                <div className="mcq-stats-card bg-gradient-info">
                  <div className="mcq-stats-body">
                    <div>
                      <h6>Topics Identified</h6>
                      <h2>{stats?.total_topics ?? (stats?.total_lectures ? stats.total_lectures * 6 : 0)}</h2>
                    </div>
                    <div className="mcq-stats-icon"><i className="fas fa-tags fa-3x"></i></div>
                  </div>
                </div>
                <div className="mcq-stats-card bg-gradient-warning">
                  <div className="mcq-stats-body">
                    <div>
                      <h6>Status</h6>
                      <h5>{stats?.processed ? <><i className="fas fa-check-circle me-1"></i>Processed</> : <><i className="fas fa-clock me-1"></i>Pending</>}</h5>
                    </div>
                    <div className="mcq-stats-icon"><i className="fas fa-microchip fa-3x"></i></div>
                  </div>
                </div>
              </div>

              <div className="mcq-charts-row">
                <div className="mcq-chart-card mcq-chart-wide">
                  <h5><i className="fas fa-chart-bar me-2"></i>Question Distribution by Lecture</h5>
                  {chartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="questions" fill="#4e73df" name="Questions" />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="mcq-chart-empty">
                      <i className="fas fa-chart-line fa-4x"></i>
                      <p>No data available. Click &quot;Run Analysis&quot; to process files.</p>
                    </div>
                  )}
                </div>
                <div className="mcq-chart-card mcq-chart-narrow">
                  <h5><i className="fas fa-chart-pie me-2"></i>Distribution Pie Chart</h5>
                  {pieData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label />
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="mcq-chart-empty">
                      <i className="fas fa-chart-pie fa-4x"></i>
                      <p>No data available</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="mcq-table-card">
                <h5><i className="fas fa-table me-2"></i>Detailed Question Distribution</h5>
                <div className="mcq-table-wrap">
                  <table className="mcq-table">
                    <thead>
                      <tr>
                        <th>Lecture</th>
                        <th>Title</th>
                        <th>Questions</th>
                        <th>Percentage</th>
                        <th>Cumulative</th>
                        <th>Visual</th>
                      </tr>
                    </thead>
                    <tbody>
                      {percentageDf.length > 0 ? percentageDf.map((row, i) => (
                        <tr key={i}>
                          <td>{row.Lecture_File}</td>
                          <td>{(row.Lecture_Title || '').slice(0, 50)}{(row.Lecture_Title || '').length > 50 ? '...' : ''}</td>
                          <td className="text-center">{row.Questions_In_Lecture}</td>
                          <td className="text-center">{Number(row.Percentage_of_Total || 0).toFixed(1)}%</td>
                          <td className="text-center">{Number(row.Cumulative_Percentage || 0).toFixed(1)}%</td>
                          <td>
                            <div className="mcq-progress-bar">
                              <div className="mcq-progress-fill" style={{ width: `${row.Percentage_of_Total || 0}%` }}>
                                {Number(row.Percentage_of_Total || 0).toFixed(1)}%
                              </div>
                            </div>
                          </td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={6} className="text-center py-4">
                            <i className="fas fa-database fa-3x text-muted mb-3"></i>
                            <p className="text-muted">No data available. Please run analysis.</p>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mcq-action-row">
                <button onClick={handleRunAnalysis} disabled={loading} className="btn btn-primary btn-lg">
                  <i className="fas fa-play me-2"></i>{loading ? 'Running...' : 'Run Analysis'}
                </button>
                <button onClick={handleGenerateStudyPlan} disabled={loading} className="btn btn-success btn-lg" title="Run Analysis first">
                  <i className="fas fa-calculator me-2"></i>Generate Study Plan
                </button>
                <button onClick={handleLoadPriorityQuestions} disabled={loading} className="btn btn-warning btn-lg">
                  <i className="fas fa-star me-2"></i>Load Priority Quiz
                </button>
              </div>
            </div>
          )}

          {/* Study Plan Tab */}
          {activeTab === 'study-plan' && (
            <div className="mcq-study-plan">
              <div className="mcq-section-card mcq-section-success">
                <h2><i className="fas fa-calendar-alt me-2"></i>Study Plan Generator</h2>
                <p className="mb-0">Generate personalized study plans based on question distribution</p>
              </div>

              <div className="mcq-params-card">
                <h4><i className="fas fa-sliders-h me-2"></i>Plan Parameters</h4>
                <div className="mcq-params-form">
                  <div className="mcq-form-row">
                    <div className="mcq-form-group">
                      <label htmlFor="totalHours">
                        <i className="fas fa-clock me-1"></i>Total Study Hours
                        <span className="form-tooltip" title="Total hours available for study">
                          <i className="fas fa-info-circle"></i>
                        </span>
                      </label>
                      <div className="input-wrapper">
                        <input 
                          type="number" 
                          id="totalHours"
                          min="1" 
                          max="200" 
                          value={totalHours} 
                          onChange={(e) => setTotalHours(Number(e.target.value))} 
                          className="mcq-input-enhanced"
                        />
                        <span className="input-suffix">hours</span>
                      </div>
                      <small>Recommended: 20-100 hours total (1-12 hours/day)</small>
                    </div>
                    <div className="mcq-form-group">
                      <label htmlFor="studyDays">
                        <i className="fas fa-calendar-day me-1"></i>Number of Study Days
                        <span className="form-tooltip" title="Days until exam">
                          <i className="fas fa-info-circle"></i>
                        </span>
                      </label>
                      <div className="input-wrapper">
                        <input 
                          type="number" 
                          id="studyDays"
                          min="1" 
                          max="60" 
                          value={studyDays} 
                          onChange={(e) => setStudyDays(Number(e.target.value))}
                          className="mcq-input-enhanced"
                        />
                        <span className="input-suffix">days</span>
                      </div>
                      <small>Recommended: 7-30 days (allows for balanced study schedule)</small>
                    </div>
                  </div>
                  <div className="mcq-form-actions">
                    <button 
                      onClick={handleGenerateStudyPlan} 
                      disabled={loading} 
                      className={`btn-mcq-enhanced ${loading ? 'loading' : ''}`}
                    >
                      <i className={`fas ${loading ? 'fa-spinner fa-spin' : 'fa-calculator'} me-2`}></i>
                      {loading ? 'Generating...' : 'Generate Study Plan'}
                    </button>
                  </div>
                </div>
              </div>

              {studyPlanData && (
                <>
                  <div className="mcq-plan-results-card">
                    <div className="mcq-plan-header">
                      <h5><i className="fas fa-chart-line me-2"></i>Your Personalized Study Plan</h5>
                      <a href={getStudyPlanPdfUrl(studyPlanData.total_hours, studyPlanData.study_days)} className="btn btn-danger btn-sm" download>
                        <i className="fas fa-file-pdf me-2"></i>Download PDF
                      </a>
                    </div>
                    <div className="mcq-alert mcq-alert-info">
                      Total study hours: <strong>{studyPlanData.total_hours}</strong> | Study days: <strong>{studyPlanData.study_days}</strong> | Average: <strong>{(studyPlanData.total_hours / studyPlanData.study_days).toFixed(1)} hours/day</strong>
                    </div>
                    <h6>Recommended Focus Areas</h6>
                    <div className="mcq-table-wrap">
                      <table className="mcq-table mcq-table-success">
                        <thead>
                          <tr>
                            <th>Priority</th>
                            <th>Lecture</th>
                            <th>Question %</th>
                            <th>Recommended Hours</th>
                            <th>Focus Intensity</th>
                          </tr>
                        </thead>
                        <tbody>
                          {studyPlanData.plan.map((row, i) => (
                            <tr key={i}>
                              <td><span className={`mcq-badge mcq-badge-${row.priority <= 3 ? 'danger' : row.priority <= 6 ? 'warning' : 'info'}`}>Priority {row.priority}</span></td>
                              <td>{row.lecture}</td>
                              <td>{row.percentage}%</td>
                              <td>{row.recommended_hours}h</td>
                              <td><span className={`mcq-badge mcq-badge-${row.focus_intensity === 'High' ? 'danger' : row.focus_intensity === 'Medium' ? 'warning' : 'info'}`}>{row.focus_intensity}</span></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <h6>Daily Study Schedule</h6>
                    <div className="mcq-table-wrap">
                      <table className="mcq-table mcq-table-sm">
                        <thead>
                          <tr>
                            <th>Day</th>
                            <th>Date</th>
                            <th>Lectures to Study</th>
                            <th>Hours</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(studyPlanData.daily_schedule || []).map((row, i) => (
                            <tr key={i}>
                              <td>Day {row.Day}</td>
                              <td>{row.Date}</td>
                              <td>{row.Lectures}</td>
                              <td>{row.Total_Hours}h</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}

              {!studyPlanData && (
                <div className="mcq-empty-state">
                  <div className="empty-state-icon">
                    <i className="fas fa-clipboard-list"></i>
                  </div>
                  <h4>No Study Plan Yet</h4>
                  <p>Follow these steps to generate your personalized study plan:</p>
                  <div className="steps-list">
                    <div className="step-item">
                      <span className="step-number">1</span>
                      <span className="step-text">Run Analysis from the Dashboard</span>
                    </div>
                    <div className="step-item">
                      <span className="step-number">2</span>
                      <span className="step-text">Set your study parameters above</span>
                    </div>
                    <div className="step-item">
                      <span className="step-number">3</span>
                      <span className="step-text">Click "Generate Study Plan"</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Priority Quiz Tab */}
          {activeTab === 'priority-questions' && (
            <div className="mcq-priority-quiz">
              <div className="mcq-section-card mcq-section-warning">
                <h2><i className="fas fa-star me-2"></i>Priority Questions Quiz</h2>
                <p className="mb-0">Questions from 4 highest priority lectures ({priorityQuestions.length} questions total)</p>
              </div>

              {priorityQuestions.length > 0 ? (
                <>
                  <div className="mcq-alert mcq-alert-info">
                    <h5><i className="fas fa-info-circle me-2"></i>Quiz Instructions</h5>
                    <ul className="mb-0">
                      <li>Answer all {priorityQuestions.length} questions below</li>
                      <li>Each question requires an answer before submission</li>
                      <li>Choose best option from A, B, C, or D</li>
                      <li>Click &quot;Submit Quiz&quot; when you have answered all questions</li>
                    </ul>
                  </div>

                  <div className="mcq-quiz-progress-card">
                    <div className="mcq-quiz-progress-header">
                      <span>Quiz Progress</span>
                      <span>{Object.keys(quizAnswers).length}/{priorityQuestions.length} answered</span>
                    </div>
                    <div className={`mcq-progress-bar mcq-progress-bar-lg ${getProgressPercent() === 100 ? 'bg-success' : getProgressPercent() >= 75 ? 'bg-info' : getProgressPercent() >= 50 ? 'bg-warning' : 'bg-secondary'}`}>
                      <div className="mcq-progress-fill" style={{ width: `${getProgressPercent()}%` }}>{getProgressPercent()}%</div>
                    </div>
                    {Object.keys(quizAnswers).length < priorityQuestions.length && (
                      <div className="mcq-alert mcq-alert-warning mt-3">
                        <i className="fas fa-exclamation-triangle me-2"></i>
                        <strong>{priorityQuestions.length - Object.keys(quizAnswers).length} unanswered question(s)</strong>. Please answer all questions before submitting.
                        <button type="button" className="mcq-alert-link" onClick={scrollToFirstUnanswered}>Go to first unanswered question</button>
                      </div>
                    )}
                  </div>

                  {[1, 2, 3, 4].map((p) => (
                    questionsByPriority[p]?.length > 0 && (
                      <div key={p} className={`mcq-priority-section priority-${p}`}>
                        <div className={`mcq-priority-header mcq-priority-${PRIORITY_COLORS[p]}`}>
                          <h5>
                            <i className={`fas fa-${PRIORITY_ICONS[p]} me-2`}></i>
                            Priority {p} - {questionsByPriority[p][0]?.lecture_title || questionsByPriority[p][0]?.lecture || 'Lecture'}
                          </h5>
                        </div>
                        <div className="mcq-priority-body">
                          {questionsByPriority[p].map((q) => (
                            <div key={q.id} id={`mcq-question-${q.id}`} className={`mcq-question-item ${!quizAnswers[q.id] ? 'unanswered' : 'answered'}`}>
                              <div className="mcq-question-header">
                                <span className={`mcq-badge mcq-badge-${PRIORITY_COLORS[p]}`}>Question {q.question_number}</span>
                                <small>{q.lecture}</small>
                              </div>
                              <div className="mcq-question-text"><strong>Q{q.question_number}:</strong> {q.question}</div>
                              <div className="mcq-options">
                                <label><strong>Select your answer:</strong></label>
                                {q.options?.map((opt, idx) => (
                                  <label key={idx} className="mcq-option-label">
                                    <input
                                      type="radio"
                                      name={`q_${q.id}`}
                                      value={opt}
                                      checked={quizAnswers[q.id] === opt}
                                      onChange={() => handleQuizAnswerChange(q.id, opt)}
                                    />
                                    <span>{opt}</span>
                                  </label>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  ))}

                  <div className="mcq-quiz-submit-card">
                    <button onClick={handleSubmitQuiz} disabled={!canSubmitQuiz || loading} className="btn btn-success btn-lg">
                      <i className="fas fa-paper-plane me-2"></i>Submit Quiz
                    </button>
                    <p className="text-muted mt-2"><small>Please answer all questions before submitting</small></p>
                  </div>
                </>
              ) : (
                <div className="mcq-empty-card">
                  <i className="fas fa-question-circle fa-4x text-muted mb-3"></i>
                  <h5>No questions available</h5>
                  <p className="text-muted">Please run analysis first</p>
                </div>
              )}
            </div>
          )}

          {/* Progress Tab */}
          {activeTab === 'progress' && (
            <div className="mcq-progress-tab">
              <div className="mcq-section-card mcq-section-success">
                <h2><i className="fas fa-chart-line me-2"></i>Student Progress Report</h2>
                <p className="mb-0">Your quiz performance and learning analytics</p>
              </div>

              {quizResults ? (
                <>
                  <div className="mcq-stats-row">
                    <div className="mcq-stats-card bg-gradient-primary">
                      <div className="mcq-stats-body">
                        <div><h6>Total Attempted</h6><h2>{quizResults.total_attempted}</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-clipboard-check fa-3x"></i></div>
                      </div>
                    </div>
                    <div className="mcq-stats-card bg-gradient-success">
                      <div className="mcq-stats-body">
                        <div><h6>Correct Answers</h6><h2>{quizResults.correct_count}</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-check-circle fa-3x"></i></div>
                      </div>
                    </div>
                    <div className="mcq-stats-card bg-gradient-danger">
                      <div className="mcq-stats-body">
                        <div><h6>Wrong Answers</h6><h2>{quizResults.wrong_count}</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-times-circle fa-3x"></i></div>
                      </div>
                    </div>
                    <div className="mcq-stats-card bg-gradient-info">
                      <div className="mcq-stats-body">
                        <div><h6>Overall Accuracy</h6><h2>{quizResults.accuracy?.toFixed(1) ?? 0}%</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-percentage fa-3x"></i></div>
                      </div>
                    </div>
                  </div>

                  <div className="mcq-table-card">
                    <h5><i className="fas fa-book me-2"></i>Topic-wise Performance</h5>
                    <div className="mcq-table-wrap">
                      <table className="mcq-table">
                        <thead>
                          <tr>
                            <th>Lecture</th>
                            <th>Total Questions</th>
                            <th>Correct</th>
                            <th>Wrong</th>
                            <th>Accuracy</th>
                            <th>Performance</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(quizResults.topic_wise || {}).map(([topic, data]) => (
                            <tr key={topic}>
                              <td><strong>{topic}</strong></td>
                              <td className="text-center">{data.total}</td>
                              <td className="text-center text-success">{data.correct}</td>
                              <td className="text-center text-danger">{data.total - data.correct}</td>
                              <td className="text-center">{data.accuracy?.toFixed(1) ?? 0}%</td>
                              <td>
                                <div className="mcq-progress-bar">
                                  <div className={`mcq-progress-fill ${data.accuracy >= 80 ? 'bg-success' : data.accuracy >= 60 ? 'bg-warning' : 'bg-danger'}`} style={{ width: `${data.accuracy || 0}%` }}>
                                    {data.accuracy?.toFixed(1) ?? 0}%
                                  </div>
                                </div>
                              </td>
                            </tr>
                          ))}
                          {(!quizResults.topic_wise || Object.keys(quizResults.topic_wise).length === 0) && (
                            <tr><td colSpan={6} className="text-center py-4"><p className="text-muted">No topic-wise data available</p></td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="mcq-chart-card">
                    <h5><i className="fas fa-chart-bar me-2"></i>Performance Overview</h5>
                    {Object.keys(quizResults.topic_wise || {}).length > 0 ? (
                      <ResponsiveContainer width="100%" height={250}>
                        <BarChart data={Object.entries(quizResults.topic_wise || {}).map(([topic, d]) => ({ name: topic, accuracy: d.accuracy || 0 }))}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="name" />
                          <YAxis domain={[0, 100]} />
                          <Tooltip />
                          <Bar dataKey="accuracy" fill="#4e73df" name="Accuracy (%)" />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <p className="text-muted">No chart data</p>
                    )}
                  </div>

                  <div className="mcq-table-card">
                    <h5><i className="fas fa-list-alt me-2"></i>Detailed Question Review</h5>
                    <div className="mcq-table-wrap">
                      <table className="mcq-table">
                        <thead>
                          <tr>
                            <th>Question ID</th>
                            <th>Lecture</th>
                            <th>Your Answer</th>
                            <th>Correct Answer</th>
                            <th>Result</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(quizResults.detailed_results || []).map((r, i) => (
                            <tr key={i} className={r.is_correct ? 'table-success' : 'table-danger'}>
                              <td><code>{r.question_id}</code></td>
                              <td>{r.lecture}</td>
                              <td><span className={`mcq-badge mcq-badge-${r.is_correct ? 'success' : 'danger'}`}>{r.student_answer}</span></td>
                              <td><span className="mcq-badge mcq-badge-info">{r.correct_answer}</span></td>
                              <td>{r.is_correct ? <><i className="fas fa-check-circle text-success"></i> Correct</> : <><i className="fas fa-times-circle text-danger"></i> Wrong</>}</td>
                            </tr>
                          ))}
                          {(!quizResults.detailed_results || quizResults.detailed_results.length === 0) && (
                            <tr><td colSpan={5} className="text-center py-4"><p className="text-muted">No detailed results available</p></td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="mcq-action-row">
                    <button onClick={handleLoadPriorityQuestions} className="btn btn-primary">
                      <i className="fas fa-redo me-2"></i>Retake Quiz
                    </button>
                    <button onClick={() => setActiveTab('study-plan')} className="btn btn-info">
                      <i className="fas fa-calendar-alt me-2"></i>Study Plan
                    </button>
                    <button type="button" onClick={() => setShowAdaptiveModal(true)} className="btn btn-warning">
                      <i className="fas fa-brain me-2"></i>Generate Adaptive Study Plan
                    </button>
                    <button onClick={() => setActiveTab('graph')} className="btn btn-secondary">
                      <i className="fas fa-project-diagram me-2"></i>Graph View
                    </button>
                  </div>
                </>
              ) : (
                <p className="mcq-hint">Complete the Priority Quiz first to see your progress and generate an adaptive study plan.</p>
              )}
            </div>
          )}

          {/* Graph View Tab */}
          {activeTab === 'graph' && (
            <div className="mcq-graph-tab">
              <div className="mcq-section-card mcq-section-info">
                <h2><i className="fas fa-project-diagram me-2"></i>Graph View</h2>
                <p className="mb-0">Interactive lecture-question relationship visualization</p>
              </div>

              {graphUrl ? (
                <>
                  <div className="mcq-graph-card">
                    <h5><i className="fas fa-network-wired me-2"></i>Lecture Recommendation Graph</h5>
                    <div className="mcq-graph-iframe-wrap">
                      <iframe src={graphUrl} title="Lecture Graph" width="100%" height="100%" frameBorder="0" style={{ minHeight: 'calc(100vh - 300px)', width: '100%', height: 'calc(100vh - 300px)' }} />
                    </div>
                    <div className="mcq-graph-footer">
                      <small><i className="fas fa-info-circle me-1"></i>Interactive graph showing relationships between lectures and questions. Use mouse to zoom, pan, and interact with nodes.</small>
                    </div>
                  </div>
                  <div className="mcq-table-card">
                    <h5><i className="fas fa-question-circle me-2"></i>How to Use the Graph</h5>
                    <div className="mcq-how-to-row">
                      <div>
                        <h6><i className="fas fa-mouse-pointer me-2"></i>Navigation</h6>
                        <ul>
                          <li><strong>Scroll:</strong> Zoom in/out</li>
                          <li><strong>Click &amp; Drag:</strong> Pan around the graph</li>
                          <li><strong>Click Node:</strong> View details about lectures or questions</li>
                          <li><strong>Double Click:</strong> Focus on a specific node</li>
                        </ul>
                      </div>
                      <div>
                        <h6><i className="fas fa-palette me-2"></i>Node Colors</h6>
                        <ul>
                          <li><strong>Blue Nodes:</strong> Lectures</li>
                          <li><strong>Green Nodes:</strong> Questions</li>
                          <li><strong>Edge Thickness:</strong> Relationship strength</li>
                          <li><strong>Node Size:</strong> Importance/weight</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="mcq-empty-card">
                  <i className="fas fa-project-diagram fa-5x text-muted mb-4"></i>
                  <h4 className="text-muted">Graph Visualization Not Available</h4>
                  <p className="text-muted">The interactive graph has not been generated yet. Please run the analysis first to create the visualization.</p>
                  <button onClick={() => setActiveTab('dashboard')} className="btn btn-primary mt-4">
                    <i className="fas fa-play me-2"></i>Run Analysis
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Adaptive Plan Tab */}
          {activeTab === 'adaptive-plan' && (
            <div className="mcq-adaptive-tab">
              <div className="mcq-section-card mcq-section-warning">
                <div className="mcq-header-content">
                  <div>
                    <h2><i className="fas fa-brain me-2"></i>Adaptive Study Plan</h2>
                    <p className="mb-0">Personalized study schedule recalibrated based on your quiz performance</p>
                  </div>
                  {adaptivePlan?.params && (
                    <div className="text-end">
                      <h4 className="mb-0">α = {Number(adaptivePlan.params.alpha).toFixed(1)}</h4>
                      <small>Adaptation Factor</small>
                    </div>
                  )}
                </div>
              </div>

              {adaptivePlan ? (
                <>
                  <div className="mcq-stats-row">
                    <div className="mcq-stats-card bg-gradient-primary">
                      <div className="mcq-stats-body">
                        <div><h6>Total Hours</h6><h2>{adaptivePlan.params.total_hours}</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-clock fa-3x"></i></div>
                      </div>
                    </div>
                    <div className="mcq-stats-card bg-gradient-success">
                      <div className="mcq-stats-body">
                        <div><h6>Study Days</h6><h2>{adaptivePlan.params.study_days}</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-calendar fa-3x"></i></div>
                      </div>
                    </div>
                    <div className="mcq-stats-card bg-gradient-info">
                      <div className="mcq-stats-body">
                        <div><h6>Max Increase</h6><h2>{(adaptivePlan.params.max_increase * 100).toFixed(0)}%</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-arrow-up fa-3x"></i></div>
                      </div>
                    </div>
                    <div className="mcq-stats-card bg-gradient-danger">
                      <div className="mcq-stats-body">
                        <div><h6>Max Decrease</h6><h2>{(adaptivePlan.params.max_decrease * 100).toFixed(0)}%</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-arrow-down fa-3x"></i></div>
                      </div>
                    </div>
                  </div>

                  {comparisonChartData.length > 0 && (
                    <div className="mcq-chart-card">
                      <h5><i className="fas fa-chart-bar me-2"></i>Baseline vs Adaptive Hours Comparison</h5>
                      <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={comparisonChartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="lecture" />
                          <YAxis />
                          <Tooltip />
                          <Legend />
                          <Bar dataKey="baseline" fill="#a8c7fa" name="Baseline Hours" />
                          <Bar dataKey="adaptive" fill="#f4e4a1" name="Adaptive Hours" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  <div className="mcq-table-card">
                    <h5><i className="fas fa-table me-2"></i>Adaptive Study Plan Details</h5>
                    <div className="mcq-table-wrap">
                      <table className="mcq-table">
                        <thead>
                          <tr>
                            <th>Priority</th>
                            <th>Lecture</th>
                            <th>Baseline Hours</th>
                            <th>Adaptive Hours</th>
                            <th>Delta</th>
                            <th>Quiz Accuracy</th>
                            <th>Mastery Gap</th>
                            <th>Focus Intensity</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(adaptivePlan.adaptive_plan || []).map((row, i) => (
                            <tr key={i}>
                              <td><span className="mcq-badge mcq-badge-primary">{row.Priority}</span></td>
                              <td><strong>{row.Lecture}</strong></td>
                              <td className="text-center">{Number(row.Baseline_Hours).toFixed(1)}h</td>
                              <td className="text-center">
                                <span className={`mcq-badge mcq-badge-${row.Adaptive_Hours > row.Baseline_Hours ? 'success' : 'warning'}`}>
                                  {Number(row.Adaptive_Hours).toFixed(1)}h
                                </span>
                              </td>
                              <td className="text-center">
                                {row.Delta_Hours > 0 ? <span className="text-success">+{Number(row.Delta_Hours).toFixed(1)}h</span> :
                                 row.Delta_Hours < 0 ? <span className="text-danger">{Number(row.Delta_Hours).toFixed(1)}h</span> :
                                 <span className="text-muted">0.0h</span>}
                              </td>
                              <td className="text-center">{row.Quiz_Accuracy}</td>
                              <td className="text-center">{row.Mastery_Gap}</td>
                              <td>
                                <span className={`mcq-badge mcq-badge-${(row.Focus_Intensity || '').includes('High') ? 'danger' : (row.Focus_Intensity || '').includes('Medium') ? 'warning' : 'info'}`}>
                                  {row.Focus_Intensity}
                                </span>
                              </td>
                            </tr>
                          ))}
                          {(!adaptivePlan.adaptive_plan || adaptivePlan.adaptive_plan.length === 0) && (
                            <tr><td colSpan={8} className="text-center py-4"><p className="text-muted">No adaptive study plan data available</p></td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="mcq-table-card">
                    <h5><i className="fas fa-calendar-alt me-2"></i>Adaptive Daily Schedule</h5>
                    <div className="mcq-table-wrap">
                      <table className="mcq-table">
                        <thead>
                          <tr>
                            <th>Day</th>
                            <th>Date</th>
                            <th>Lectures</th>
                            <th>Total Hours</th>
                            <th>Target</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(adaptivePlan.adaptive_daily || []).map((row, i) => (
                            <tr key={i}>
                              <td><span className="mcq-badge mcq-badge-info">Day {row.Day}</span></td>
                              <td>{row.Date}</td>
                              <td>{row.Lectures}</td>
                              <td className="text-center"><strong>{row.Total_Hours}h</strong></td>
                              <td>{row.Target}</td>
                            </tr>
                          ))}
                          {(!adaptivePlan.adaptive_daily || adaptivePlan.adaptive_daily.length === 0) && (
                            <tr><td colSpan={5} className="text-center py-4"><p className="text-muted">No daily schedule available</p></td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="mcq-action-row">
                    <button onClick={() => setActiveTab('progress')} className="btn btn-primary">
                      <i className="fas fa-arrow-left me-2"></i>Back to Progress
                    </button>
                    <button onClick={() => setActiveTab('study-plan')} className="btn btn-info">
                      <i className="fas fa-calendar-alt me-2"></i>View Baseline Plan
                    </button>
                    <button onClick={() => setActiveTab('graph')} className="btn btn-secondary">
                      <i className="fas fa-project-diagram me-2"></i>Graph View
                    </button>
                  </div>
                </>
              ) : (
                <p className="mcq-hint">Complete the quiz and click &quot;Generate Adaptive Study Plan&quot; from the Progress tab.</p>
              )}
            </div>
          )}
        </div>

        {/* Enhanced Adaptive Plan Modal */}
        {showAdaptiveModal && (
          <div className="mcq-modal-overlay" onClick={() => setShowAdaptiveModal(false)}>
            <div className="mcq-modal-enhanced" onClick={(e) => e.stopPropagation()}>
              <div className="mcq-modal-header-enhanced">
                <div className="modal-header-content">
                  <div className="modal-icon">
                    <i className="fas fa-brain"></i>
                  </div>
                  <div className="modal-title-section">
                    <h3>Generate Adaptive Study Plan</h3>
                    <p>Personalize your study schedule based on quiz performance</p>
                  </div>
                </div>
                <button type="button" className="mcq-modal-close-enhanced" onClick={() => setShowAdaptiveModal(false)} aria-label="Close">
                  <i className="fas fa-times"></i>
                </button>
              </div>
              
              <div className="mcq-modal-body-enhanced">
                <div className="adaptive-info-card">
                  <div className="info-icon">
                    <i className="fas fa-lightbulb"></i>
                  </div>
                  <div className="info-content">
                    <h4>How Adaptive Planning Works</h4>
                    <p>The system analyzes your quiz performance and automatically adjusts study time allocation:</p>
                    <ul>
                      <li><strong>Weak areas</strong> get more study time</li>
                      <li><strong>Strong areas</strong> get less study time</li>
                      <li><strong>Optimizes</strong> your overall learning efficiency</li>
                    </ul>
                  </div>
                </div>

                <div className="adaptive-params-section">
                  <h4><i className="fas fa-sliders-h me-2"></i>Adaptation Parameters</h4>
                  
                  <div className="params-grid-enhanced">
                    <div className="param-group-enhanced">
                      <label htmlFor="adaptiveTotalHours">
                        <i className="fas fa-clock me-1"></i>Total Study Hours
                        <span className="form-tooltip" title="Total hours available for adaptive study">
                          <i className="fas fa-info-circle"></i>
                        </span>
                      </label>
                      <div className="input-wrapper">
                        <input 
                          type="number" 
                          id="adaptiveTotalHours"
                          min="1" 
                          max="100" 
                          step="0.5" 
                          value={adaptiveParams.total_hours} 
                          onChange={(e) => setAdaptiveParams((p) => ({ ...p, total_hours: Number(e.target.value) }))}
                          className="mcq-input-enhanced"
                        />
                        <span className="input-suffix">hours</span>
                      </div>
                    </div>

                    <div className="param-group-enhanced">
                      <label htmlFor="adaptiveStudyDays">
                        <i className="fas fa-calendar-day me-1"></i>Study Days
                        <span className="form-tooltip" title="Number of days for adaptive study">
                          <i className="fas fa-info-circle"></i>
                        </span>
                      </label>
                      <div className="input-wrapper">
                        <input 
                          type="number" 
                          id="adaptiveStudyDays"
                          min="1" 
                          max="30" 
                          value={adaptiveParams.study_days} 
                          onChange={(e) => setAdaptiveParams((p) => ({ ...p, study_days: Number(e.target.value) }))}
                          className="mcq-input-enhanced"
                        />
                        <span className="input-suffix">days</span>
                      </div>
                    </div>
                  </div>

                  <div className="advanced-params">
                    <h5><i className="fas fa-cog me-2"></i>Advanced Settings</h5>
                    
                    <div className="params-grid-enhanced">
                      <div className="param-group-enhanced">
                        <label htmlFor="adaptationFactor">
                          <i className="fas fa-balance-scale me-1"></i>Adaptation Factor (α)
                          <span className="form-tooltip" title="How aggressively to adapt based on performance">
                            <i className="fas fa-info-circle"></i>
                          </span>
                        </label>
                        <div className="input-wrapper">
                          <input 
                            type="number" 
                            id="adaptationFactor"
                            min="0.1" 
                            max="1" 
                            step="0.1" 
                            value={adaptiveParams.alpha} 
                            onChange={(e) => setAdaptiveParams((p) => ({ ...p, alpha: Number(e.target.value) }))}
                            className="mcq-input-enhanced"
                          />
                          <span className="input-suffix">α</span>
                        </div>
                        <div className="param-description">
                          <small>Higher = more aggressive adaptation (0.1-1.0)</small>
                        </div>
                      </div>

                      <div className="param-group-enhanced">
                        <label htmlFor="maxIncrease">
                          <i className="fas fa-arrow-up me-1"></i>Max Increase
                          <span className="form-tooltip" title="Maximum percentage increase per lecture">
                            <i className="fas fa-info-circle"></i>
                          </span>
                        </label>
                        <div className="input-wrapper">
                          <input 
                            type="number" 
                            id="maxIncrease"
                            min="10" 
                            max="100" 
                            step="5" 
                            value={adaptiveParams.max_increase} 
                            onChange={(e) => setAdaptiveParams((p) => ({ ...p, max_increase: Number(e.target.value) }))}
                            className="mcq-input-enhanced"
                          />
                          <span className="input-suffix">%</span>
                        </div>
                        <div className="param-description">
                          <small>Per lecture maximum increase</small>
                        </div>
                      </div>

                      <div className="param-group-enhanced">
                        <label htmlFor="maxDecrease">
                          <i className="fas fa-arrow-down me-1"></i>Max Decrease
                          <span className="form-tooltip" title="Maximum percentage decrease per lecture">
                            <i className="fas fa-info-circle"></i>
                          </span>
                        </label>
                        <div className="input-wrapper">
                          <input 
                            type="number" 
                            id="maxDecrease"
                            min="5" 
                            max="50" 
                            step="5" 
                            value={adaptiveParams.max_decrease} 
                            onChange={(e) => setAdaptiveParams((p) => ({ ...p, max_decrease: Number(e.target.value) }))}
                            className="mcq-input-enhanced"
                          />
                          <span className="input-suffix">%</span>
                        </div>
                        <div className="param-description">
                          <small>Per lecture maximum decrease</small>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="mcq-modal-footer-enhanced">
                <button type="button" className="btn-cancel-enhanced" onClick={() => setShowAdaptiveModal(false)}>
                  <i className="fas fa-times me-2"></i>Cancel
                </button>
                <button type="button" className={`btn-adaptive-enhanced ${loading ? 'loading' : ''}`} onClick={handleGenerateAdaptivePlan} disabled={loading}>
                  <i className={`fas ${loading ? 'fa-spinner fa-spin' : 'fa-brain'} me-2`}></i>
                  {loading ? 'Generating...' : 'Generate Adaptive Plan'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default MCQStudyPlan;
