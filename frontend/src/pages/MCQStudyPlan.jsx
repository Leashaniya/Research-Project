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
  getGraphStudentContext,
  getWeakTopicSummary,
  getStudyPlanPdfUrl,
  getLectureDistribution,
} from '../services/mcqApi';
import './MCQStudyPlan.css';

const COLORS = ['#a8c7fa', '#b8e6b8', '#b3e5e5', '#f4e4a1', '#f8b4b4', '#d8b4fe'];
const PRIORITY_COLORS = { 1: 'danger', 2: 'warning', 3: 'info', 4: 'secondary' };
const PRIORITY_ICONS = { 1: 'fire', 2: 'exclamation-triangle', 3: 'chart-line', 4: 'clock' };
const getPriorityColor = (p) => PRIORITY_COLORS[p] || 'info';
const getPriorityIcon = (p) => PRIORITY_ICONS[p] || 'book';

const TOPIC_TOKEN_LABELS = {
  jdbc: 'JDBC / Database Connectivity',
  group: 'Aggregation (GROUP BY, COUNT, SUM)',
  groups: 'Aggregation (GROUP BY, COUNT, SUM)',
  aggregation: 'Aggregation (GROUP BY, COUNT, SUM)',
  aggregate: 'Aggregation (GROUP BY, COUNT, SUM)',
  sql: 'SQL Queries',
  relation: 'Entity Relationships',
  relations: 'Entity Relationships',
  relational: 'Entity Relationships',
  eid: 'Entity Attributes',
  server: 'Database Server',
  login: 'Authentication',
  views: 'Views',
  view: 'Views',
  trigger: 'Triggers',
  triggers: 'Triggers',
  security: 'Database Security',
  general: 'General',
};

const TOPIC_PHRASE_LABELS = [
  ['faculty member', 'ER Modeling'],
  ['group by', 'Aggregation (GROUP BY, COUNT, SUM)'],
  ['entity relationships', 'Entity Relationships'],
  ['entity relationship', 'Entity Relationships'],
];

const CURATED_TOPIC_LABELS = {
  jdbc: 'JDBC / Database Connectivity',
  'jdbc / database connectivity': 'JDBC / Database Connectivity',
  'database access': 'Database Access',
  'views and triggers': 'Views and Triggers',
  'roles and privileges': 'Roles and Privileges',
  'backup and recovery': 'Backup and Recovery',
  'sql joins': 'SQL Joins',
  normalization: 'Normalization',
  'keys and constraints': 'Keys and Constraints',
  'transactions and acid': 'Transactions and ACID',
  'indexing and performance': 'Indexing and Performance',
  'er modeling': 'ER Modeling',
};

/** Same rules as backend topic_labels.clean_topic_display_name — use everywhere topics appear in the UI. */
const cleanTopicDisplayName = (topic = '') => {
  const normalized = String(topic).replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!normalized) return '';
  const key = normalized.toLowerCase();
  if (CURATED_TOPIC_LABELS[key]) return CURATED_TOPIC_LABELS[key];
  if (TOPIC_TOKEN_LABELS[key]) return TOPIC_TOKEN_LABELS[key];
  for (const [phrase, label] of TOPIC_PHRASE_LABELS) {
    if (key.includes(phrase)) return label;
  }
  const words = key.split(' ');
  if (words.length <= 4 && words.every((w) => /^[a-z]+$/i.test(w))) {
    return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
  }
  return normalized.length > 48 ? `${normalized.slice(0, 45)}...` : normalized;
};

const formatLectureName = (name = '') => {
  const clean = String(name).replace('.pdf', '');
  return clean.length > 28 ? `${clean.slice(0, 28)}...` : clean;
};

function getFriendlyLectureLabel(file, title, topics = []) {
  const num = file?.match(/\d+/)?.[0] || '';

  const cleanTitle = (title || '')
    .replace(/DATABASE MANAGEMENT SYSTEMS.*?-?/i, '')
    .replace(/lecture\s*\d+/i, '')
    .trim();

  let topicLabel = '';
  if (topics && topics.length > 0) {
    topicLabel = topics[0];
  }

  if (cleanTitle) {
    return `Lecture ${num} – ${cleanTitle}`;
  }

  if (topicLabel) {
    return `Lecture ${num} – ${cleanTopicDisplayName(topicLabel)}`;
  }

  return `Lecture ${num}`;
}

function formatDailyScheduleLectures(lecturesText, distributionRows) {
  if (!lecturesText || !distributionRows?.length) return lecturesText;
  let s = String(lecturesText);
  const sorted = [...distributionRows].sort(
    (a, b) => String(b.Lecture_File || '').length - String(a.Lecture_File || '').length
  );
  for (const r of sorted) {
    const f = r.Lecture_File;
    if (!f || !s.includes(f)) continue;
    const label = getFriendlyLectureLabel(f, r.Lecture_Title, r.Top_Topics || []);
    s = s.split(f).join(label);
  }
  return s;
}

function getExamWeightWhy(percentage) {
  const p = Number(percentage) || 0;
  if (p > 20) return 'Suggested: shows up a lot in past exams';
  if (p > 10) return 'Suggested: comes up fairly often in past exams';
  return 'Suggested: good to review — fewer past-exam questions';
}

function formatBaselineDayPlan(scheduleRow, distributionRows) {
  const raw = String(scheduleRow.Lectures || '').trim();
  if (!raw) {
    return {
      lectureLines: [],
      focus: '—',
      task: 'Practice 5 questions + revise notes',
    };
  }
  const parts = raw.split(',').map((s) => s.trim()).filter(Boolean);
  const rowsByFile = Object.fromEntries((distributionRows || []).map((r) => [r.Lecture_File, r]));
  const lectureLines = parts.map((file) => {
    const r = rowsByFile[file];
    return getFriendlyLectureLabel(file, r?.Lecture_Title, r?.Top_Topics || []);
  });
  const topicOrder = [];
  parts.forEach((file) => {
    (rowsByFile[file]?.Top_Topics || []).forEach((t) => {
      const h = cleanTopicDisplayName(t);
      if (h && !topicOrder.includes(h)) topicOrder.push(h);
    });
  });
  const focus = topicOrder.slice(0, 4).join(', ') || 'Core ideas from your slides for these lectures';
  const task = 'Practice 5 questions + revise notes';
  return { lectureLines, focus, task };
}

const humanizeFocusLine = (focus) => {
  if (!focus || focus === 'Key ideas from this lecture') return 'Key concepts from this lecture';
  return focus
    .split(',')
    .map((t) => cleanTopicDisplayName(t.trim()))
    .filter(Boolean)
    .join(', ');
};

const formatPerformanceLevel = (status) => {
  const s = String(status || '');
  if (s === 'weak_low_evidence' || (s.startsWith('weak') && s.includes('low_evidence'))) return 'Weak — few quiz questions';
  if (s === 'moderate_low_evidence' || (s.startsWith('moderate') && s.includes('low_evidence'))) return 'Moderate — few quiz questions';
  if (s === 'strong_low_evidence' || (s.startsWith('strong') && s.includes('low_evidence'))) return 'Strong — few quiz questions';
  if (s.startsWith('weak')) return 'Weak';
  if (s.startsWith('moderate')) return 'Moderate';
  if (s.startsWith('strong')) return 'Strong';
  return s.replace(/_/g, ' ');
};

const normalizeLectureKey = (value = '') => String(value).replace(/\.pdf$/i, '');

const getMainWeakTopic = (quizResults, fallbackWeakTopics = []) => {
  const rows = Object.values(quizResults?.topic_wise_accuracy || {});
  const weakRows = rows
    .map((r) => ({
      topic: cleanTopicDisplayName(r?.topic_name || ''),
      accuracy: Number(r?.accuracy ?? 100),
      band: String(r?.band || ''),
      reliable: Boolean(r?.is_reliable),
      total: Number(r?.total || 0),
    }))
    .filter((r) => r.topic && r.band === 'weak')
    .sort((a, b) => {
      if (a.reliable !== b.reliable) return a.reliable ? -1 : 1;
      if (a.accuracy !== b.accuracy) return a.accuracy - b.accuracy;
      return b.total - a.total;
    });

  if (weakRows.length > 0) return weakRows[0].topic;
  return cleanTopicDisplayName(fallbackWeakTopics?.[0] || '');
};

