import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '/guidance';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const getToken = useCallback(() => {
    return localStorage.getItem('authToken');
  }, []);

  const setToken = useCallback((token) => {
    if (token) {
      localStorage.setItem('authToken', token);
    } else {
      localStorage.removeItem('authToken');
    }
  }, []);

  const checkAuth = useCallback(async () => {
    const token = getToken();
    const headers = token ? { Authorization: `Bearer ${token}` } : {};

    try {
      const response = await fetch(`${API_URL}/guidance/auth/me`, {
        credentials: 'include',
        headers,
      });
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else {
        setUser(null);
        if (token) {
          setToken(null);
        }
      }
    } catch {
      setUser(null);
      setToken(null);
    } finally {
      setLoading(false);
    }
  }, [getToken, setToken]);

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    if (token) {
      setToken(token);
      const cleanUrl = window.location.pathname + window.location.hash;
      window.history.replaceState({}, document.title, cleanUrl);
    }
    checkAuth();
  }, [checkAuth, setToken]);

  const login = useCallback(() => {
    window.location.href = `${API_URL}/guidance/auth/login`;
  }, []);

  const logout = useCallback(async () => {
    try {
      const token = getToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      await fetch(`${API_URL}/guidance/auth/logout`, {
        method: 'POST',
        credentials: 'include',
        headers,
      });
    } catch (e) {
      console.error('Logout error:', e);
    }
    setUser(null);
    setToken(null);
    window.location.href = '/';
  }, [getToken, setToken]);

  const value = {
    user,
    loading,
    setUser,
    login,
    logout,
    checkAuth,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
