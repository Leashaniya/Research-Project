import React from 'react';
import './App.css';

// Configuration for frontend URLs
const FRONTEND_URLS = {
  CA_GUIDANCE: process.env.REACT_APP_CA_GUIDANCE_URL || 'http://localhost:3333',
  MODEL_PAPER: process.env.REACT_APP_MODEL_PAPER_URL || 'http://localhost:3000'
};

function App() {
  const handleCAGuidanceClick = () => {
    window.location.href = FRONTEND_URLS.CA_GUIDANCE;
  };

  const handleModelPaperClick = () => {
    window.location.href = FRONTEND_URLS.MODEL_PAPER;
  };

  return (
    <div className="App">
      <div className="dashboard-container">
        <header className="dashboard-header">
          <h1 className="dashboard-title">Academic Assistance Dashboard</h1>
          <p className="dashboard-subtitle">
            Choose a service to get started
          </p>
        </header>

        <div className="dashboard-cards">
          <div className="dashboard-card" onClick={handleCAGuidanceClick}>
            <div className="card-icon">
              <svg
                width="64"
                height="64"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M12 2L2 7L12 12L22 7L12 2Z"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M2 17L12 22L22 17"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M2 12L12 17L22 12"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <h2 className="card-title">CA Guidance</h2>
            <p className="card-description">
              Get personalized guidance, summaries, flashcards, and study recommendations
              for your Continuous Assessment topics.
            </p>
            <button className="card-button">Enter CA Guidance</button>
          </div>

          <div className="dashboard-card" onClick={handleModelPaperClick}>
            <div className="card-icon">
              <svg
                width="64"
                height="64"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M14 2V8H20"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M16 13H8"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M16 17H8"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M10 9H9H8"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <h2 className="card-title">Model Paper</h2>
            <p className="card-description">
              Generate AI-powered model exam papers with aligned short notes
              based on past papers and lecture materials.
            </p>
            <button className="card-button">Enter Model Paper</button>
          </div>
        </div>

        <footer className="dashboard-footer">
          <p>Select a service above to begin</p>
        </footer>
      </div>
    </div>
  );
}

export default App;