const lectureHasDirectQuizEvidence = (lecture, quizResults) => {
  const stem = normalizeLectureKey(lecture);
  const topicWise = quizResults?.topic_wise || {};
  return Object.prototype.hasOwnProperty.call(topicWise, stem) || Object.prototype.hasOwnProperty.call(topicWise, `${stem}.pdf`);
};

const toFriendlyLectureLabel = (lectureFile, lectureMetaByFile) => {
  const stem = normalizeLectureKey(lectureFile);
  return getFriendlyLectureLabel(
    lectureFile,
    lectureMetaByFile[lectureFile]?.title || lectureMetaByFile[stem]?.title,
    lectureMetaByFile[lectureFile]?.topics || lectureMetaByFile[stem]?.topics || []
  );
};

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

const getAdaptiveReason = (row, lectureMetaByFile = {}) => {
  const quizAcc = Number(row?.Quiz_Accuracy);
  const masteryGap = Number(row?.Mastery_Gap);
  const delta = Number(row?.Delta_Hours);
  const focus = String(row?.Focus_Intensity || '');
  const lecture = String(row?.Lecture || '');
  const stem = normalizeLectureKey(lecture);
  const topics = lectureMetaByFile[lecture]?.topics || lectureMetaByFile[stem]?.topics || [];
  const primaryTopic = cleanTopicDisplayName(topics?.[0] || '');

  let reason = 'Balanced revision for this lecture.';
  if (!Number.isNaN(quizAcc)) {
    if (quizAcc < 40) {
      reason = `Low quiz score (${quizAcc.toFixed(1)}%) in this lecture.`;
    } else if (quizAcc < 60) {
      reason = `Moderate quiz score (${quizAcc.toFixed(1)}%): needs reinforcement.`;
    } else if (quizAcc >= 75) {
      reason = `Strong quiz score (${quizAcc.toFixed(1)}%): maintain performance.`;
    } else {
      reason = `Stable quiz score (${quizAcc.toFixed(1)}%): keep regular practice.`;
    }
  }

  if (!Number.isNaN(masteryGap) && masteryGap > 0.35) {
    reason = `Large mastery gap detected (${masteryGap.toFixed(2)}).`;
  }

  let action = 'Revise notes, then practice 5 MCQs.';
  if (delta > 0.05) {
    action = `Extra time added (${formatHours(Math.abs(delta))}) to improve this area.`;
  } else if (delta < -0.05) {
    action = `Time reduced (${formatHours(Math.abs(delta))}) because this area is more stable.`;
  }

  if (focus.includes('High')) {
    action = primaryTopic
      ? `Focus first on ${primaryTopic}, then attempt targeted MCQs.`
      : 'Focus first on core weak concepts, then attempt targeted MCQs.';
  } else if (focus.includes('Low')) {
    action = primaryTopic
      ? `Light maintenance: quick revision of ${primaryTopic} + short practice.`
      : 'Light maintenance: quick revision + short practice set.';
  }

  return { reason, action };
};

const ADAPTIVE_DAILY_BLOCK_MAX_H = 3;

const suggestedTaskForAdaptiveSegment = () => 'Practice 5 questions + revise notes';

/**
 * Day-by-day breakdown using the same Adaptive_Hours as the adaptive plan (after rebalancing).
 * Chunks are spread round-robin across study days; dates match the baseline daily_schedule from the same generation call when present.
 */
