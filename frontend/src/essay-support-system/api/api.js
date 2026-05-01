/**
 * api.js — Centralised HTTP helpers for the Adaptive Learning System.
 *
 * Session management
 * ------------------
 * A UUID is stored in localStorage under "als_session_id" and sent
 * as the X-Session-Id header with every request.
 *
 * Every exported function mirrors an endpoint in backend/main.py.
 */

const BASE = '/essay/api';

/* ── Session helpers ── */

function getSessionId() {
  return localStorage.getItem('als_session_id') || '';
}

function setSessionId(id) {
  localStorage.setItem('als_session_id', id);
}

/* ── Generic request wrapper ── */

async function request(path, { method = 'GET', body = null } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const sid = getSessionId();
  if (sid) headers['X-Session-Id'] = sid;

  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  const data = await res.json();

  // Auto-persist session id returned by the server
  if (data.session_id) setSessionId(data.session_id);

  // Pages check `data.success` — inject it for every ok response
  return { success: true, ...data };
}

/* ── API methods ── */

const api = {
  healthCheck:   ()                              => request('/health'),
  startSession:  (diff)                          => request('/sessions/start',  { method: 'POST', body: { difficulty: diff || 'easy' } }),
  resetSession:  ()                              => request('/sessions/reset',  { method: 'POST', body: {} }),
  getQuestion:   (diff)                          => request('/questions/next',  { method: 'POST', body: { difficulty: diff || null } }),
  submitAnswer:  (payload) => {
    // Handle both individual and batch submissions
    if (payload.batch_mode) {
      // Batch submission
      return request('/answers/submit', { 
        method: 'POST', 
        body: {
          answers: payload.answers,
          questions: payload.questions,
          topic: payload.topic,
          difficulty: payload.difficulty,
          batch_mode: true
        }
      });
    } else {
      // Individual submission (backward compatibility)
      return request('/answers/submit', { 
        method: 'POST', 
        body: { 
          answer: payload.answer, 
          question: payload.question, 
          difficulty: payload.difficulty 
        }
      });
    }
  },
  evaluatePracticeAnswers: (data)                => request('/practice/evaluate', { method: 'POST', body: data }),
  getStats:      ()                              => request('/stats'),
  checkPdfs:     ()                              => request('/pdfs/check'),
  getHistory:    ()                              => request('/history'),
  getAnalytics:  ()                              => request('/analytics/overview'),
};

export default api;
