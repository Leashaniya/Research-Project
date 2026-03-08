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

// Utility function to convert decimal hours to hours + minutes format
const formatHours = (decimalHours) => {
  if (!decimalHours || decimalHours === 0) return '0 hours';
  
  const hours = Math.floor(decimalHours);
  const minutes = Math.round((decimalHours - hours) * 60);
  
  if (hours === 0) {
    return `${minutes} minutes`;
  } else if (minutes === 0) {
    return `${hours} hour${hours !== 1 ? 's' : ''}`;
  } else {
    return `${hours} hour${hours !== 1 ? 's' : ''} ${minutes} minutes`;
  }
};

// Helper function to generate adaptive daily schedule
const generateAdaptiveDailySchedule = (plan, totalHours, studyDays, quizResults) => {
  const schedule = [];
  
  // Calculate adaptive hours for each lecture based on performance
  const lecturesWithAdaptiveHours = plan.map(lecture => {
    const lectureKey = lecture.lecture.replace('.pdf', '');
    const quizAccuracy = quizResults?.topic_wise?.[lectureKey]?.accuracy ?? quizResults?.accuracy ?? 75;
    const masteryGap = 100 - quizAccuracy;
    const baselineHours = (totalHours * lecture.percentage / 100);
    const adaptiveHours = baselineHours * (1 + masteryGap / 200); // Increase for weaker lectures
    
    return {
      ...lecture,
      quizAccuracy,
      masteryGap,
      baselineHours,
      adaptiveHours,
      priority: lecture.priority
    };
  }).sort((a, b) => {
    // Sort by priority first, then by mastery gap (weaker = higher priority)
    if (a.priority !== b.priority) return a.priority - b.priority;
    return b.masteryGap - a.masteryGap;
  });
  
  // Create daily chunks for each lecture (split large lectures into multiple days)
  const lectureChunks = [];
  lecturesWithAdaptiveHours.forEach(lecture => {
    const chunks = Math.ceil(lecture.adaptiveHours / 3); // Max 3 hours per session
    const hoursPerChunk = lecture.adaptiveHours / chunks;
    
    for (let i = 0; i < chunks; i++) {
      lectureChunks.push({
        lectureName: lecture.lecture,
        hours: hoursPerChunk,
        priority: lecture.priority,
        masteryGap: lecture.masteryGap,
        chunkNumber: i + 1,
        totalChunks: chunks
      });
    }
  });
  
  // Distribute chunks across days evenly
  const chunksPerDay = Math.ceil(lectureChunks.length / studyDays);
  const hoursPerDay = totalHours / studyDays;
  
  for (let day = 1; day <= studyDays; day++) {
    const date = new Date();
    date.setDate(date.getDate() + day - 1);
    
    const dayChunks = lectureChunks.slice((day - 1) * chunksPerDay, day * chunksPerDay);
    const dayLectures = [];
    let totalDayHours = 0;
    
    // Group chunks by lecture and combine if they're the same lecture
    const lectureGroups = {};
    dayChunks.forEach(chunk => {
      const key = chunk.lectureName;
      if (!lectureGroups[key]) {
        lectureGroups[key] = {
          name: chunk.lectureName,
          hours: 0,
          priority: chunk.priority,
          masteryGap: chunk.masteryGap,
          chunks: []
        };
      }
      lectureGroups[key].hours += chunk.hours;
      lectureGroups[key].chunks.push(chunk);
    });
    
    // Convert to array and format
    Object.values(lectureGroups).forEach(group => {
      totalDayHours += group.hours;
      dayLectures.push({
        name: group.name,
        hours: group.hours,
        formattedHours: formatHours(group.hours),
        priority: group.priority,
        masteryGap: group.masteryGap
      });
    });
    
    // Generate meaningful target based on day content
    let target = "Review and practice";
    if (dayLectures.length > 0) {
      const weakLectures = dayLectures.filter(l => l.masteryGap > 20);
      const highPriorityLectures = dayLectures.filter(l => l.priority <= 3);
      
      if (weakLectures.length > 0 && highPriorityLectures.length > 0) {
        const weakNames = weakLectures.map(l => l.name.replace('.pdf', '')).join(' and ');
        target = `Focus on weak areas from ${weakNames} and retry difficult MCQs`;
      } else if (weakLectures.length > 0) {
        const weakNames = weakLectures.map(l => l.name.replace('.pdf', '')).join(' and ');
        target = `Revise weaker topics from ${weakNames} and strengthen understanding`;
      } else if (highPriorityLectures.length > 0) {
        const priorityNames = highPriorityLectures.map(l => l.name.replace('.pdf', '')).join(' and ');
        target = `Focus on high-priority concepts from ${priorityNames} with practice questions`;
      } else if (dayLectures.length === 1) {
        target = `Review and practice ${dayLectures[0].name.replace('.pdf', '')} thoroughly`;
      } else {
        const lectureNames = dayLectures.map(l => l.name.replace('.pdf', '')).join(', ');
        target = `Review important concepts from ${lectureNames}`;
      }
    }
    
    schedule.push({
      Day: day,
      Date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
      Lectures: dayLectures.length > 0 
        ? dayLectures.map(l => `${l.name.replace('.pdf', '')} (${l.formattedHours})`).join(', ')
        : 'Light review day',
      Total_Hours: formatHours(totalDayHours),
      Target: target
    });
  }
  
  return schedule;
};

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
    setLoading(true);
    setError('');
    setShowAdaptiveModal(false);
    
    try {
      // Input validation
      const totalHours = Number(adaptiveParams.total_hours);
      const studyDays = Number(adaptiveParams.study_days);
      
      // Validation rules
      if (!totalHours || totalHours <= 0) {
        throw new Error('Total study hours must be a positive number. Please enter at least 1 hour.');
      }
      
      if (!studyDays || studyDays <= 0 || !Number.isInteger(studyDays)) {
        throw new Error('Study days must be a positive integer. Please enter 1-30 days.');
      }
      
      if (studyDays > 30) {
        throw new Error('Study days should not exceed 30 for optimal planning. Please enter 1-30 days.');
      }
      
      const avgHoursPerDay = totalHours / studyDays;
      if (avgHoursPerDay > 12) {
        throw new Error(`You entered ${totalHours} hours for ${studyDays} day${studyDays !== 1 ? 's' : ''}. Maximum allowed is 12 hours/day (${studyDays * 12} hours total). Please reduce total hours or increase study days.`);
      }
      
      if (avgHoursPerDay < 1) {
        throw new Error(`You entered ${totalHours} hours for ${studyDays} day${studyDays !== 1 ? 's' : ''}. Minimum required is 1 hour/day (${studyDays} hours total). Please increase total hours or decrease study days.`);
      }
      
      // Generate baseline study plan
      const result = await getStudyPlan(totalHours, studyDays);
      
      // Adaptation parameters
      const alpha = adaptiveParams.alpha || 0.5; // Adaptation sensitivity
      const maxIncrease = (adaptiveParams.max_increase || 30) / 100; // 30% default
      const maxDecrease = (adaptiveParams.max_decrease || 15) / 100; // 15% default
      
      // Transform to adaptive plan with performance-based adaptation
      const adaptivePlan = {
        params: adaptiveParams,
        adaptive_plan: result.plan.map((lecture, index) => {
          // Calculate baseline hours (frequency-based)
          const baselineHours = (totalHours * lecture.percentage / 100);
          
          // Calculate mastery gap and adaptation factor
          const lectureKey = lecture.lecture.replace('.pdf', '');
          const quizAccuracy = quizResults?.topic_wise?.[lectureKey]?.accuracy ?? quizResults?.accuracy ?? 75; // Use real quiz accuracy
          const masteryGap = 100 - quizAccuracy; // Higher gap = more adaptation needed
          const adaptationFactor = 1 + (alpha * masteryGap / 100);
          
          // Calculate adaptive hours with caps
          let adaptiveHours = baselineHours * adaptationFactor;
          const maxAllowed = baselineHours * (1 + maxIncrease);
          const minAllowed = baselineHours * (1 - maxDecrease);
          
          adaptiveHours = Math.max(minAllowed, Math.min(maxAllowed, adaptiveHours));
          
          // Calculate delta
          const deltaHours = adaptiveHours - baselineHours;
          
          // Determine focus intensity based on priority and mastery gap
          let focusIntensity = 'Low';
          if (lecture.priority <= 3 && masteryGap >= 25) {
            focusIntensity = 'High';
          } else if (lecture.priority <= 6 || masteryGap >= 15) {
            focusIntensity = 'Medium';
          }
          
          return {
            Priority: lecture.priority,
            Lecture: lecture.lecture,
            Baseline_Hours: baselineHours,
            Adaptive_Hours: adaptiveHours,
            Delta_Hours: deltaHours,
            Quiz_Accuracy: `${Number(quizAccuracy).toFixed(2)}%`,
            Mastery_Gap: `${Number(masteryGap).toFixed(2)}%`,
            Focus_Intensity: focusIntensity
          };
        }),
        
        daily_schedule: result.daily_schedule || [],
        total_hours: totalHours,
        study_days: studyDays
      };
      
      setAdaptivePlan(adaptivePlan);
      setActiveTab('adaptive-plan');
      
    } catch (err) {
      setError('Failed to generate adaptive study plan: ' + err.message);
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
        <CommonHeader hideGoogleSignIn={true} />
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
      <CommonHeader hideGoogleSignIn={true} />
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
                      <h2>{stats?.total_topics && stats.total_topics > stats?.total_lectures ? stats.total_topics : (stats?.total_lectures ? stats.total_lectures * 6 : 0)}</h2>
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
                    <ResponsiveContainer width="100%" height={350}>
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
                    <ResponsiveContainer width="100%" height={350}>
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
                      Total study hours: <strong>{studyPlanData.total_hours}</strong> | Study days: <strong>{studyPlanData.study_days}</strong> | Average: <strong>{formatHours(studyPlanData.total_hours / studyPlanData.study_days)}/day</strong>
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
                              <td>{formatHours(row.recommended_hours)}</td>
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
                              <td>{formatHours(row.Total_Hours)}</td>
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
                      <ResponsiveContainer width="100%" height={300}>
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
                        <div><h6>Max Increase</h6><h2>{adaptivePlan.params.max_increase}%</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-arrow-up fa-3x"></i></div>
                      </div>
                    </div>
                    <div className="mcq-stats-card bg-gradient-danger">
                      <div className="mcq-stats-body">
                        <div><h6>Max Decrease</h6><h2>{adaptivePlan.params.max_decrease}%</h2></div>
                        <div className="mcq-stats-icon"><i className="fas fa-arrow-down fa-3x"></i></div>
                      </div>
                    </div>
                  </div>

                  {comparisonChartData.length > 0 && (
                    <div className="mcq-chart-card">
                      <h5><i className="fas fa-chart-bar me-2"></i>Baseline vs Adaptive Hours Comparison</h5>
                      <ResponsiveContainer width="100%" height={350}>
                        <BarChart data={comparisonChartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="lecture" />
                          <YAxis />
                          <Tooltip 
                            formatter={(value, name) => [
                              formatHours(value), 
                              name === 'baseline' ? 'Baseline' : 'Adaptive'
                            ]}
                          />
                          <Legend 
                            formatter={(value) => value === 'baseline' ? 'Baseline Hours' : 'Adaptive Hours'}
                          />
                          <Bar dataKey="baseline" fill="#a8c7fa" name="baseline" />
                          <Bar dataKey="adaptive" fill="#f4e4a1" name="adaptive" />
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
                              <td className="text-center">{formatHours(Number(row.Baseline_Hours))}</td>
                              <td className="text-center">
                                <span className={`mcq-badge mcq-badge-${row.Adaptive_Hours > row.Baseline_Hours ? 'success' : 'warning'}`}>
                                  {formatHours(Number(row.Adaptive_Hours))}
                                </span>
                              </td>
                              <td className="text-center">
                                {row.Delta_Hours > 0 ? <span className="text-success">+{formatHours(Number(row.Delta_Hours))}</span> :
                                 row.Delta_Hours < 0 ? <span className="text-danger">{formatHours(Number(row.Delta_Hours))}</span> :
                                 <span className="text-muted">0 hours</span>}
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
                <p className="mcq-hint">Click &quot;Generate Frequency-Based Plan&quot; to create an optimized study schedule.</p>
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
                    <h3>Adaptive Study Plan</h3>
                    <p>Adjust your study plan based on lecture priority and your quiz results.</p>
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
                    <h4>How this plan is created</h4>
                    <p>The system creates your personalized study schedule by considering:</p>
                    <ul>
                      <li>Lecture priority is used to decide what needs more focus</li>
                      <li>Quiz results help identify weaker areas</li>
                      <li>Study time is adjusted to balance strong and weak topics</li>
                      <li>The plan stays within realistic study limits</li>
                    </ul>
                  </div>
                </div>

                <div className="adaptive-params-section">
                  <h4><i className="fas fa-sliders-h me-2"></i>Basic Settings</h4>
                  
                  <div className="params-grid-enhanced">
                    <div className="param-group-enhanced">
                      <label htmlFor="adaptiveTotalHours">
                        <i className="fas fa-clock me-1"></i>Total Study Hours
                        <span className="form-tooltip" title="Enter the total time you can spend studying">
                          <i className="fas fa-info-circle"></i>
                        </span>
                      </label>
                      <div className="input-wrapper">
                        <input 
                          type="number" 
                          id="adaptiveTotalHours"
                          min="1" 
                          max="200" 
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
                        <span className="form-tooltip" title="Enter how many days you have before finishing this plan">
                          <i className="fas fa-info-circle"></i>
                        </span>
                      </label>
                      <div className="input-wrapper">
                        <input 
                          type="number" 
                          id="adaptiveStudyDays"
                          min="1" 
                          max="60" 
                          value={adaptiveParams.study_days} 
                          onChange={(e) => setAdaptiveParams((p) => ({ ...p, study_days: Number(e.target.value) }))}
                          className="mcq-input-enhanced"
                        />
                        <span className="input-suffix">days</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="advanced-params">
                <h5><i className="fas fa-cog me-2"></i>Adjustment Settings</h5>
                
                <div className="params-grid-enhanced">
                  <div className="param-group-enhanced">
                    <label htmlFor="adaptationFactor">
                      <i className="fas fa-balance-scale me-1"></i>Adaptation Factor (α)
                      <span className="form-tooltip" title="Controls how strongly the plan responds to quiz performance">
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
                      <small>Higher values make the plan respond more to quiz results (0.1-1.0)</small>
                    </div>
                  </div>

                  <div className="param-group-enhanced">
                    <label htmlFor="maxIncrease">
                      <i className="fas fa-arrow-up me-1"></i>Max Increase
                      <span className="form-tooltip" title="Maximum extra time added for weaker lectures">
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
                      <small>Maximum percentage increase per lecture</small>
                    </div>
                  </div>

                  <div className="param-group-enhanced">
                    <label htmlFor="maxDecrease">
                      <i className="fas fa-arrow-down me-1"></i>Max Decrease
                      <span className="form-tooltip" title="Maximum reduction for stronger lectures">
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
                      <small>Maximum percentage decrease per lecture</small>
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
