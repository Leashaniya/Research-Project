/**
 * helpers.js — small UI utilities used across components.
 */

export function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

export function getDifficultyColor(level) {
  switch (level?.toLowerCase()) {
    case 'easy':   return 'var(--success)';
    case 'medium': return 'var(--warning)';
    case 'hard':   return 'var(--danger)';
    default:       return 'var(--text-muted)';
  }
}

export function getScoreColor(score) {
  if (score >= 80) return 'var(--success)';
  if (score >= 50) return 'var(--warning)';
  return 'var(--danger)';
}

export function getScoreClass(score) {
  if (score >= 80) return 'score-high';
  if (score >= 50) return 'score-mid';
  return 'score-low';
}

export function getRewardLabel(reward) {
  if (reward >= 1)    return { text: 'Excellent', color: 'var(--success)' };
  if (reward >= 0.5)  return { text: 'Good',      color: 'var(--warning)' };
  return               { text: 'Needs work',      color: 'var(--danger)' };
}

export function truncate(str, max = 120) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '…' : str;
}
