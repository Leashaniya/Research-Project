import { createContext, useContext, useState, useCallback } from 'react';
import api from '../api/api';

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  const [session, setSession] = useState({
    id: localStorage.getItem('als_session_id') || null,
    difficulty: 'easy',
    attempts: 0,
    averageScore: 0,
    totalScore: 0,
    scoreHistory: [],
    active: false,
  });

  const startSession = useCallback(async (difficulty = 'easy') => {
    const data = await api.startSession(difficulty);
    setSession((prev) => ({
      ...prev,
      id: data.session_id,
      difficulty: data.difficulty,
      attempts: 0,
      averageScore: 0,
      totalScore: 0,
      scoreHistory: [],
      active: true,
    }));
    return data;
  }, []);

  const resetSession = useCallback(async () => {
    const data = await api.resetSession();
    setSession((prev) => ({
      ...prev,
      id: data.session_id,
      difficulty: 'easy',
      attempts: 0,
      averageScore: 0,
      totalScore: 0,
      scoreHistory: [],
      active: false,
    }));
    return data;
  }, []);

  const updateFromResult = useCallback((result) => {
    setSession((prev) => {
      const attempts = prev.attempts + 1;
      const totalScore = prev.totalScore + (result.score || 0);
      const averageScore = Math.round((totalScore / attempts) * 10) / 10;
      return {
        ...prev,
        difficulty: result.next_difficulty || prev.difficulty,
        attempts,
        totalScore,
        averageScore,
        scoreHistory: [
          ...prev.scoreHistory,
          {
            attempt: attempts,
            score: result.score,
            difficulty: result.next_difficulty || prev.difficulty,
            reward: result.reward,
          },
        ],
      };
    });
  }, []);

  return (
    <SessionContext.Provider
      value={{ session, startSession, resetSession, updateFromResult }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be inside <SessionProvider>');
  return ctx;
}
