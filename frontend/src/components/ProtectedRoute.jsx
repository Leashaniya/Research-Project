import { Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './ProtectedRoute.css';

/**
 * Protects all service routes: user must be signed in with Google before accessing
 * the dashboard, CA guidance, model paper, essay support, or MCQ study plan.
 * First-page design: hero-style welcome, distinct from dashboard cards.
 */
export default function ProtectedRoute() {
  const { user, loading, login } = useAuth();

  if (loading) {
    return (
      <div className="protected-route-loading">
        <div className="protected-route-loading-bg" aria-hidden="true" />
        <div className="protected-route-spinner" aria-hidden="true" />
        <p>Checking sign-in…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="protected-route-gate">
        <div className="protected-route-bg" aria-hidden="true">
          <span className="protected-route-blob protected-route-blob-1" />
          <span className="protected-route-blob protected-route-blob-2" />
          <span className="protected-route-blob protected-route-blob-3" />
          <span className="protected-route-blob protected-route-blob-4" />
        </div>
        <div className="protected-route-wave" aria-hidden="true">
          <svg viewBox="0 0 1440 120" fill="none" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">
            <path d="M0 120L48 105C96 90 192 60 288 45C384 30 480 30 576 37.5C672 45 768 60 864 67.5C960 75 1056 75 1152 67.5C1248 60 1344 45 1392 37.5L1440 30V120H1392C1344 120 1248 120 1152 120C1056 120 960 120 864 120C768 120 672 120 576 120C480 120 384 120 288 120C192 120 96 120 48 120H0Z" fill="currentColor"/>
          </svg>
        </div>

        <main className="protected-route-content">
          <div className="protected-route-badge">Welcome</div>
          <h1 className="protected-route-title">
            Academic Assistance
          </h1>
          <p className="protected-route-tagline">
            Your learning companion for guidance, summaries, model papers and more. Sign in to get started.
          </p>
          <button type="button" className="protected-route-btn-login" onClick={login}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Sign in with Google
          </button>
        </main>
      </div>
    );
  }

  return <Outlet />;
}
