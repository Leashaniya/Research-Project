// MCQ Study Plan API - use /mcq when behind gateway (like /papers, /guidance)
// Or VITE_MCQ_API_URL for direct FastAPI (e.g. http://localhost:8002)
const API_BASE_URL = (import.meta as unknown as { env?: { VITE_MCQ_API_URL?: string } }).env?.VITE_MCQ_API_URL || '/mcq';

export interface DashboardStats {
  total_lectures: number;
  total_questions: number;
  total_topics?: number;
  avg_questions_per_lecture: number;
  high_priority_lectures: number;
  study_completion_percentage: number;
  processed?: boolean;
}

export interface PercentageRow {
  Lecture_File: string;
  Lecture_Title?: string;
  Questions_In_Lecture: number;
  Percentage_of_Total: number;
  Cumulative_Percentage?: number;
}

export interface AnalysisResponse {
  success: boolean;
  stats: DashboardStats;
  question_distribution_count?: number;
  total_lectures?: number;
  total_questions?: number;
  percentage_df?: any[];
  message: string;
  /** True when results were read from disk cache (same PDFs / config as last run). */
  from_cache?: boolean;
}

export interface StudyPlanItem {
  priority: number;
  lecture: string;
  focus_intensity: string;
  recommended_hours: number;
  questions: number;
  percentage: number;
}

export interface DailyScheduleItem {
  Day: number;
  Date: string;
  Lectures: string;
  Total_Hours: number;
  Target?: string;
}

export interface QuizQuestion {
  id: string;
  question: string;
  options: string[];
  answer: string;
  lecture: string;
  lecture_title?: string;
  priority: number;
  question_number: number;
}

export interface QuizResults {
  total_attempted: number;
  correct_count: number;
  wrong_count: number;
  accuracy: number;
  topic_wise: Record<string, { correct: number; total: number; accuracy: number }>;
  detailed_results: Array<{
    question_id: string;
    student_answer: string;
    correct_answer: string;
    is_correct: boolean;
    lecture: string;
  }>;
  accuracy_by_lecture?: Record<string, number>;
  overall_accuracy?: number;
}

export interface AdaptivePlanItem {
  Priority: number;
  Lecture: string;
  Baseline_Hours: number;
  Adaptive_Hours: number;
  Delta_Hours: number;
  Quiz_Accuracy: string;
  Mastery_Gap: string;
  Focus_Intensity: string;
}

export interface AdaptivePlanResponse {
  success: boolean;
  adaptive_plan: AdaptivePlanItem[];
  adaptive_daily: DailyScheduleItem[];
  params: {
    total_hours: number;
    study_days: number;
    alpha: number;
    max_increase: number;
    max_decrease: number;
  };
}

export interface WeakTopicSummaryItem {
  topic: string;
  simple_explanation: string;
  key_points: string[];
  common_mistakes: string[];
  next_action: string;
}

/**
 * Health check / backend availability
 */
export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/dashboard/`);
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Get dashboard statistics
 */
export async function getDashboardStats(): Promise<DashboardStats> {
  const response = await fetch(`${API_BASE_URL}/api/dashboard/stats`);
  if (!response.ok) {
    throw new Error(`Dashboard stats API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

function resolveMcqUserId(explicit?: string): string {
  if (explicit && explicit.trim()) return explicit.trim();
  try {
    const fromStorage = typeof localStorage !== 'undefined' ? localStorage.getItem('mcq_user_id') : null;
    if (fromStorage && fromStorage.trim()) return fromStorage.trim();
  } catch {
    /* ignore */
  }
  return 'default';
}

/**
 * Run analysis on lecture materials. Uses `mcq_user_id` in localStorage when set,
 * or pass `userId` for per-account disk cache (backend stores under data/{user_id}/).
 */