const buildAdaptiveDailyScheduleFromPlan = (adaptiveRows, studyDays, baselineDailySchedule, lectureMetaByFile) => {
  if (!adaptiveRows?.length || !studyDays || studyDays < 1) return [];

  const sorted = [...adaptiveRows].sort((a, b) => Number(a.Priority || 0) - Number(b.Priority || 0));
  const chunks = [];
  sorted.forEach((row) => {
    let left = Number(row.Adaptive_Hours || 0);
    if (left <= 1e-9) return;
    while (left > 1e-9) {
      const piece = Math.min(ADAPTIVE_DAILY_BLOCK_MAX_H, left);
      chunks.push({
        Lecture: row.Lecture,
        hours: piece,
        Evidence_Source: row.Evidence_Source,
        Focus_Intensity: row.Focus_Intensity,
      });
      left -= piece;
    }
  });

  const buckets = Array.from({ length: studyDays }, () => []);
  chunks.forEach((c, i) => {
    buckets[i % studyDays].push(c);
  });

  const schedule = [];
  for (let d = 0; d < studyDays; d++) {
    const baselineRow = baselineDailySchedule?.[d];
    const dayNum = baselineRow?.Day != null ? baselineRow.Day : d + 1;
    let dateStr = baselineRow?.Date != null ? String(baselineRow.Date).trim() : '';
    if (!dateStr) {
      const date = new Date();
      date.setDate(date.getDate() + d);
      dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }

    const raw = buckets[d];
    const merged = [];
    raw.forEach((c) => {
      const last = merged[merged.length - 1];
      if (last && last.Lecture === c.Lecture) {
        last.hours += c.hours;
      } else {
        merged.push({ ...c, hours: c.hours });
      }
    });

    const segments = merged.map((m) => {
      const stem = normalizeLectureKey(m.Lecture);
      const meta = lectureMetaByFile[m.Lecture] || lectureMetaByFile[stem] || {};
      const topics = meta.topics || [];
      const focus =
        topics
          .slice(0, 3)
          .filter(Boolean)
          .map((t) => cleanTopicDisplayName(t))
          .join(', ') || 'Key ideas from this lecture';
      return {
        lectureFile: m.Lecture,
        friendlyLecture: getFriendlyLectureLabel(m.Lecture, meta.title, topics),
        hours: m.hours,
        focus,
        task: suggestedTaskForAdaptiveSegment(m.Evidence_Source, m.Focus_Intensity),
      };
    });

    const totalDay = segments.reduce((s, seg) => s + seg.hours, 0);
    if (segments.length === 0) {
      schedule.push({
        day: dayNum,
        date: dateStr,
        segments: [
          {
            lectureFile: null,
            friendlyLecture: 'Free revision day',
            hours: 0,
            focus: 'Review any weak topics',
            task: 'Practice questions + revise notes',
          },
        ],
        totalHours: 0,
      });
    } else {
      schedule.push({
        day: dayNum,
        date: dateStr,
        segments,
        totalHours: totalDay,
      });
    }
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
  const [graphStudentContext, setGraphStudentContext] = useState(null);
  const [weakTopicSummary, setWeakTopicSummary] = useState([]);
  const [backendConnected, setBackendConnected] = useState(false);
  const [showAdaptiveModal, setShowAdaptiveModal] = useState(false);
  const [showDetailedReview, setShowDetailedReview] = useState(false);
  const [expandedStudyDay, setExpandedStudyDay] = useState(null);
  const [expandedLectureRow, setExpandedLectureRow] = useState(null);
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

  useEffect(() => {
    setExpandedStudyDay(null);
    setExpandedLectureRow(null);
  }, [studyPlanData]);

  useEffect(() => {
    if (activeTab === 'graph' && backendConnected) {
      loadGraphUrl();
      loadGraphStudentContext();
    }
  }, [activeTab, backendConnected]);

  const checkBackendConnection = async () => {
    const isHealthy = await checkBackendHealth();
    setBackendConnected(isHealthy);
    if (isHealthy) {
      loadDashboardStats();
      loadGraphUrl();
      loadGraphStudentContext();
      loadWeakTopicSummary();
      loadLectureDistribution();
    }
  };

  const loadGraphStudentContext = async () => {
    try {
      const data = await getGraphStudentContext();
      setGraphStudentContext(data);
    } catch {
      setGraphStudentContext(null);
    }
  };

  const loadWeakTopicSummary = async () => {
    try {
      const rows = await getWeakTopicSummary();
      setWeakTopicSummary(Array.isArray(rows) ? rows : []);
    } catch {
      setWeakTopicSummary([]);
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
      if (url) {
        const sep = url.includes('?') ? '&' : '?';
        setGraphUrl(`${url}${sep}v=${Date.now()}`);
      } else {
        setGraphUrl(null);
      }
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
      await loadGraphUrl();
      await loadGraphStudentContext();
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
      await loadLectureDistribution();
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
    setShowDetailedReview(false);
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
      scrollToFirstUnanswered();
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
      await loadGraphUrl();
      await loadGraphStudentContext();
      await loadWeakTopicSummary();
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
      
      if (!quizResults) {
        throw new Error('Please submit the quiz first to generate the adaptive plan.');
      }

      const alpha = 0.5;
      const maxIncrease = 0.3;
      const maxDecrease = 0.15;
      const response = await generateAdaptivePlan(
        quizResults,
        totalHours,
        studyDays,
        alpha,
        maxIncrease,
        maxDecrease
      );
      console.log("Adaptive plan triggered", response?.data ?? response);

      const adaptivePlan = {
        params: response?.params || {
          total_hours: totalHours,
          study_days: studyDays,
          alpha,
          max_increase: maxIncrease,
          max_decrease: maxDecrease,
        },
        adaptive_plan: response?.adaptive_plan || [],
        adaptive_daily: response?.adaptive_daily || [],
        daily_schedule: response?.adaptive_daily || [],
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
    const byP = {};
    priorityQuestions.forEach((q) => {
      const p = Number(q.priority || 1);
      if (!byP[p]) byP[p] = [];
      byP[p].push(q);
    });
    return byP;
  }, [priorityQuestions]);

  const priorityOrder = React.useMemo(() => {
    return Object.keys(questionsByPriority)
      .map((k) => Number(k))
      .sort((a, b) => a - b);
  }, [questionsByPriority]);

  const highPriorityOrder = React.useMemo(
    () => priorityOrder.filter((p) => p >= 1 && p <= 4),
    [priorityOrder]
  );

  const coveragePriorityOrder = React.useMemo(
    () => priorityOrder.filter((p) => p >= 5 && p <= 8),
    [priorityOrder]
  );

  const lectureMetaByFile = React.useMemo(() => {
    const m = Object.create(null);
    (percentageDf || []).forEach((r) => {
      const f = r.Lecture_File;
      if (!f) return;
      const payload = { title: r.Lecture_Title, topics: r.Top_Topics || [] };
      m[f] = payload;
      const stem = String(f).replace(/\.pdf$/i, '');
      if (stem) m[stem] = payload;
    });
    return m;
  }, [percentageDf]);

  const chartData = percentageDf.map((r) => {
    const friendly = getFriendlyLectureLabel(r.Lecture_File, r.Lecture_Title, r.Top_Topics || []);
    return {
    name: friendly,
    shortName: formatLectureName(friendly),
    questions: r.Questions_In_Lecture || 0,
    percentage: r.Percentage_of_Total || 0,
    };
  });

  const pieData = chartData.map((d, i) => ({
    name: d.name,
    value: d.percentage,
    fill: COLORS[i % COLORS.length],
  }));

  const whatToStudyFirst = React.useMemo(() => {
    const sorted = [...(percentageDf || [])].sort(
      (a, b) => Number(b.Percentage_of_Total || 0) - Number(a.Percentage_of_Total || 0)
    );
    const topLectures = sorted.slice(0, 2).map((r) =>
      getFriendlyLectureLabel(r.Lecture_File, r.Lecture_Title, r.Top_Topics || [])
    );
    const seen = new Set();
    const topTopics = [];
    for (const r of sorted) {
      for (const t of r.Top_Topics || []) {
        const c = cleanTopicDisplayName(t);
        if (c && !seen.has(c)) {
          seen.add(c);
          topTopics.push(c);
          if (topTopics.length >= 3) break;
        }
      }
      if (topTopics.length >= 3) break;
    }
    return { topLectures, topTopics };
  }, [percentageDf]);

  const comparisonChartData = adaptivePlan?.adaptive_plan?.map((row, i) => ({
    lecture: row.Lecture,
    shortLecture: formatLectureName(
      getFriendlyLectureLabel(
        row.Lecture,
        lectureMetaByFile[row.Lecture]?.title,
        lectureMetaByFile[row.Lecture]?.topics || []
      )
    ),
    baseline: row.Baseline_Hours,
    adaptive: row.Adaptive_Hours,
    fill: COLORS[i % COLORS.length],
  })) || [];

  const topicWeaknessRows = React.useMemo(() => {
    const rows = Object.values(quizResults?.topic_wise_accuracy || {});
    return rows
      .map((r) => ({
        topic_name: r.topic_name || 'General',
        correct: Number(r.correct || 0),
        total: Number(r.total || 0),
        accuracy: Number(r.accuracy || 0),
        status: r.status || r.band || 'moderate',
        is_reliable: Boolean(r.is_reliable),
      }))
      .sort((a, b) => a.accuracy - b.accuracy);
  }, [quizResults]);

  const progressFocusNowRows = React.useMemo(() => {
    return topicWeaknessRows
      .filter((r) => r.accuracy < 50 && r.total >= 2)
      .sort((a, b) => a.accuracy - b.accuracy)
      .slice(0, 3);
  }, [topicWeaknessRows]);

  const progressOtherTopicRows = React.useMemo(() => {
    const inFocus = new Set(progressFocusNowRows.map((r) => r.topic_name));
    return topicWeaknessRows.filter((r) => !inFocus.has(r.topic_name));
  }, [topicWeaknessRows, progressFocusNowRows]);

  const adaptiveTopicTiers = React.useMemo(() => {
    const rows = Object.values(quizResults?.topic_wise_accuracy || {});
    const weak = [];
    const moderate = [];
    const strong = [];
    const addUnique = (arr, label) => {
      if (label && !arr.includes(label)) arr.push(label);
    };
    rows.forEach((r) => {
      const band = String(r.band || 'moderate');
      const label = cleanTopicDisplayName(r.topic_name || 'General');
      if (!label) return;
      if (band === 'weak') addUnique(weak, label);
      else if (band === 'moderate') addUnique(moderate, label);
      else if (band === 'strong') addUnique(strong, label);
    });
    return { weak, moderate, strong };
  }, [quizResults]);

  const studentLearningContext = React.useMemo(() => {
    const backendCtx = graphStudentContext?.student_learning_context || {};
    const weakTopics =
      backendCtx.weak_topics_confirmed && backendCtx.weak_topics_confirmed.length
        ? backendCtx.weak_topics_confirmed
        : (quizResults?.weak_topics_confirmed || []).map((t) => cleanTopicDisplayName(t));
    const relatedTopics = backendCtx.related_topics || [];
    const studyPlanSettings = {
      ...(backendCtx.study_plan_settings || {}),
      total_hours: adaptivePlan?.params?.total_hours ?? backendCtx?.study_plan_settings?.total_hours ?? null,
      study_days: adaptivePlan?.params?.study_days ?? backendCtx?.study_plan_settings?.study_days ?? null,
      alpha: adaptivePlan?.params?.alpha ?? backendCtx?.study_plan_settings?.alpha ?? null,
      max_increase: adaptivePlan?.params?.max_increase ?? backendCtx?.study_plan_settings?.max_increase ?? null,
      max_decrease: adaptivePlan?.params?.max_decrease ?? backendCtx?.study_plan_settings?.max_decrease ?? null,
    };
    return {
      weak_topics_confirmed: weakTopics,
      topic_accuracy: backendCtx.topic_accuracy || [],
      priority_lectures: backendCtx.priority_lectures || (graphStudentContext?.meta?.priority_files || []),
      related_topics: relatedTopics,
      recommended_mcqs: backendCtx.recommended_mcqs || [],
      study_plan_settings: studyPlanSettings,
      quiz_accuracy_overall: backendCtx.quiz_accuracy_overall ?? quizResults?.accuracy ?? 0,
      updated_at: backendCtx.updated_at || '',
    };
  }, [graphStudentContext, quizResults, adaptivePlan]);

  const adaptiveGraphragNarrative = React.useMemo(() => {
    const weakQuiz = (quizResults?.weak_topics_confirmed || []).map((t) => cleanTopicDisplayName(t));
    const weakSaved = studentLearningContext?.weak_topics_confirmed || [];
    const weakShow = weakQuiz.length ? weakQuiz : weakSaved;
    const links = studentLearningContext?.related_topics?.map((l) => ({
      from_weak: l.weak_topic,
      related_concept: l.related_topic,
      link_type: l.link_type || '',
    })) || [];
    return { weakShow, links };
  }, [quizResults, studentLearningContext]);

  const adaptiveNowAction = React.useMemo(() => {
    const focusFirst = getMainWeakTopic(quizResults, adaptiveGraphragNarrative.weakShow) || '';
    const relatedFromLink = adaptiveGraphragNarrative.links?.find((l) => {
      if (!focusFirst) return true;
      const weak = String(l?.from_weak || '').toLowerCase();
      const ff = String(focusFirst).toLowerCase();
      return weak.includes(ff) || ff.includes(weak);
    });
    const thenRevise = relatedFromLink?.related_concept || adaptiveGraphragNarrative.links?.[0]?.related_concept || '';
    return { focusFirst, thenRevise };
  }, [adaptiveGraphragNarrative]);

  const adaptiveDailySchedule = React.useMemo(() => {
    if (!adaptivePlan?.adaptive_plan?.length || !adaptivePlan?.params) return [];
    const studyDays = Number(adaptivePlan.params.study_days || 0);
    if (!studyDays) return [];
    return buildAdaptiveDailyScheduleFromPlan(
      adaptivePlan.adaptive_plan,
      studyDays,
      adaptivePlan.daily_schedule || [],
      lectureMetaByFile
    );
  }, [adaptivePlan, lectureMetaByFile]);

  const adaptiveDayNarrativeBlocks = React.useMemo(() => {
    if (!adaptiveDailySchedule.length) return [];
    return adaptiveDailySchedule.map((day) => {
      const lines = [`Day ${day.day}:`];
      day.segments.forEach((seg) => {
        if (!seg.lectureFile && Number(seg.hours || 0) < 1e-9) {
          lines.push('- Lecture: Free revision day');
          lines.push('- Focus: Review any weak topics');
          lines.push('- Task: Practice questions + revise notes');
          return;
        }
        lines.push(`- Lecture: ${seg.friendlyLecture}`);
        lines.push(`- Focus: ${humanizeFocusLine(seg.focus)}`);
        lines.push('- Task: Practice 5 questions + revise notes');
      });
      return lines.join('\n');
    });
  }, [adaptiveDailySchedule]);

  const highFrequencyLectureFiles = React.useMemo(() => {
    const sorted = [...(percentageDf || [])].sort(
      (a, b) => Number(b.Percentage_of_Total || 0) - Number(a.Percentage_of_Total || 0)
    );
    return new Set(sorted.slice(0, 3).map((r) => r.Lecture_File).filter(Boolean));
  }, [percentageDf]);

  const getQuizQuestionReasons = React.useCallback(
    (q) => {
      const stem = normalizeLectureKey(q.lecture || '');
      const p = q.priority ?? 1;
      const lectureTopics = lectureMetaByFile[q.lecture]?.topics || lectureMetaByFile[stem]?.topics || [];
      const R_PAST = 'Comes frequently in exams';
      const R_WEIGHT = 'From an important lecture';
      const R_CONCEPT = 'Important concept you should understand';
      const R_REVISION = 'Added for revision';

      const reasons = [];
      if (p <= 2) reasons.push(R_WEIGHT);
      else if (highFrequencyLectureFiles.has(q.lecture)) reasons.push(R_PAST);

      if (lectureTopics.length > 0) reasons.push(R_CONCEPT);
      if (p >= 3) reasons.push(R_REVISION);

      if (p > 2 && highFrequencyLectureFiles.has(q.lecture) && !reasons.includes(R_PAST)) {
        reasons.splice(1, 0, R_PAST);
      }

      const unique = [...new Set(reasons)];
      if (unique.length === 0) {
        return [R_REVISION, R_CONCEPT].slice(0, 2);
      }
      return unique.slice(0, 3);
    },
    [highFrequencyLectureFiles, lectureMetaByFile]
  );

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
              <h2><i className="fas fa-chart-pie me-2"></i>Study plan &amp; practice</h2>
              <p className="mb-0">Your study assistant — see what to study, practice, and review next.</p>
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
                      <h6>
                        Topics Identified
                        <span className="form-tooltip" title="Rough count of ideas found in your slides — used to help plan your study.">
                          <i className="fas fa-info-circle ms-1"></i>
                        </span>
                      </h6>
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

              {(whatToStudyFirst.topLectures.length > 0 || whatToStudyFirst.topTopics.length > 0) && (
                <div className="mcq-what-first-card">
                  <h5>Start here</h5>
                  <p className="mcq-what-first-helper mb-2">A quick starting point based on past exam patterns.</p>
                  {whatToStudyFirst.topLectures.length > 0 && (
                    <div className="mcq-what-first-block">
                      <h6>Start with:</h6>
                      <ul>
                        {whatToStudyFirst.topLectures.map((name) => (
                          <li key={name}>{name}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {whatToStudyFirst.topTopics.length > 0 && (
                    <div className="mcq-what-first-block">
                      <h6>Focus on:</h6>
                      <ul>
                        {whatToStudyFirst.topTopics.map((t) => (
                          <li key={t}>{t}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              <div className="mcq-charts-row">
                <div className="mcq-chart-card mcq-chart-wide">
                  <h5><i className="fas fa-chart-bar me-2"></i>Questions per lecture</h5>
                  <p className="mcq-chart-subtitle">Taller bars = more practice questions from that lecture in past exams.</p>
                  {chartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={350}>
                      <BarChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="shortName" />
                        <YAxis label={{ value: 'Questions', angle: -90, position: 'insideLeft' }} />
                        <Tooltip
                          formatter={(value, name) => [value, name === 'questions' ? 'Question Count' : name]}
                          labelFormatter={(label, payload) => payload?.[0]?.payload?.name || label}
                        />
                        <Legend />
                        <Bar dataKey="questions" fill="#4e73df" name="Questions" />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="mcq-chart-empty">
                      <i className="fas fa-chart-line fa-4x"></i>
                      <p>No data yet. Click &quot;Run Analysis&quot; on the Dashboard to load your materials.</p>
                    </div>
                  )}
                </div>
                <div className="mcq-chart-card mcq-chart-narrow">
                  <h5><i className="fas fa-chart-pie me-2"></i>Question Weight (%) by Lecture</h5>
                  {pieData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={350}>
                      <PieChart>
                        <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label={({ percent }) => `${(percent * 100).toFixed(0)}%`} />
                        <Tooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, 'Question Weight']} />
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
                <h5><i className="fas fa-table me-2"></i>All lectures &amp; topics</h5>
                <details className="mcq-details-collapse">
                  <summary>Show full table</summary>
                <div className="mcq-table-wrap">
                  <table className="mcq-table">
                    <thead>
                      <tr>
                        <th>Lecture</th>
                        <th>Title</th>
                            <th>Top Topics</th>
                        <th>Questions</th>
                        <th>Percentage</th>
                        <th>Cumulative</th>
                        <th>Visual</th>
                      </tr>
                    </thead>
                    <tbody>
                      {percentageDf.length > 0 ? percentageDf.map((row, i) => (
                        <tr key={i}>
                          <td>{getFriendlyLectureLabel(row.Lecture_File, row.Lecture_Title, row.Top_Topics || [])}</td>
                          <td>{(row.Lecture_Title || '').slice(0, 50)}{(row.Lecture_Title || '').length > 50 ? '...' : ''}</td>
                          <td>
                            {(row.Top_Topics || []).length > 0 ? (
                              <div className="mcq-topic-chip-row">
                                {(row.Top_Topics || []).slice(0, 3).map((topic) => {
                                  const label = cleanTopicDisplayName(topic);
                                  return label ? <span key={`${row.Lecture_File}-${label}`} className="mcq-topic-chip">{label}</span> : null;
                                })}
                              </div>
                            ) : (
                              <span className="text-muted">Not available</span>
                            )}
                          </td>
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
                          <td colSpan={7} className="text-center py-4">
                            <i className="fas fa-database fa-3x text-muted mb-3"></i>
                            <p className="text-muted">No data yet. Run Analysis on the Dashboard first.</p>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                </details>
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
                <p className="mb-0">Build a simple day-by-day plan from your materials and past-exam-style questions.</p>
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
                      <small>Suggested: 20–100 hours total (about 1–12 hours/day)</small>
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
                      <small>Suggested: 7–30 days for a steady pace</small>
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
                    <div className="mcq-study-plan-tip">
                      👉 Follow this plan daily. Focus more time on important topics and practice questions.
                    </div>
                    <div className="mcq-plan-header">
                      <h5><i className="fas fa-chart-line me-2"></i>Your study plan</h5>
                      <a href={getStudyPlanPdfUrl(studyPlanData.total_hours, studyPlanData.study_days)} className="btn btn-danger btn-sm" download>
                        <i className="fas fa-file-pdf me-2"></i>Download PDF
                      </a>
                    </div>
                    <div className="mcq-alert mcq-alert-info mcq-plan-summary-compact">
                      Total study hours: <strong>{studyPlanData.total_hours}</strong> | Study days: <strong>{studyPlanData.study_days}</strong> | Average: <strong>{formatHours(studyPlanData.total_hours / studyPlanData.study_days)}/day</strong>
                    </div>
                    <h6>Where to focus your study time</h6>
                    <p className="mcq-study-plan-hint">Order 1 = spend more time here first. Key ideas come from your slides.</p>
                    <div className="mcq-plan-question-base">
                      <strong>Question %</strong> — Based on {stats?.total_questions ?? 0} past paper questions <i className="fas fa-check-circle mcq-validated-check"></i>
                    </div>
                    <div className="mcq-study-lecture-cards mcq-priority-planner-list">
                      {studyPlanData.plan.map((row, i) => {
                        const p = i + 1;
                        const priorityMeta =
                          p === 1
                            ? { label: 'Must Study', tone: 'must', bg: '#ff5a3d' }
                            : p <= 3
                              ? { label: 'Important', tone: 'important', bg: '#f59e0b' }
                              : p <= 6
                                ? { label: 'Review', tone: 'review', bg: '#3b82f6' }
                                : { label: 'Optional', tone: 'optional', bg: '#6b7280' };
                        const topics = (lectureMetaByFile[row.lecture]?.topics || [])
                          .slice(0, 3)
                          .map((t) => cleanTopicDisplayName(t));
                        const detailsAvailable = topics.length > 0 || Boolean(getExamWeightWhy(row.percentage));
                        const rowKey = `${row.lecture}-${i}`;
                        const rowExpanded = expandedLectureRow === rowKey;
                        return (
                          <div
                            key={i}
                            className="mcq-lecture-card mcq-lecture-compact-row"
                            style={{ borderLeft: `5px solid ${priorityMeta.bg}` }}
                          >
                            <button
                              type="button"
                              className="mcq-lecture-row-main"
                              onClick={() => {
                                if (!detailsAvailable) return;
                                setExpandedLectureRow((prev) => (prev === rowKey ? null : rowKey));
                              }}
                            >
                              <span className="mcq-order-badge">{p}</span>
                              <span className={`mcq-priority-pill mcq-priority-pill-${priorityMeta.tone}`}>
                                {priorityMeta.label}
                                </span>
                              <div className="mcq-lecture-main-content">
                                <h6 className="mcq-lecture-title">
                                {getFriendlyLectureLabel(
                                  row.lecture,
                                  lectureMetaByFile[row.lecture]?.title,
                                  lectureMetaByFile[row.lecture]?.topics || []
                                )}
                                </h6>
                                <div className="mcq-lecture-topics-row">
                                  {topics.length > 0 ? (
                                    topics.map((t) => (
                                      <span key={t} className="mcq-lecture-topic-pill">{t}</span>
                                    ))
                                  ) : (
                                    <span className="text-muted">No key topics</span>
                                  )}
                                </div>
                              </div>
                              <div className="mcq-lecture-side-metrics">
                                <div className="mcq-lecture-exam-share">{Number(row.percentage || 0).toFixed(2)}% exam</div>
                                <div className="mcq-lecture-hours">{formatHours(row.recommended_hours)}</div>
                              </div>
                              <span className="mcq-lecture-expand-arrow">
                                {detailsAvailable ? (rowExpanded ? '▲' : '▼') : ''}
                              </span>
                            </button>
                            {detailsAvailable && rowExpanded && (
                              <div className="mcq-lecture-row-details">
                                <div className="mcq-lecture-why">{getExamWeightWhy(row.percentage)}</div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                    <h6>Daily Study Schedule</h6>
                    <div className="mcq-day-timeline">
                          {(studyPlanData.daily_schedule || []).map((row, i) => {
                            const dayPlan = formatBaselineDayPlan(row, percentageDf);
                        const lectureLine = dayPlan.lectureLines.length > 0
                          ? dayPlan.lectureLines.join('; ')
                          : formatDailyScheduleLectures(row.Lectures, percentageDf) || '—';
                        const dayKey = Number(row.Day || i + 1);
                        const isExpanded = expandedStudyDay === dayKey;
                            return (
                          <div key={i} className="mcq-day-timeline-item">
                            <button
                              type="button"
                              className="mcq-day-timeline-header mcq-day-accordion-header"
                              onClick={() => setExpandedStudyDay((prev) => (prev === dayKey ? null : dayKey))}
                              aria-expanded={isExpanded}
                            >
                              <span className="mcq-day-timeline-day">Day {row.Day}</span>
                              <span className="mcq-day-timeline-date">— {row.Date}</span>
                              <span className="mcq-day-hours-pill">{formatHours(row.Total_Hours)}</span>
                              <span className="mcq-day-accordion-arrow">{isExpanded ? '▲' : '▼'}</span>
                            </button>
                            {isExpanded && (
                              <div className="mcq-day-timeline-body">
                                <span className="mcq-day-timeline-dot" />
                                <div>
                                  <div className="mcq-day-timeline-lecture">{lectureLine}</div>
                                  <div className="mcq-day-timeline-focus"><strong>Focus:</strong> {humanizeFocusLine(dayPlan.focus)}</div>
                                  <div className="mcq-day-timeline-task"><strong>Task:</strong> Practice 5 questions + revise notes <i className="fas fa-check-circle mcq-validated-check"></i></div>
                                        </div>
                                      </div>
                                    )}
                                    </div>
                            );
                          })}
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
                <h2><i className="fas fa-star me-2"></i>Guided Practice Quiz</h2>
                <p className="mb-0">Practice questions from important lectures ({priorityQuestions.length} total).</p>
              </div>

              {priorityQuestions.length > 0 ? (
                <>
                  <div className="mcq-alert mcq-alert-info">
                    <h5><i className="fas fa-info-circle me-2"></i>Quick instructions</h5>
                    <ul className="mb-0">
                      <li>Answer all questions</li>
                      <li>Choose the best option (A/B/C/D)</li>
                      <li>Submit when all are answered</li>
                      <li>Each question includes a short reason</li>
                    </ul>
                  </div>

                  <div className="mcq-alert mcq-alert-info">
                    This quiz includes all lectures. High-priority lectures have more questions, while others ensure full syllabus coverage.
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

                  {highPriorityOrder.length > 0 && (
                    <div className="mcq-priority-group-section">
                      <h5 className="mcq-priority-group-heading">High Priority Lectures (Focus More)</h5>
                      {highPriorityOrder.map((p) => (
                    questionsByPriority[p]?.length > 0 && (
                      <div key={p} className={`mcq-priority-section priority-${p}`}>
                            <div className={`mcq-priority-header mcq-priority-${getPriorityColor(p)}`}>
                              <h5>
                                <i className={`fas fa-${getPriorityIcon(p)} me-2`}></i>
                                Priority {p} - {getFriendlyLectureLabel(
                                  questionsByPriority[p][0]?.lecture,
                                  questionsByPriority[p][0]?.lecture_title || lectureMetaByFile[questionsByPriority[p][0]?.lecture]?.title,
                                  lectureMetaByFile[questionsByPriority[p][0]?.lecture]?.topics || []
                                )}
                          </h5>
                        </div>
                        <div className="mcq-priority-body">
                          {questionsByPriority[p].map((q) => (
                            <div key={q.id} id={`mcq-question-${q.id}`} className={`mcq-question-item ${!quizAnswers[q.id] ? 'unanswered' : 'answered'}`}>
                              <div className="mcq-question-header">
                                <div className="mcq-question-header-left">
                                      <span className={`mcq-badge mcq-badge-${getPriorityColor(p)}`}>Question {q.question_number}</span>
                                      <span className="mcq-badge mcq-badge-danger">High Focus</span>
                                    </div>
                                    <small className="text-muted">
                                      {getFriendlyLectureLabel(
                                        q.lecture,
                                        lectureMetaByFile[q.lecture]?.title,
                                        lectureMetaByFile[q.lecture]?.topics || []
                                      )}
                                    </small>
                                  </div>
                                  <div className="mcq-quiz-topic-reason-block">
                                    <div className="mcq-quiz-topic-line">
                                      📘 Topic: {cleanTopicDisplayName(q.topic_name || 'General')}
                                    </div>
                                    <div className="mcq-quiz-reason-list">
                                      <strong>Why this question:</strong>
                                      <ul>
                                        {getQuizQuestionReasons(q).map((reason) => (
                                          <li key={reason}>{reason}</li>
                                        ))}
                                      </ul>
                                  </div>
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
                    </div>
                  )}

                  {coveragePriorityOrder.length > 0 && (
                    <div className="mcq-priority-group-section">
                      <h5 className="mcq-priority-group-heading">Coverage Lectures (Don&apos;t Ignore)</h5>
                      {coveragePriorityOrder.map((p) => (
                        questionsByPriority[p]?.length > 0 && (
                          <div key={p} className={`mcq-priority-section priority-${p}`}>
                            <div className={`mcq-priority-header mcq-priority-${getPriorityColor(p)}`}>
                              <h5>
                                <i className={`fas fa-${getPriorityIcon(p)} me-2`}></i>
                                Priority {p} - {getFriendlyLectureLabel(
                                  questionsByPriority[p][0]?.lecture,
                                  questionsByPriority[p][0]?.lecture_title || lectureMetaByFile[questionsByPriority[p][0]?.lecture]?.title,
                                  lectureMetaByFile[questionsByPriority[p][0]?.lecture]?.topics || []
                                )}
                              </h5>
                            </div>
                            <div className="mcq-priority-body">
                              {questionsByPriority[p].map((q) => (
                                <div key={q.id} id={`mcq-question-${q.id}`} className={`mcq-question-item ${!quizAnswers[q.id] ? 'unanswered' : 'answered'}`}>
                                  <div className="mcq-question-header">
                                    <div className="mcq-question-header-left">
                                      <span className={`mcq-badge mcq-badge-${getPriorityColor(p)}`}>Question {q.question_number}</span>
                                      <span className="mcq-badge mcq-badge-info">Coverage</span>
                                    </div>
                                    <small className="text-muted">
                                      {getFriendlyLectureLabel(
                                        q.lecture,
                                        lectureMetaByFile[q.lecture]?.title,
                                        lectureMetaByFile[q.lecture]?.topics || []
                                      )}
                                    </small>
                                  </div>
                                  <div className="mcq-quiz-topic-reason-block">
                                    <div className="mcq-quiz-topic-line">
                                      📘 Topic: {cleanTopicDisplayName(q.topic_name || 'General')}
                                    </div>
                                    <div className="mcq-quiz-reason-list">
                                      <strong>Why this question:</strong>
                                      <ul>
                                        {getQuizQuestionReasons(q).map((reason) => (
                                          <li key={reason}>{reason}</li>
                                        ))}
                                      </ul>
                                    </div>
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
                    </div>
                  )}

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
                    <h5><i className="fas fa-book me-2"></i>Scores by lecture</h5>
                    <details className="mcq-details-collapse">
                      <summary>Show full table</summary>
                    <div className="mcq-table-wrap">
                      <table className="mcq-table">
                        <thead>
                          <tr>
                            <th>Lecture</th>
                            <th>Total Questions</th>
                            <th>Correct</th>
                            <th>Wrong</th>
                            <th>Accuracy</th>
                              <th>Your score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(quizResults.topic_wise || {}).map(([topic, data]) => (
                            <tr key={topic}>
                              <td>
                                <strong>
                                  {getFriendlyLectureLabel(
                                    topic,
                                    lectureMetaByFile[topic]?.title,
                                    lectureMetaByFile[topic]?.topics || []
                                  )}
                                </strong>
                              </td>
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
                            <tr><td colSpan={6} className="text-center py-4"><p className="text-muted">No lecture-wise data available</p></td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                    </details>
                  </div>

                  <div className="mcq-table-card">
                    <h5><i className="fas fa-tags me-2"></i>Topics from your quiz</h5>
                    <h6 className="mcq-focus-now-heading">Focus Now</h6>
                    <p className="mcq-focus-now-helper">
                      Focus on the red topics first. These are selected from your quiz accuracy and have enough evidence from multiple questions.
                    </p>
                    <p className="mcq-focus-now-helper">These are topics where you need more practice based on your quiz.</p>
                    <p className="mcq-focus-now-action">Revise these topics first, then practice related MCQs.</p>
                    {progressFocusNowRows.length === 0 ? (
                      <p className="text-muted mcq-focus-now-empty">No topics meet the bar yet (under 50% with at least 2 questions).</p>
                    ) : (
                      <div className="mcq-table-wrap">
                        <table className="mcq-table">
                          <thead>
                            <tr>
                              <th>Topic</th>
                              <th>Correct</th>
                              <th>Total</th>
                              <th>Accuracy</th>
                              <th>Based on</th>
                              <th>Your Level</th>
                            </tr>
                          </thead>
                          <tbody>
                            {progressFocusNowRows.map((row) => (
                              <tr key={row.topic_name}>
                                <td><strong>{cleanTopicDisplayName(row.topic_name)}</strong></td>
                                <td className="text-center">{row.correct}</td>
                                <td className="text-center">{row.total}</td>
                                <td className="text-center">{row.accuracy.toFixed(1)}%</td>
                              <td className="mcq-evidence-cell">
                                Based on {row.total} question{row.total === 1 ? '' : 's'}
                              </td>
                              <td>
                                <span className="mcq-badge mcq-badge-danger">{formatPerformanceLevel(row.status)}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    )}

                    {progressOtherTopicRows.length > 0 && (
                      <details className="mcq-details-collapse mcq-other-topics-details">
                        <summary>Other topics</summary>
                        <div className="mcq-table-wrap">
                          <table className="mcq-table">
                            <thead>
                              <tr>
                                <th>Topic</th>
                                <th>Correct</th>
                                <th>Total</th>
                                <th>Accuracy</th>
                                <th>Based on</th>
                                <th>Your Level</th>
                              </tr>
                            </thead>
                            <tbody>
                              {progressOtherTopicRows.map((row) => (
                                <tr key={row.topic_name}>
                                  <td><strong>{cleanTopicDisplayName(row.topic_name)}</strong></td>
                                  <td className="text-center">{row.correct}</td>
                                  <td className="text-center">{row.total}</td>
                                  <td className="text-center">{row.accuracy.toFixed(1)}%</td>
                                  <td className="mcq-evidence-cell">
                                    Based on {row.total} question{row.total === 1 ? '' : 's'}
                                  </td>
                                  <td>
                                    <span
                                      className={`mcq-badge mcq-badge-${
                                        row.status.startsWith('weak')
                                          ? 'danger'
                                          : row.status.startsWith('strong')
                                            ? 'success'
                                            : 'warning'
                                      }`}
                                    >
                                      {formatPerformanceLevel(row.status)}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </details>
                    )}
                    {topicWeaknessRows.length === 0 && (
                      <p className="text-muted">No topic breakdown yet — complete the Priority Quiz first.</p>
                    )}
                  </div>

                  <div className="mcq-table-card">
                    <h5><i className="fas fa-book-open me-2"></i>Weak Topic Revision Summary</h5>
                    <p className="mcq-study-plan-hint">
                      These summaries are generated from your lecture content and quiz weak areas.
                    </p>
                    <p className="text-muted mb-2">
                      For best quality summaries, set <code>OPENAI_API_KEY</code> or <code>ANTHROPIC_API_KEY</code> in the backend environment.
                    </p>
                    {weakTopicSummary.length > 0 ? (
                      <div>
                        {weakTopicSummary.map((item) => (
                          <details key={item.topic} className="mcq-details-collapse">
                            <summary>{item.topic}</summary>
                            <p className="mb-2"><strong>Simple explanation:</strong> {item.simple_explanation}</p>
                            {(item.key_points || []).length > 0 && (
                              <>
                                <p className="mb-1"><strong>Key points to revise:</strong></p>
                                <ul className="mb-2">
                                  {item.key_points.map((kp, idx) => (
                                    <li key={`${item.topic}-kp-${idx}`}>{kp}</li>
                                  ))}
                                </ul>
                              </>
                            )}
                            {(item.common_mistakes || []).length > 0 && (
                              <>
                                <p className="mb-1"><strong>Common mistakes:</strong></p>
                                <ul className="mb-2">
                                  {item.common_mistakes.map((cm, idx) => (
                                    <li key={`${item.topic}-cm-${idx}`}>{cm}</li>
                                  ))}
                                </ul>
                              </>
                            )}
                            <p className="mb-0"><strong>Next action:</strong> {item.next_action}</p>
                          </details>
                        ))}
                      </div>
                    ) : (
                      <p className="text-muted mb-0">Complete the quiz to generate weak-topic revision summaries.</p>
                    )}
                  </div>

                  <div className="mcq-chart-card">
                    <h5><i className="fas fa-chart-bar me-2"></i>Your scores by lecture</h5>
                    {Object.keys(quizResults.topic_wise || {}).length > 0 ? (
                      <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={Object.entries(quizResults.topic_wise || {}).map(([topic, d]) => ({
                          name: getFriendlyLectureLabel(
                            topic,
                            lectureMetaByFile[topic]?.title,
                            lectureMetaByFile[topic]?.topics || []
                          ),
                          accuracy: d.accuracy || 0,
                        }))}>
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
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm mb-3"
                      onClick={() => setShowDetailedReview((v) => !v)}
                    >
                      {showDetailedReview ? 'Hide Detailed Question Review' : 'Show Detailed Question Review'}
                    </button>
                    {showDetailedReview && (
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
                              <td>
                                {getFriendlyLectureLabel(
                                  r.lecture,
                                  lectureMetaByFile[r.lecture]?.title,
                                  lectureMetaByFile[r.lecture]?.topics || []
                                )}
                              </td>
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
                    )}
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
              <div className="mcq-graph-context-card">
                <h6><i className="fas fa-user-graduate me-2"></i>Learning Status</h6>
                <p className="mb-1">
                  <strong>Weak topics:</strong>{' '}
                  {studentLearningContext.weak_topics_confirmed?.length
                    ? studentLearningContext.weak_topics_confirmed.slice(0, 5).join(', ')
                    : '—'}
                </p>
                <p className="mb-1">
                  <strong>Related topics:</strong>{' '}
                  {studentLearningContext.related_topics?.length
                    ? studentLearningContext.related_topics.slice(0, 5).map((t) => t.related_topic).filter(Boolean).join(', ')
                    : '—'}
                </p>
                <p className="mb-0">
                  <strong>Recommended MCQs:</strong> {studentLearningContext.recommended_mcqs?.length || 0}
                </p>
              </div>

              <div className="mcq-graph-student-summary">
                <h6><i className="fas fa-compass me-2"></i>What should you do now?</h6>
                <ol className="mb-0">
                  <li>Revise weak topics</li>
                  <li>Practice recommended MCQs</li>
                  <li>Retake quiz</li>
                </ol>
              </div>

              {graphUrl ? (
                <>
                  <div className="mcq-graph-legend">
                    <span><i className="fas fa-circle text-danger me-1"></i>Red: weak topics</span>
                    <span><i className="fas fa-circle text-warning me-1"></i>Orange: related concepts</span>
                    <span><i className="fas fa-circle text-primary me-1"></i>Blue: practice MCQs</span>
                    <span><i className="fas fa-mouse-pointer me-1"></i>Click blue for full question + reason</span>
                  </div>
                  <div className="mcq-graph-flow-line">
                    <strong>Learning Flow:</strong> Weak Topic <i className="fas fa-arrow-right mx-1"></i> Related Concept <i className="fas fa-arrow-right mx-1"></i> Practice MCQ <i className="fas fa-arrow-right mx-1"></i> Explanation
                  </div>
                  <div className="mcq-graph-card">
                    <h5><i className="fas fa-map me-2"></i>Graph Visualization</h5>
                    <p className="text-muted mb-2">This shows what you are weak in and what to practice next.</p>
                    <div className="mcq-graph-iframe-wrap">
                      <iframe key={graphUrl} src={graphUrl} title="Study map and practice graph" width="100%" height="100%" frameBorder="0" style={{ minHeight: 'calc(100vh - 300px)', width: '100%', height: 'calc(100vh - 300px)' }} />
                    </div>
                    <div className="mcq-graph-footer">
                      <small><i className="fas fa-info-circle me-1"></i>Hover nodes for tips. Drag to pan, scroll to zoom.</small>
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
                    <p className="mb-0">A study schedule shaped by your quiz — more time where you need it</p>
                  </div>
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
                    <div className="mcq-stats-card bg-gradient-danger">
                      <div className="mcq-stats-body">
                        <div><h6>Main weak topic</h6><h5>{adaptiveNowAction.focusFirst || 'Take quiz to detect'}</h5></div>
                        <div className="mcq-stats-icon"><i className="fas fa-bullseye fa-3x"></i></div>
                      </div>
                    </div>
                      </div>

                  <div className="mcq-adaptive-action-box">
                    <h5>What should you do now?</h5>
                    <ol className="mb-0">
                      <li>Revise weak topics</li>
                      <li>Practice MCQs</li>
                      <li>Recheck your progress</li>
                    </ol>
                    </div>

                  <div className="mcq-adaptive-tier-card">
                    <h5 className="mb-3">Your performance by topic</h5>
                    <div className="mcq-tier-grid">
                      <div className="mcq-tier-block mcq-tier-weak">
                        <h6>Focus first</h6>
                        <p className="mcq-tier-list">
                          {adaptiveTopicTiers.weak.length
                            ? adaptiveTopicTiers.weak.slice(0, 5).join(', ')
                            : '—'}
                        </p>
                      </div>
                      <div className="mcq-tier-block mcq-tier-moderate">
                        <h6>Practice more</h6>
                        <p className="mcq-tier-list">
                          {adaptiveTopicTiers.moderate.length
                            ? adaptiveTopicTiers.moderate.slice(0, 5).join(', ')
                            : '—'}
                        </p>
                      </div>
                      <div className="mcq-tier-block mcq-tier-strong">
                        <h6>Keep revising</h6>
                        <p className="mcq-tier-list">
                          {adaptiveTopicTiers.strong.length
                            ? adaptiveTopicTiers.strong.slice(0, 5).join(', ')
                            : '—'}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mcq-graphrag-adaptive-card">
                    <h5><i className="fas fa-project-diagram me-2"></i>Related topics you should revise next</h5>
                    <p className="mb-1"><strong>Weak topics (quiz)</strong></p>
                    <p className="mcq-graphrag-adaptive-text">
                      {adaptiveGraphragNarrative.weakShow.length
                        ? adaptiveGraphragNarrative.weakShow.join(', ')
                        : '— Complete the quiz to list weak topics here.'}
                    </p>
                    <p className="mb-1 mt-2"><strong>Related topics to revise</strong></p>
                    {adaptiveGraphragNarrative.links.length ? (
                      <ul className="mcq-graphrag-link-list mb-2">
                        {adaptiveGraphragNarrative.links.slice(0, 5).map((l, idx) => (
                          <li key={`${l.from_weak}-${l.related_concept}-${idx}`}>
                            <strong>{l.from_weak}</strong> → {l.related_concept}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mcq-graphrag-adaptive-text mb-2">— Run <strong>Dashboard → Run Analysis</strong> after your quiz to refresh related topic suggestions.</p>
                    )}
                  </div>

                  {comparisonChartData.length > 0 && (
                    <details className="mcq-details-collapse">
                      <summary>View hour changes</summary>
                    <div className="mcq-chart-card">
                        <h5><i className="fas fa-chart-bar me-2"></i>Study hours: starting plan vs adjusted plan</h5>
                      <ResponsiveContainer width="100%" height={350}>
                        <BarChart data={comparisonChartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="shortLecture" />
                          <YAxis />
                          <Tooltip 
                            formatter={(value, name) => [
                              formatHours(value), 
                              name === 'baseline' ? 'Baseline' : 'Adaptive'
                            ]}
                              labelFormatter={(_, payload) => {
                                const lec = payload?.[0]?.payload?.lecture;
                                if (!lec) return '';
                                return getFriendlyLectureLabel(
                                  lec,
                                  lectureMetaByFile[lec]?.title,
                                  lectureMetaByFile[lec]?.topics || []
                                );
                              }}
                          />
                          <Legend 
                            formatter={(value) => value === 'baseline' ? 'Baseline Hours' : 'Adaptive Hours'}
                          />
                          <Bar dataKey="baseline" fill="#a8c7fa" name="baseline" />
                          <Bar dataKey="adaptive" fill="#f4e4a1" name="adaptive" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    </details>
                  )}

                  <details className="mcq-details-collapse">
                    <summary>View lecture plan details</summary>
                  <div className="mcq-table-card">
                    <h5><i className="fas fa-table me-2"></i>Adaptive Study Plan Details</h5>
                    <div className="mcq-table-wrap">
                      <table className="mcq-table">
                        <thead>
                          <tr>
                            <th>Priority</th>
                            <th>Lecture</th>
                            <th>Adaptive Hours</th>
                              <th>Focus level</th>
                              <th>Why</th>
                          </tr>
                        </thead>
                        <tbody>
                            {(adaptivePlan.adaptive_plan || []).map((row, i) => {
                              const reasonInfo = getAdaptiveReason(row, lectureMetaByFile);
                              return (
                            <tr key={i}>
                              <td><span className="mcq-badge mcq-badge-primary">{`Priority ${i + 1}`}</span></td>
                              <td><strong>{getFriendlyLectureLabel(row.Lecture, lectureMetaByFile[row.Lecture]?.title, lectureMetaByFile[row.Lecture]?.topics || [])}</strong></td>
                              <td className="text-center">
                                <span className={`mcq-badge mcq-badge-${row.Adaptive_Hours > row.Baseline_Hours ? 'success' : 'warning'}`}>
                                  {formatHours(Number(row.Adaptive_Hours))}
                                </span>
                              </td>
                              <td>
                                <span className={`mcq-badge mcq-badge-${(row.Focus_Intensity || '').includes('High') ? 'danger' : (row.Focus_Intensity || '').includes('Medium') ? 'warning' : 'info'}`}>
                                  {row.Focus_Intensity}
                                </span>
                              </td>
                                <td className="mcq-adaptive-reason-cell">
                                  <div className="mcq-adaptive-reason-main">
                                    {reasonInfo.reason}
                                  </div>
                                  <div className="mcq-adaptive-reason-action">
                                    Next: {reasonInfo.action}
                                  </div>
                                </td>
                            </tr>
                            )})}
                          {(!adaptivePlan.adaptive_plan || adaptivePlan.adaptive_plan.length === 0) && (
                              <tr><td colSpan={5} className="text-center py-4"><p className="text-muted">No adaptive study plan data available</p></td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  </details>

                  {adaptiveDailySchedule.length > 0 && (
                    <div className="mcq-table-card mcq-adaptive-daily-card">
                      <h5><i className="fas fa-calendar-check me-2"></i>Daily adaptive schedule</h5>
                      {adaptiveDailySchedule.length > 0 && (
                        <div className="mcq-adaptive-day-cards">
                          {adaptiveDailySchedule.map((day) => (
                            <details key={`${day.day}-${day.date}`} className="mcq-adaptive-day-card" open={day.day === 1}>
                              <summary className="mcq-adaptive-day-title">Day {day.day}: <span>{day.date}</span></summary>
                              {day.segments.map((seg, idx) => (
                                <ul key={`${day.day}-${idx}`} className="mcq-day-plan-bullets">
                                  <li><strong>Lecture:</strong> {seg.friendlyLecture}</li>
                                  <li className="mcq-adaptive-day-focus-line"><strong>Focus topic:</strong> {humanizeFocusLine(seg.focus)}</li>
                                  <li className="mcq-adaptive-day-task-line"><strong>Task:</strong> Revise → Practice 5 MCQs → Review mistakes</li>
                                </ul>
                              ))}
                            </details>
                          ))}
                        </div>
                      )}
                      <details className="mcq-details-collapse mcq-adaptive-daily-details">
                        <summary>Hour-by-hour breakdown (optional)</summary>
                      <div className="mcq-table-wrap">
                        <table className="mcq-table mcq-table-sm mcq-adaptive-daily-table">
                          <thead>
                            <tr>
                              <th>Day</th>
                              <th>Date</th>
                              <th>Lecture</th>
                                <th>Focus</th>
                                <th>Task</th>
                              <th>Hours</th>
                            </tr>
                          </thead>
                          <tbody>
                            {adaptiveDailySchedule.flatMap((day) =>
                              day.segments.map((seg, j) => (
                                <tr key={`${day.day}-${day.date}-${j}`}>
                                  <td>Day {day.day}</td>
                                  <td>{day.date}</td>
                                  <td>
                                      {seg.lectureFile ? (
                                        <strong>{seg.friendlyLecture}</strong>
                                      ) : (
                                        <strong className="mcq-free-revision-label">{seg.friendlyLecture}</strong>
                                      )}
                                  </td>
                                    <td className="mcq-adaptive-daily-focus">{humanizeFocusLine(seg.focus)}</td>
                                  <td className="mcq-adaptive-daily-task">{seg.task}</td>
                                  <td className="text-center">{formatHours(Number(seg.hours))}</td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                      </details>
                    </div>
                  )}

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
                <p className="mcq-hint">Open Progress → Generate Adaptive Study Plan to build your personalized schedule.</p>
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
                    <h4>How this plan is created:</h4>
                    <ul className="mcq-how-plan-lines mb-0">
                      <li>Weak topics are identified from your quiz</li>
                      <li>More time is given to low-scoring areas</li>
                      <li>Study time is balanced across all lectures</li>
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
