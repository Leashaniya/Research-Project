import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  FaGraduationCap,
  FaFileAlt,
  FaBook,
  FaFilePdf,
  FaRocket,
  FaClipboard,
  FaBookOpen,
  FaCheck,
  FaCopy
} from 'react-icons/fa';
import { HiMiniSparkles } from 'react-icons/hi2';
import './App.css';

const API_URL = import.meta.env.VITE_API_URL;

function App() {
  const [user, setUser] = useState(null);
  const [assignmentFile, setAssignmentFile] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('guidance'); // 'guidance' or 'summarize'
  const [summaryTopic, setSummaryTopic] = useState('');
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryAudio, setSummaryAudio] = useState(null);

  // ✅ Helper: make a path absolute using API_URL
  const toAbsoluteUrl = (maybeRelativeUrl) => {
    if (!maybeRelativeUrl) return null;
    const url = String(maybeRelativeUrl).trim();
    if (!url) return null;

    if (url.startsWith('http://') || url.startsWith('https://')) return url;

    const base = String(API_URL || '').replace(/\/$/, '');
    if (!base) return url;

    if (url.startsWith('/')) return `${base}${url}`;
    return `${base}/${url}`;
  };

  // ✅ (AUDIO CHANGE) Remove markdown audio parsing - backend now returns audio_url separately
  // const extractAudioFromMarkdown = ...  ❌ REMOVED

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

  const handleLogin = () => {
    window.location.href = `${API_URL}/auth/login`;
  };

  const handleRunGuidance = async (e) => {
    e.preventDefault();
    setLoading(true);
    setReport(null);

    if (!assignmentFile) {
      setReport({ error: 'Please select a PDF file to upload.' });
      setLoading(false);
      return;
    }

    const formData = new FormData();
    formData.append('file', assignmentFile);

    try {
      const response = await fetch(`${API_URL}/protected/run-guidance`, {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();

        console.log('=== Full API Response ===');
        console.log(JSON.stringify(result, null, 2));

        setReport({
          content: result.report,
          images: result.images || []
        });
      } else {
        console.error('Failed to run guidance');
        setReport({ error: 'Failed to run guidance. Make sure you are logged in.' });
      }
    } catch (error) {
      console.error('Error running guidance:', error);
      setReport({ error: 'An error occurred while running the guidance.' });
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
      setUser(null);
      setReport(null);
      setAssignmentFile(null);
      setSummary(null);
      setSummaryTopic('');
      setSummaryAudio(null);
    } catch (error) {
      console.error('Error logging out:', error);
    }
  };

  const handleSummarize = async (e) => {
    e.preventDefault();
    setSummaryLoading(true);
    setSummary(null);
    setSummaryAudio(null); // ✅ clear old audio immediately

    if (!summaryTopic || !summaryTopic.trim()) {
      setSummary({ error: 'Please enter a topic to summarize.' });
      setSummaryLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/protected/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ topic: summaryTopic.trim() }),
      });

      if (response.ok) {
        const result = await response.json();

        console.log('=== Summary Response ===');
        console.log(JSON.stringify(result, null, 2));

        // ✅ (AUDIO CHANGE) Use backend-provided audio_url directly
        const audioUrl = toAbsoluteUrl(result.audio_url);

        setSummary({
          content: result.summary || '',
          images: result.images || [],
          topic: result.topic
        });

        setSummaryAudio(audioUrl);
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to create summary' }));
        setSummary({ error: errorData.detail || 'Failed to create summary. Make sure you are logged in.' });
      }
    } catch (error) {
      console.error('Error creating summary:', error);
      setSummary({ error: 'An error occurred while creating the summary.' });
    } finally {
      setSummaryLoading(false);
    }
  };

  // Custom component for rendering code blocks and images
  const CodeBlock = {
    code({ node, inline, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '');
      const [copied, setCopied] = useState(false);

      const handleCopy = () => {
        const codeString = String(children).replace(/\n$/, '');
        navigator.clipboard.writeText(codeString);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      };

      return !inline && match ? (
        <div style={{ position: 'relative' }}>
          <SyntaxHighlighter
            style={atomDark}
            language={match[1]}
            PreTag="div"
            {...props}
          >
            {String(children).replace(/\n$/, '')}
          </SyntaxHighlighter>
          <button
            onClick={handleCopy}
            style={{
              position: 'absolute',
              top: '10px',
              right: '10px',
              background: copied ? '#28a745' : 'rgba(255, 255, 255, 0.2)',
              color: 'white',
              border: '1px solid rgba(255, 255, 255, 0.3)',
              padding: '6px 12px',
              cursor: 'pointer',
              borderRadius: '6px',
              fontSize: '0.85rem',
              fontWeight: '500',
              transition: 'all 0.3s ease',
            }}
          >
            {copied ? (
              <>
                <FaCheck style={{ marginRight: '4px' }} /> Copied!
              </>
            ) : (
              <>
                <FaCopy style={{ marginRight: '4px' }} /> Copy
              </>
            )}
          </button>
        </div>
      ) : (
        <code className={className} {...props}>
          {children}
        </code>
      );
    },

    img({ node, src, alt, ...props }) {
      // ✅ Use the same absolute-url function for images too
      const imageSrc = toAbsoluteUrl(src);

      return (
        <img
          {...props}
          src={imageSrc}
          alt={alt || 'Image'}
          className="markdown-image"
          style={{ maxWidth: '100%', width: 'auto', height: 'auto' }}
          onError={(e) => {
            console.error('Failed to load image:', imageSrc);
            e.target.style.display = 'none';
          }}
        />
      );
    },
  };

  return (
    <div className="app-container">
      <div className="app-content">
        <div className="app-header">
          <h1><FaGraduationCap style={{ marginRight: '10px', verticalAlign: 'middle' }} />CA Guidance and Summarization</h1>
        </div>

        {!user ? (
          <div className="login-screen">
            <h1>Welcome!</h1>
            <p>Please sign in with your Google account to get started</p>
            <button className="btn btn-login" onClick={handleLogin}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" style={{ marginRight: '8px' }}>
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
              Login with Google
            </button>
          </div>
        ) : (
          <div>
            <div className="user-info">
              <div className="user-welcome">
                <div className="user-avatar">
                  {user.name ? user.name.charAt(0).toUpperCase() : 'U'}
                </div>
                <span>Welcome back, <strong>{user.name}</strong>!</span>
              </div>
              <button className="btn btn-logout" onClick={handleLogout}>
                Logout
              </button>
            </div>

            {/* Tab Navigation */}
            <div className="tab-navigation">
              <button
                onClick={() => setActiveTab('guidance')}
                className={`tab-button ${activeTab === 'guidance' ? 'active' : ''}`}
              >
                <FaFileAlt style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Assignment Guidance
              </button>
              <button
                onClick={() => setActiveTab('summarize')}
                className={`tab-button ${activeTab === 'summarize' ? 'active' : ''}`}
              >
                <FaBook style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Lecture Summaries
              </button>
              <button
                onClick={() => setActiveTab('flashcards')}
                className={`tab-button ${activeTab === 'flashcards' ? 'active' : ''}`}
              >
                <FaClipboard style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Flashcard Generator
              </button>
            </div>

            {/* Guidance Tab */}
            {activeTab === 'guidance' && (
              <div className="content-area">
                <form onSubmit={handleRunGuidance} className="form-container">
                  <div className="form-group">
                    <label className="form-label" htmlFor="assignment-file">
                      <FaFilePdf style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Upload Assignment PDF
                    </label>
                    <input
                      id="assignment-file"
                      type="file"
                      accept="application/pdf"
                      onChange={(e) => setAssignmentFile(e.target.files[0])}
                      className="file-input"
                      required
                    />
                    {assignmentFile && (
                      <div className="info-message" style={{ marginTop: '10px' }}>
                        Selected: <strong>{assignmentFile.name}</strong>
                      </div>
                    )}
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={loading}>
                    {loading ? (
                      <>
                        <span className="loading-spinner"></span>
                        Processing PDF...
                      </>
                    ) : (
                      <>
                        <FaRocket style={{ marginRight: '8px' }} />
                        Generate Guidance
                      </>
                    )}
                  </button>
                </form>

                {report && (
                  <div>
                    <h2 style={{ marginBottom: '20px', color: '#495057' }}>
                      <FaClipboard style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Guidance Report
                    </h2>

                    {typeof report === 'string' ? (
                      <div className="report-content">
                        <ReactMarkdown components={CodeBlock}>{report}</ReactMarkdown>
                      </div>
                    ) : report.content ? (
                      <div className="report-content">
                        <ReactMarkdown components={CodeBlock}>{report.content}</ReactMarkdown>
                      </div>
                    ) : report.markdown_report ? (
                      <div className="report-content">
                        <ReactMarkdown components={CodeBlock}>{report.markdown_report}</ReactMarkdown>
                      </div>
                    ) : report.error ? (
                      <div className="error-message">{report.error}</div>
                    ) : (
                      <div className="report-content">
                        <ReactMarkdown components={CodeBlock}>
                          {JSON.stringify(report, null, 2)}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Summarization Tab */}
            {activeTab === 'summarize' && (
              <div className="content-area">
                <form onSubmit={handleSummarize} className="form-container">
                  <div className="form-group">
                    <label className="form-label" htmlFor="topic">
                      <FaBook style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Enter Topic to Summarize
                    </label>
                    <input
                      id="topic"
                      type="text"
                      value={summaryTopic}
                      onChange={(e) => setSummaryTopic(e.target.value)}
                      placeholder="e.g., Entity-Relationship Diagrams, Normalization, SQL Queries, Database Design..."
                      className="text-input"
                      required
                    />
                    <p style={{ marginTop: '8px', fontSize: '0.9rem', color: '#6c757d' }}>
                      Enter a topic from your lecture materials to get a comprehensive summary with relevant diagrams.
                    </p>
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={summaryLoading}>
                    {summaryLoading ? (
                      <>
                        <span className="loading-spinner"></span>
                        Creating Summary...
                      </>
                    ) : (
                      <>
                        <HiMiniSparkles style={{ marginRight: '8px' }} />
                        Create Summary
                      </>
                    )}
                  </button>
                </form>

                {summary && (
                  <div style={{ marginTop: '30px' }}>
                    {summary.topic && (
                      <h2 style={{ marginBottom: '20px', color: '#495057' }}>
                        <FaBookOpen style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Summary:{' '}
                        <span style={{ color: '#336db0' }}>{summary.topic}</span>
                      </h2>
                    )}

                    {summary.error ? (
                      <div className="error-message">{summary.error}</div>
                    ) : summary.content ? (
                      <div>
                        {summaryAudio && (
                          <div style={{ marginBottom: '12px' }}>
                            <audio controls src={summaryAudio} style={{ width: '100%' }}>
                              Your browser does not support the audio element.
                            </audio>
                          </div>
                        )}

                        <div className="report-content">
                          <ReactMarkdown components={CodeBlock}>
                            {summary.content}
                          </ReactMarkdown>
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}

                  {/* Flashcards Tab */}
                  {activeTab === 'flashcards' && (
                    <div className="content-area">
                      <h2 style={{ marginBottom: '20px', color: '#495057' }}>
                        <FaClipboard style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Flashcards
                      </h2>

                      <div className="report-content">
                        <p>Flashcards coming soon — study key concepts here.</p>
                      </div>
                    </div>
                  )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
