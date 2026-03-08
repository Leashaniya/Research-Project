import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './DashboardHome.css';
import './DashboardHomeMCQ.css';

const API_URL = import.meta.env.VITE_API_URL || '/guidance';

export default function DashboardHome() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);

  useEffect(() => {
    const checkUser = async () => {
      try {
        const response = await fetch(`${API_URL}/auth/me`, { credentials: 'include' });
        if (response.ok) {
          const userData = await response.json();
          setUser(userData);
        }
      } catch (error) {
        console.error('Error checking user status:', error);
      }
    };
    checkUser();
  }, []);

  const handleGoogleLogin = () => {
    window.location.href = `${API_URL}/auth/login`;
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
      setUser(null);
      // Redirect so ProtectedRoute remounts and shows sign-in gate; services become hidden
      window.location.href = '/';
    } catch (error) {
      console.error('Error logging out:', error);
    }
  };

  return (
    <div className="dashboard-page">
      <div className="dashboard-container">
        <header className="dashboard-header">
          <h1 className="dashboard-title">Academic Assistance Dashboard</h1>
          <p className="dashboard-subtitle">
            Choose a service to get started
          </p>

          {user ? (
            <div className="dashboard-user">
              <div className="dashboard-user-info">
                {user.picture ? (
                  <img src={user.picture} alt="" className="dashboard-user-avatar" />
                ) : (
                  <div className="dashboard-user-avatar dashboard-user-avatar-initial">
                    {user.name ? user.name.charAt(0).toUpperCase() : 'U'}
                  </div>
                )}
                <span className="dashboard-user-name">
                  Signed in as <strong>{user.name || user.email || 'User'}</strong>
                </span>
              </div>
              <button type="button" className="btn-dashboard-logout" onClick={handleLogout}>
                Logout
              </button>
            </div>
          ) : (
            <button type="button" className="btn-google-login" onClick={handleGoogleLogin}>
              Sign in with Google
            </button>
          )}
        </header>

        <div className="dashboard-cards">

          {/* CA Guidance */}
          <div className="dashboard-card" onClick={() => navigate('/ca-guidance')}>
            <div className="card-icon">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h2 className="card-title">Educational Support</h2>
            <p className="card-description">
              Get personalized guidance, summaries, flashcards, and study recommendations
              for your Continuous Assessment topics.
            </p>
            <button type="button" className="card-button">Enter Educational Support</button>
          </div>

          {/* Model Paper */}
          <div className="dashboard-card" onClick={() => navigate('/model-paper')}>
            <div className="card-icon">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M14 2V8H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M16 13H8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M16 17H8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M10 9H9H8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h2 className="card-title">Model Paper</h2>
            <p className="card-description">
              Generate AI-powered model exam papers with aligned short notes
              based on past papers and lecture materials.
            </p>
            <button type="button" className="card-button">Enter Model Paper</button>
          </div>

          {/* MCQ Study Plan - React */}
          <div 
            className="dashboard-card"
            onClick={() => navigate('/mcq-study-plan')}
          >
            <div className="card-icon bg-gradient-mcq">
              🎯
            </div>
            <h2 className="card-title">MCQ Study Plan</h2>
            <p className="card-description">
              Generate adaptive study plans from lecture materials, analyze question patterns,
              and get personalized MCQ recommendations with progress tracking.
            </p>
            <button 
              type="button" 
              className="card-button btn-mcq"
              onClick={() => navigate('/mcq-study-plan')}
            >
              Enter MCQ Study Plan
            </button>
          </div>

          <div className="dashboard-card" onClick={() => navigate('/essay-support')}>
            <div className="card-icon">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M6.5 2H20V22H6.5A2.5 2.5 0 0 1 4 19.5V4.5A2.5 2.5 0 0 1 6.5 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M8 7H16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M8 11H14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h2 className="card-title">Essay Support</h2>
            <p className="card-description">
              Practice with AI-powered adaptive questions extracted from your PDFs.
              Get instant feedback and track your progress with reinforcement learning.
            </p>
            <button type="button" className="card-button">Enter Essay Support</button>
          </div>
        </div>

        <footer className="dashboard-footer">
          <p>Select a service above to begin</p>
        </footer>
      </div>
    </div>
  );
}