export async function runAnalysis(userId?: string): Promise<AnalysisResponse> {
  const uid = encodeURIComponent(resolveMcqUserId(userId));
  const response = await fetch(`${API_BASE_URL}/api/dashboard/analyze?user_id=${uid}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const msg = data.detail || data.message || data.error || `Analysis API error: ${response.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  if (data.success === false) {
    throw new Error(data.message || "Analysis failed");
  }
  return data;
}

export interface StudyPlanResponse {
  plan: StudyPlanItem[];
  daily_schedule: DailyScheduleItem[];
  total_hours: number;
  study_days: number;
}

/**
 * Get study plan
 */
export async function getStudyPlan(totalHours: number, studyDays: number): Promise<StudyPlanResponse> {
  const response = await fetch(`${API_BASE_URL}/api/study-plan/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      total_hours: totalHours,
      study_days: studyDays,
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const msg = err.detail || err.error || err.message || `Study plan API error: ${response.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return response.json();
}

/**
 * Get study plan PDF download URL
 */
export function getStudyPlanPdfUrl(totalHours: number, studyDays: number): string {
  return `${API_BASE_URL}/api/study-plan/download-pdf?total_hours=${totalHours}&study_days=${studyDays}`;
}

/**
 * Get priority questions for quiz
 */
export async function getPriorityQuestions(): Promise<QuizQuestion[]> {
  const response = await fetch(`${API_BASE_URL}/api/priority-questions`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const msg = err.detail || err.error || err.message || `Priority questions API error: ${response.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return response.json();
}

/**
 * Submit quiz answers and get results
 */
export async function submitQuiz(
  answers: Record<string, string>,
  correctAnswers: Record<string, string>
): Promise<QuizResults> {
  const response = await fetch(`${API_BASE_URL}/api/quiz/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers, correct_answers: correctAnswers }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const msg = err.detail || err.error || err.message || `Quiz submit API error: ${response.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return response.json();
}

/**
 * Generate adaptive study plan from quiz results
 */
export async function generateAdaptivePlan(
  quizResults: QuizResults,
  totalHours: number = 20,
  studyDays: number = 7,
  alpha: number = 0.5,
  maxIncrease: number = 0.3,
  maxDecrease: number = 0.15
): Promise<AdaptivePlanResponse> {
  const response = await fetch(`${API_BASE_URL}/api/adaptive-plan/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      quiz_results: quizResults,
      total_hours: totalHours,
      study_days: studyDays,
      alpha,
      max_increase: maxIncrease,
      max_decrease: maxDecrease,
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const msg = err.detail || err.message || err.error || `Adaptive plan API error: ${response.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return response.json();
}

/**
 * Get graph URL for iframe
 */
export async function getGraphUrl(): Promise<string | null> {
  const response = await fetch(`${API_BASE_URL}/api/graph/url`);
  const data = await response.json();
  return data.url ? `${API_BASE_URL}${data.url}` : null;
}

export interface GraphConceptLink {
  from_weak: string;
  related_concept: string;
  link_type?: string;
}

export interface StudentLearningContext {
  weak_topics_confirmed: string[];
  topic_accuracy: Array<{
    topic_name: string;
    accuracy: number;
    total: number;
    band: string;
  }>;
  priority_lectures: string[];
  related_topics: Array<{
    weak_topic: string;
    related_topic: string;
    link_type?: string;
  }>;
  recommended_mcqs: Array<{
    question_id: string;
    score?: number;
  }>;
  study_plan_settings: {
    total_hours: number | null;
    study_days: number | null;
    alpha?: number | null;
    max_increase?: number | null;
    max_decrease?: number | null;
  };
  quiz_accuracy_overall: number;
  updated_at: string;
}

export interface GraphStudentContextResponse {
  available: boolean;
  student_learning_context?: StudentLearningContext;
  weak_topics_confirmed?: string[];
  related_concept_links?: GraphConceptLink[];
  student_map_summary?: {
    weak_topics?: string[];
    related_concepts?: string[];
    practice_count?: number;
    uses_graphrag_topic_links?: boolean;
  };
  uses_confirmed_weak_topics?: boolean;
  meta?: Record<string, unknown>;
}

/**
 * Last saved GraphRAG summary (written when the learning-map HTML is built).
 */
export async function getGraphStudentContext(): Promise<GraphStudentContextResponse> {
  const response = await fetch(`${API_BASE_URL}/api/graph/student-context`);
  if (!response.ok) {
    return { available: false, meta: {}, related_concept_links: [] };
  }
  return response.json();
}

/**
 * Get lecture distribution (for charts)
 */
export async function getLectureDistribution(): Promise<PercentageRow[]> {
  const response = await fetch(`${API_BASE_URL}/api/dashboard/lecture-distribution`);
  if (!response.ok) return [];
  return response.json();
}

export async function getWeakTopicSummary(): Promise<WeakTopicSummaryItem[]> {
  const response = await fetch(`${API_BASE_URL}/api/weak-topic-summary`);
  if (!response.ok) return [];
  const data = await response.json().catch(() => ({}));
  return (data.weak_topic_summary || []) as WeakTopicSummaryItem[];
}
