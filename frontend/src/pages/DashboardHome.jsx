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
              📘
            </div>
            <h2 className="card-title">CA Guidance</h2>
            <p className="card-description">
              Get personalized guidance, summaries, flashcards, and study recommendations
              for your Continuous Assessment topics.
            </p>
            <button type="button" className="card-button">
              Enter CA Guidance
            </button>
          </div>

          {/* Model Paper */}
          <div className="dashboard-card" onClick={() => navigate('/model-paper')}>
            <div className="card-icon">
              📝
            </div>
            <h2 className="card-title">Model Paper</h2>
            <p className="card-description">
              Generate AI-powered model exam papers with aligned short notes
              based on past papers and lecture materials.
            </p>
            <button type="button" className="card-button">
              Enter Model Paper
            </button>
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

        </div>

        <footer className="dashboard-footer">
          <p>Select a service above to begin</p>
        </footer>
      </div>
    </div>
  );
}