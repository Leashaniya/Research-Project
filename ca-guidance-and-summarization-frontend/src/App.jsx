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
  FaCopy,
  FaChartLine
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
  const [flashcardTopic, setFlashcardTopic] = useState('');
  const [flashcards, setFlashcards] = useState(null);
  const [flashLoading, setFlashLoading] = useState(false);
  const [selectedBloomLevel, setSelectedBloomLevel] = useState(null);
  const [summaryAccuracy, setSummaryAccuracy] = useState(null);
  const [summaryAccuracyLoading, setSummaryAccuracyLoading] = useState(false);
  const [guidanceAccuracy, setGuidanceAccuracy] = useState(null);
  const [guidanceAccuracyLoading, setGuidanceAccuracyLoading] = useState(false);
  // Feedback and reinforcement state
  const [feedbackRating, setFeedbackRating] = useState(null);
  const [confusedConcept, setConfusedConcept] = useState('');
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [reinforceLoading, setReinforceLoading] = useState(false);
  const [feedbackError, setFeedbackError] = useState(null);
  const [reinforceError, setReinforceError] = useState(null);
  const [reinforceSuccess, setReinforceSuccess] = useState(false);
  const [reinforcementVisible, setReinforcementVisible] = useState(false);
  const [loadedTopic, setLoadedTopic] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [baseSummary, setBaseSummary] = useState(null);
  const [reinforcedSummary, setReinforcedSummary] = useState(null);
  const [activeSummaryView, setActiveSummaryView] = useState('base'); // 'base' or 'reinforced'
  const [forceRegenerate, setForceRegenerate] = useState(false);
  const [lastFeedbackId, setLastFeedbackId] = useState(null); // Store feedback_id after submission

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

  // ✅ Helper: normalize summary ids (API sometimes returns `_id`)
  const getSummaryId = (s) => s?.summary_id || s?._id || null;

  const normalizeTopic = (t) => String(t || '').trim().toLowerCase();
  const isSameTopic = (a, b) => normalizeTopic(a) && normalizeTopic(a) === normalizeTopic(b);

  const createSessionId = () => {
    try {
      // modern browsers
      if (globalThis?.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    } catch {
      // ignore
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  };

  const formatColomboDateTime = (isoString) => {
    try {
      return new Date(isoString).toLocaleString(undefined, { timeZone: 'Asia/Colombo' });
    } catch {
      return '';
    }
  };

  const formatDurationMss = (seconds) => {
    const s = Number(seconds);
    if (!Number.isFinite(s) || s < 0) return null;
    const total = Math.round(s);
    const m = Math.floor(total / 60);
    const rem = total % 60;
    return `${m}:${String(rem).padStart(2, '0')}`;
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
    setGuidanceAccuracy(null); // Clear previous accuracy results

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
    // New topic load: clear any previous topic reinforcement UI/state
    setReinforcedSummary(null);
    setReinforcementVisible(false);
    setReinforceSuccess(false);
    setReinforceError(null);
    setFeedbackError(null);
    setFeedbackRating(null);
    setConfusedConcept('');
    setFeedbackComment('');
    setLastFeedbackId(null);
    setSummary(null);
    setSummaryAudio(null); // ✅ clear old audio immediately
    setSummaryAccuracy(null); // Clear previous accuracy results

    if (!summaryTopic || !summaryTopic.trim()) {
      setSummary({ error: 'Please enter a topic to summarize.' });
      setSummaryLoading(false);
      return;
    }

    const requestedTopic = summaryTopic.trim();
    const newSessionId = createSessionId();
    setLoadedTopic(requestedTopic);
    setSessionId(newSessionId);

    try {
      const response = await fetch(`${API_URL}/protected/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ 
          topic: requestedTopic,
          force: forceRegenerate
        }),
      });

      if (response.ok) {
        const result = await response.json();

        console.log('=== Summary Response ===');
        console.log(JSON.stringify(result, null, 2));

        // ✅ (AUDIO CHANGE) Use backend-provided audio_url directly
        const audioUrl = toAbsoluteUrl(result.audio_url);

        // Fetch summaries and ALWAYS load/show ONLY the base summary for this topic
        try {
          const allSummariesResponse = await fetch(`${API_URL}/protected/summaries/topic/${encodeURIComponent(requestedTopic)}`, {
            method: 'GET',
            credentials: 'include',
          });
          
          if (allSummariesResponse.ok) {
            const allSummaries = await allSummariesResponse.json();
            const base = allSummaries.base ? {
              ...allSummaries.base,
              content: allSummaries.base.summary_text,
              summary_id: allSummaries.base.summary_id || allSummaries.base._id,
              audio_url: toAbsoluteUrl(allSummaries.base.audio_url),
              created_at: allSummaries.base.created_at,
              audio_duration_seconds: allSummaries.base.audio_duration_seconds ?? null
            } : null;

            // Never show/load reinforcement summary on topic load
            setReinforcedSummary(null);
            setReinforcementVisible(false);

            if (base) setBaseSummary(base);

            // Always show Base summary by default (if available)
            if (base) {
              setActiveSummaryView('base');
              setSummary(base);
              setSummaryAudio(base.audio_url);
            } else {
              // Fallback: show the response as base-like if base missing
              const fallback = {
                content: result.summary || '',
                images: result.images || [],
                topic: requestedTopic,
                summary_id: result.summary_id,
                summary_type: 'base',
                created_at: result.created_at,
                from_cache: result.from_cache || false,
                audio_url: audioUrl,
                audio_duration_seconds: result.audio_duration_seconds ?? null
              };
              setBaseSummary(fallback);
              setActiveSummaryView('base');
              setSummary(fallback);
              setSummaryAudio(audioUrl);
            }
          }
        } catch (err) {
          console.error('Error fetching all summaries:', err);
        }
        
        // If we didn't set audio yet, keep audio from initial response
        setSummaryAudio((prev) => prev || audioUrl);
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

  const handleSubmitFeedback = async () => {
    const summaryId = getSummaryId(summary);
    if (!summary || !summaryId) {
      alert('No summary available to provide feedback on.');
      return;
    }

    if (!feedbackRating) {
      alert('Please select whether the summary was helpful or not.');
      return;
    }

    setFeedbackLoading(true);
    setFeedbackError(null);

    try {
      const response = await fetch(`${API_URL}/protected/summaries/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          topic: summary.topic,
          summary_id: summaryId,
          rating: feedbackRating,
          confused_concept: confusedConcept.trim() || null,
          comment: feedbackComment.trim() || null
        }),
      });

      if (response.ok) {
        const result = await response.json();
        setFeedbackSubmitted(true);
        setFeedbackError(null);
        // Store feedback_id so we can use it for reinforcement
        if (result.feedback_id) {
          setLastFeedbackId(result.feedback_id);
        }
        // Keep feedback rating visible so user can generate reinforced summary
        // Show success message
        setTimeout(() => {
          // Don't reset feedbackSubmitted immediately - keep it so button stays visible
        }, 3000);
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to submit feedback' }));
        setFeedbackError(errorData.detail || 'Failed to submit feedback.');
      }
    } catch (error) {
      console.error('Error submitting feedback:', error);
      setFeedbackError('An error occurred while submitting feedback.');
    } finally {
      setFeedbackLoading(false);
    }
  };

  const handleSubmitFeedbackAndReinforce = async () => {
    const baseId = getSummaryId(baseSummary);
    if (!baseSummary || !baseId || !loadedTopic) {
      alert('No summary available to provide feedback on.');
      return;
    }

    if (!feedbackRating) {
      alert('Please select whether the summary was helpful or not.');
      return;
    }

    setFeedbackLoading(true);
    setReinforceLoading(true);
    setFeedbackError(null);
    setReinforceError(null);
    setReinforceSuccess(false);

    try {
      // 1) Save feedback
      const feedbackResp = await fetch(`${API_URL}/protected/summaries/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          topic: loadedTopic,
          summary_id: baseId,
          rating: feedbackRating,
          confused_concept: confusedConcept.trim() || null,
          comment: feedbackComment.trim() || null,
          session_id: sessionId
        }),
      });

      if (!feedbackResp.ok) {
        const errorData = await feedbackResp.json().catch(() => ({ detail: 'Failed to submit feedback' }));
        setFeedbackError(errorData.detail || 'Failed to submit feedback.');
        return;
      }

      const feedbackResult = await feedbackResp.json().catch(() => ({}));
      if (feedbackResult.feedback_id) setLastFeedbackId(feedbackResult.feedback_id);

      // 2) Generate reinforced summary using latest feedback (force=true)
      const reinforceResp = await fetch(`${API_URL}/summaries/reinforce`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          topic: loadedTopic,
          force: true,
          summary_id: baseId,
          session_id: sessionId
        }),
      });

      if (!reinforceResp.ok) {
        const errorData = await reinforceResp.json().catch(() => ({ detail: 'Failed to generate reinforced summary' }));
        setReinforceError(errorData.detail || 'Failed to generate reinforced summary.');
        return;
      }

      const result = await reinforceResp.json();
      const audioUrl = toAbsoluteUrl(result.audio_url);

      const reinforcedData = {
        content: result.summary || '',
        images: result.images || [],
        topic: result.topic,
        summary_id: result.summary_id,
        summary_type: 'reinforced',
        created_at: result.created_at,
        from_cache: result.from_cache || false,
        audio_url: audioUrl,
        audio_duration_seconds: result.audio_duration_seconds ?? null,
        session_id: sessionId
      };

      setReinforcedSummary(reinforcedData);
      setSummary(reinforcedData);
      setSummaryAudio(audioUrl);
      setActiveSummaryView('reinforced'); // Switch to reinforced view
      setReinforcementVisible(true);

      setReinforceSuccess(true);
      setTimeout(() => setReinforceSuccess(false), 4000);

      // Reset feedback inputs after successful generation
      setFeedbackRating(null);
      setConfusedConcept('');
      setFeedbackComment('');
      setFeedbackSubmitted(false);
      setLastFeedbackId(null);
    } catch (error) {
      console.error('Error submitting feedback and generating reinforced summary:', error);
      setReinforceError('An error occurred while generating reinforced summary.');
    } finally {
      setFeedbackLoading(false);
      setReinforceLoading(false);
    }
  };

  const handleReinforceSummary = async () => {
    if (!summary || !summary.topic) {
      alert('No summary available to reinforce from feedback.');
      return;
    }

    setReinforceLoading(true);
    setReinforceError(null);

    try {
      const response = await fetch(`${API_URL}/summaries/reinforce`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          topic: summary.topic,
          force: true
        }),
      });

      if (response.ok) {
        const result = await response.json();

        // Update reinforced summary
        const audioUrl = toAbsoluteUrl(result.audio_url);
        
        const reinforcedData = {
          content: result.summary || '',
          images: result.images || [],
          topic: result.topic,
          summary_id: result.summary_id,
          summary_type: 'reinforced',
          created_at: result.created_at,
          from_cache: result.from_cache || false,
          audio_url: audioUrl
        };
        
        setReinforcedSummary(reinforcedData);
        setSummary(reinforcedData);
        setSummaryAudio(audioUrl);
        setActiveSummaryView('reinforced'); // Switch to reinforced view
        
        // Update base summary reference if needed
        if (baseSummary && baseSummary.summary_id === summary.summary_id) {
          // Keep base summary reference
        }
        
        // Reset feedback state after successful reinforcement
        setFeedbackRating(null);
        setConfusedConcept('');
        setFeedbackComment('');
        setFeedbackSubmitted(false);
        setLastFeedbackId(null);
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to generate reinforced summary' }));
        setReinforceError(errorData.detail || 'Failed to generate reinforced summary.');
      }
    } catch (error) {
      console.error('Error generating reinforced summary:', error);
      setReinforceError('An error occurred while generating reinforced summary.');
    } finally {
      setReinforceLoading(false);
    }
  };

  const handleCheckSummaryAccuracy = async () => {
    if (!summary || !summary.content || !summary.topic) {
      alert('Please generate a summary first before checking accuracy.');
      return;
    }

    setSummaryAccuracyLoading(true);
    setSummaryAccuracy(null);

    try {
      const response = await fetch(`${API_URL}/protected/check-summary-accuracy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          topic: summary.topic,
          summary_content: summary.content
        }),
      });

      if (response.ok) {
        const result = await response.json();
        setSummaryAccuracy(result);
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to check accuracy' }));
        setSummaryAccuracy({ error: errorData.detail || 'Failed to check summary accuracy.' });
      }
    } catch (error) {
      console.error('Error checking summary accuracy:', error);
      setSummaryAccuracy({ error: 'An error occurred while checking accuracy.' });
    } finally {
      setSummaryAccuracyLoading(false);
    }
  };

  const handleCheckGuidanceAccuracy = async () => {
    if (!report || (!report.content && typeof report !== 'string')) {
      alert('Please generate guidance first before checking accuracy.');
      return;
    }

    setGuidanceAccuracyLoading(true);
    setGuidanceAccuracy(null);

    try {
      const guidanceContent = typeof report === 'string' ? report : report.content || '';
      
      const response = await fetch(`${API_URL}/protected/check-guidance-accuracy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          guidance_content: guidanceContent,
          assignment_topic: null
        }),
      });

      if (response.ok) {
        const result = await response.json();
        setGuidanceAccuracy(result);
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to check accuracy' }));
        setGuidanceAccuracy({ error: errorData.detail || 'Failed to check guidance accuracy.' });
      }
    } catch (error) {
      console.error('Error checking guidance accuracy:', error);
      setGuidanceAccuracy({ error: 'An error occurred while checking accuracy.' });
    } finally {
      setGuidanceAccuracyLoading(false);
    }
  };

  const handleGenerateFlashcards = async (e) => {
    e.preventDefault();
    setFlashLoading(true);
    setFlashcards(null);
    setSelectedBloomLevel(null);

    if (!flashcardTopic || !flashcardTopic.trim()) {
      setFlashcards({ error: 'Please enter a topic to generate flashcards.' });
      setFlashLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/protected/generate-flashcards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ topic: flashcardTopic.trim() }),
      });

      if (response.ok) {
        const result = await response.json();
        setFlashcards(result);
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to generate flashcards' }));
        setFlashcards({ error: errorData.detail || 'Failed to generate flashcards. Make sure you are logged in.' });
      }
    } catch (error) {
      console.error('Error generating flashcards:', error);
      setFlashcards({ error: 'An error occurred while generating flashcards.' });
    } finally {
      setFlashLoading(false);
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

                    {/* Accuracy Check Button and Results */}
                    {!report.error && (
                      <div style={{ marginTop: '30px', padding: '20px', border: '1px solid #dee2e6', borderRadius: '8px', backgroundColor: '#f8f9fa' }}>
                        <button
                          onClick={handleCheckGuidanceAccuracy}
                          className="btn btn-primary"
                          disabled={guidanceAccuracyLoading}
                          style={{ marginBottom: '20px' }}
                        >
                          {guidanceAccuracyLoading ? (
                            <>
                              <span className="loading-spinner"></span>
                              Checking Accuracy...
                            </>
                          ) : (
                            <>
                              <FaChartLine style={{ marginRight: '8px' }} />
                              Check Accuracy
                            </>
                          )}
                        </button>

                        {guidanceAccuracy && (
                          <div style={{ marginTop: '20px' }}>
                            {guidanceAccuracy.error ? (
                              <div className="error-message">{guidanceAccuracy.error}</div>
                            ) : (
                              <div>
                                <h3 style={{ marginBottom: '15px', color: '#495057' }}>
                                  <FaChartLine style={{ marginRight: '8px' }} />
                                  Accuracy Assessment
                                </h3>
                                {guidanceAccuracy.overall && (
                                  <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#fff', borderRadius: '6px', border: '1px solid #dee2e6' }}>
                                    <div style={{ fontSize: '1.2rem', fontWeight: 'bold', marginBottom: '10px' }}>
                                      Overall Accuracy: {guidanceAccuracy.overall.avg_fmeasure_pct?.toFixed(2) || 0}%
                                    </div>
                                    <div style={{ fontSize: '1rem', marginBottom: '5px' }}>
                                      Level: <strong>{guidanceAccuracy.overall.accuracy_level}</strong>
                                    </div>
                                    <div style={{ fontSize: '0.95rem', color: '#6c757d', marginTop: '10px' }}>
                                      {guidanceAccuracy.overall.recommendation}
                                    </div>
                                  </div>
                                )}
                                <div style={{ backgroundColor: '#fff', padding: '15px', borderRadius: '6px', border: '1px solid #dee2e6' }}>
                                  <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.9rem', margin: 0 }}>
                                    {guidanceAccuracy.report}
                                  </pre>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
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
                    <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <input
                        type="checkbox"
                        id="force-regenerate"
                        checked={forceRegenerate}
                        onChange={(e) => setForceRegenerate(e.target.checked)}
                        disabled={summaryLoading}
                      />
                      <label htmlFor="force-regenerate" style={{ fontSize: '0.9rem', color: '#495057', cursor: 'pointer' }}>
                        Force regenerate (ignore saved summaries)
                      </label>
                    </div>
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
                      <div style={{ marginBottom: '20px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
                          <h2 style={{ margin: 0, color: '#495057' }}>
                            <FaBookOpen style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Summary:{' '}
                            <span style={{ color: '#336db0' }}>{summary.topic}</span>
                          </h2>
                        {summary.summary_type && (
                          <span style={{
                            padding: '4px 12px',
                            borderRadius: '12px',
                            fontSize: '0.85rem',
                            fontWeight: '600',
                            backgroundColor: summary.summary_type === 'reinforced' ? '#28a745' : '#6c757d',
                            color: '#fff',
                            textTransform: 'capitalize'
                          }}>
                            {summary.summary_type === 'reinforced' ? 'Reinforced' : 'Base'}
                          </span>
                        )}
                        {summary.summary_type === 'reinforced' && summary.audio_duration_seconds != null ? (
                          <span style={{
                            padding: '4px 12px',
                            borderRadius: '12px',
                            fontSize: '0.85rem',
                            color: '#6c757d',
                            backgroundColor: '#f8f9fa',
                            border: '1px solid #dee2e6'
                          }} title={summary.created_at ? `Created: ${formatColomboDateTime(summary.created_at)}` : 'Audio duration'}>
                            {formatDurationMss(summary.audio_duration_seconds) || '0:00'}
                          </span>
                        ) : summary.created_at ? (
                          <span style={{
                            padding: '4px 12px',
                            borderRadius: '12px',
                            fontSize: '0.85rem',
                            color: '#6c757d',
                            backgroundColor: '#f8f9fa',
                            border: '1px solid #dee2e6'
                          }} title="Created timestamp">
                            {formatColomboDateTime(summary.created_at)}
                          </span>
                        ) : null}
                        {summary.from_cache && (
                          <span style={{
                            padding: '4px 12px',
                            borderRadius: '12px',
                            fontSize: '0.85rem',
                            color: '#6c757d',
                            backgroundColor: '#e7f3ff',
                            border: '1px solid #b3d9ff'
                          }}>
                            Cached
                          </span>
                        )}
                        </div>
                        
                        {/* Summary Type Switcher - Show reinforced ONLY after feedback→generate for THIS topic/session */}
                        {baseSummary && reinforcementVisible && reinforcedSummary && isSameTopic(reinforcedSummary.topic, loadedTopic) && reinforcedSummary.session_id === sessionId && (
                          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                            <button
                              onClick={() => {
                                setActiveSummaryView('base');
                                setSummary(baseSummary);
                                setSummaryAudio(baseSummary.audio_url);
                              }}
                              style={{
                                padding: '8px 16px',
                                fontSize: '0.9rem',
                                fontWeight: '600',
                                backgroundColor: activeSummaryView === 'base' ? '#336db0' : '#fff',
                                color: activeSummaryView === 'base' ? '#fff' : '#495057',
                                border: `2px solid ${activeSummaryView === 'base' ? '#336db0' : '#dee2e6'}`,
                                borderRadius: '6px',
                                cursor: 'pointer',
                                transition: 'all 0.3s ease'
                              }}
                            >
                              Base Summary
                            </button>
                            <button
                              onClick={() => {
                                setActiveSummaryView('reinforced');
                                setSummary(reinforcedSummary);
                                setSummaryAudio(reinforcedSummary.audio_url);
                              }}
                              style={{
                                padding: '8px 16px',
                                fontSize: '0.9rem',
                                fontWeight: '600',
                                backgroundColor: activeSummaryView === 'reinforced' ? '#28a745' : '#fff',
                                color: activeSummaryView === 'reinforced' ? '#fff' : '#495057',
                                border: `2px solid ${activeSummaryView === 'reinforced' ? '#28a745' : '#dee2e6'}`,
                                borderRadius: '6px',
                                cursor: 'pointer',
                                transition: 'all 0.3s ease'
                              }}
                            >
                              Reinforced Summary
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {summary.error ? (
                      <div className="error-message">{summary.error}</div>
                    ) : summary.content ? (
                      <div>
                        <div className="report-content">
                          <ReactMarkdown components={CodeBlock}>
                            {summary.content}
                          </ReactMarkdown>
                        </div>

                        <div style={{ marginTop: '14px' }}>
                          <strong>Listen to the Audio of the summarization: </strong>
                          {summaryAudio ? (
                            <div style={{ marginTop: '8px' }}>
                              <audio controls src={summaryAudio} style={{ width: '100%' }}>
                                Your browser does not support the audio element.
                              </audio>
                            </div>
                          ) : (
                            <div className="info-message" style={{ marginTop: '8px' }}>
                              No audio available.
                            </div>
                          )}
                        </div>

                        {/* Feedback Section */}
                        <div style={{ marginTop: '30px', padding: '20px', border: '1px solid #dee2e6', borderRadius: '8px', backgroundColor: '#f8f9fa' }}>
                          <h3 style={{ marginBottom: '16px', color: '#495057', fontSize: '1.1rem' }}>
                            Was this summary helpful?
                          </h3>
                          
                          <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
                            <button
                              onClick={() => setFeedbackRating('helpful')}
                              disabled={feedbackLoading || reinforceLoading}
                              style={{
                                padding: '10px 20px',
                                fontSize: '1rem',
                                fontWeight: '600',
                                backgroundColor: feedbackRating === 'helpful' ? '#28a745' : '#fff',
                                color: feedbackRating === 'helpful' ? '#fff' : '#495057',
                                border: `2px solid ${feedbackRating === 'helpful' ? '#28a745' : '#dee2e6'}`,
                                borderRadius: '8px',
                                cursor: feedbackLoading || reinforceLoading ? 'not-allowed' : 'pointer',
                                opacity: feedbackLoading || reinforceLoading ? 0.6 : 1,
                                transition: 'all 0.3s ease'
                              }}
                            >
                              👍 Helpful
                            </button>
                            <button
                              onClick={() => setFeedbackRating('not_helpful')}
                              disabled={feedbackLoading || reinforceLoading}
                              style={{
                                padding: '10px 20px',
                                fontSize: '1rem',
                                fontWeight: '600',
                                backgroundColor: feedbackRating === 'not_helpful' ? '#dc3545' : '#fff',
                                color: feedbackRating === 'not_helpful' ? '#fff' : '#495057',
                                border: `2px solid ${feedbackRating === 'not_helpful' ? '#dc3545' : '#dee2e6'}`,
                                borderRadius: '8px',
                                cursor: feedbackLoading || reinforceLoading ? 'not-allowed' : 'pointer',
                                opacity: feedbackLoading || reinforceLoading ? 0.6 : 1,
                                transition: 'all 0.3s ease'
                              }}
                            >
                              👎 Not Helpful
                            </button>
                          </div>

                          {feedbackRating && (
                            <>
                              <div style={{ marginBottom: '16px' }}>
                                <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500', color: '#495057' }}>
                                  Confused about (optional):
                                </label>
                                <input
                                  type="text"
                                  value={confusedConcept}
                                  onChange={(e) => setConfusedConcept(e.target.value)}
                                  placeholder="e.g., normalization steps, ER diagram relationships..."
                                  disabled={feedbackLoading || reinforceLoading}
                                  style={{
                                    width: '100%',
                                    padding: '10px',
                                    border: '1px solid #dee2e6',
                                    borderRadius: '6px',
                                    fontSize: '0.95rem',
                                    opacity: feedbackLoading || reinforceLoading ? 0.6 : 1
                                  }}
                                />
                              </div>

                              <div style={{ marginBottom: '16px' }}>
                                <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500', color: '#495057' }}>
                                  Comment (optional):
                                </label>
                                <textarea
                                  value={feedbackComment}
                                  onChange={(e) => setFeedbackComment(e.target.value)}
                                  placeholder="Any additional feedback..."
                                  disabled={feedbackLoading || reinforceLoading}
                                  rows={3}
                                  style={{
                                    width: '100%',
                                    padding: '10px',
                                    border: '1px solid #dee2e6',
                                    borderRadius: '6px',
                                    fontSize: '0.95rem',
                                    fontFamily: 'inherit',
                                    resize: 'vertical',
                                    opacity: feedbackLoading || reinforceLoading ? 0.6 : 1
                                  }}
                                />
                              </div>

                              <button
                                onClick={handleSubmitFeedbackAndReinforce}
                                disabled={feedbackLoading || reinforceLoading}
                                className="btn btn-primary"
                                style={{ marginBottom: '12px' }}
                              >
                                {feedbackLoading || reinforceLoading ? (
                                  <>
                                    <span className="loading-spinner"></span>
                                    Submitting & Generating...
                                  </>
                                ) : (
                                  <>
                                    <HiMiniSparkles style={{ marginRight: '8px' }} />
                                    Feedback → Generate
                                  </>
                                )}
                              </button>

                              {reinforceSuccess && (
                                <div style={{ 
                                  marginTop: '12px', 
                                  padding: '10px', 
                                  backgroundColor: '#d4edda', 
                                  border: '1px solid #c3e6cb',
                                  borderRadius: '6px',
                                  color: '#155724',
                                  fontSize: '0.9rem'
                                }}>
                                  Reinforcement summary generated successfully ✅
                                </div>
                              )}
                              
                              {feedbackError && (
                                <div className="error-message" style={{ marginTop: '12px' }}>
                                  {feedbackError}
                                </div>
                              )}

                              {reinforceError && (
                                <div className="error-message" style={{ marginTop: '12px' }}>
                                  {reinforceError}
                                </div>
                              )}
                            </>
                          )}
                        </div>

                        {/* Accuracy Check Button and Results */}
                        <div style={{ marginTop: '30px', padding: '20px', border: '1px solid #dee2e6', borderRadius: '8px', backgroundColor: '#f8f9fa' }}>
                          <button
                            onClick={handleCheckSummaryAccuracy}
                            className="btn btn-primary"
                            disabled={summaryAccuracyLoading}
                            style={{ marginBottom: '20px' }}
                          >
                            {summaryAccuracyLoading ? (
                              <>
                                <span className="loading-spinner"></span>
                                Checking Accuracy...
                              </>
                            ) : (
                              <>
                                <FaChartLine style={{ marginRight: '8px' }} />
                                Check Accuracy
                              </>
                            )}
                          </button>

                          {summaryAccuracy && (
                            <div style={{ marginTop: '20px' }}>
                              {summaryAccuracy.error ? (
                                <div className="error-message">{summaryAccuracy.error}</div>
                              ) : (
                                <div>
                                  <h3 style={{ marginBottom: '15px', color: '#495057' }}>
                                    <FaChartLine style={{ marginRight: '8px' }} />
                                    Accuracy Assessment
                                  </h3>
                                  {summaryAccuracy.overall && (
                                    <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#fff', borderRadius: '6px', border: '1px solid #dee2e6' }}>
                                      <div style={{ fontSize: '1.2rem', fontWeight: 'bold', marginBottom: '10px' }}>
                                        Overall Accuracy: {summaryAccuracy.overall.avg_fmeasure_pct?.toFixed(2) || 0}%
                                      </div>
                                      <div style={{ fontSize: '1rem', marginBottom: '5px' }}>
                                        Level: <strong>{summaryAccuracy.overall.accuracy_level}</strong>
                                      </div>
                                      <div style={{ fontSize: '0.95rem', color: '#6c757d', marginTop: '10px' }}>
                                        {summaryAccuracy.overall.recommendation}
                                      </div>
                                    </div>
                                  )}
                                  <div style={{ backgroundColor: '#fff', padding: '15px', borderRadius: '6px', border: '1px solid #dee2e6' }}>
                                    <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.9rem', margin: 0 }}>
                                      {summaryAccuracy.report}
                                    </pre>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}

                
              </div>
            )}

            {/* Flashcards Tab */}
            {activeTab === 'flashcards' && (
              <div className="content-area">
                <form onSubmit={handleGenerateFlashcards} className="form-container">
                  <div className="form-group">
                    <label className="form-label" htmlFor="flashcard-topic">
                      <FaClipboard style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Enter Topic for Flashcards
                    </label>
                    <input
                      id="flashcard-topic"
                      type="text"
                      value={flashcardTopic}
                      onChange={(e) => setFlashcardTopic(e.target.value)}
                      placeholder="e.g., Normalization, ER Diagrams, Transactions..."
                      className="text-input"
                      required
                    />
                    <p style={{ marginTop: '8px', fontSize: '0.9rem', color: '#6c757d' }}>
                      Enter a topic to generate short Q&A flashcards.
                    </p>
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={flashLoading}>
                    {flashLoading ? (
                      <>
                        <span className="loading-spinner"></span>
                        Generating...
                      </>
                    ) : (
                      <>
                        <FaClipboard style={{ marginRight: '8px' }} />
                        Generate Flashcards
                      </>
                    )}
                  </button>
                </form>

                {flashcards && (
                  <div style={{ marginTop: '24px' }}>
                    {flashcards.error ? (
                      <div className="error-message">{flashcards.error}</div>
                    ) : (
                      <div>
                        {flashcards.topic && (
                          <h2 style={{ marginBottom: '20px', color: '#495057' }}>
                            <FaClipboard style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Flashcards: <span style={{ color: '#336db0' }}>{flashcards.topic}</span>
                          </h2>
                        )}

                        {flashcards.flashcards && (
                          <div>
                            {/* Bloom's Taxonomy Level Buttons */}
                            <div style={{ 
                              display: 'flex', 
                              flexWrap: 'wrap', 
                              gap: '12px', 
                              marginBottom: '24px',
                              padding: '16px',
                              backgroundColor: '#f8f9fa',
                              borderRadius: '8px',
                              border: '1px solid #dee2e6'
                            }}>
                              {['remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'].map((level) => (
                                <button
                                  key={level}
                                  onClick={() => setSelectedBloomLevel(selectedBloomLevel === level ? null : level)}
                                  style={{
                                    padding: '12px 20px',
                                    fontSize: '1rem',
                                    fontWeight: '600',
                                    textTransform: 'capitalize',
                                    backgroundColor: selectedBloomLevel === level ? '#336db0' : '#fff',
                                    color: selectedBloomLevel === level ? '#fff' : '#495057',
                                    border: `2px solid ${selectedBloomLevel === level ? '#336db0' : '#dee2e6'}`,
                                    borderRadius: '8px',
                                    cursor: 'pointer',
                                    transition: 'all 0.3s ease',
                                    boxShadow: selectedBloomLevel === level ? '0 4px 8px rgba(51, 109, 176, 0.3)' : '0 2px 4px rgba(0,0,0,0.1)',
                                  }}
                                  onMouseEnter={(e) => {
                                    if (selectedBloomLevel !== level) {
                                      e.target.style.backgroundColor = '#e9ecef';
                                    }
                                  }}
                                  onMouseLeave={(e) => {
                                    if (selectedBloomLevel !== level) {
                                      e.target.style.backgroundColor = '#fff';
                                    }
                                  }}
                                >
                                  {level}
                                </button>
                              ))}
                            </div>

                            {/* Display flashcards for selected level */}
                            {selectedBloomLevel && flashcards.flashcards[selectedBloomLevel] && (
                              <div style={{ marginTop: '20px' }}>
                                <h3 style={{ 
                                  marginBottom: '16px', 
                                  color: '#495057',
                                  textTransform: 'capitalize',
                                  fontSize: '1.3rem'
                                }}>
                                  {selectedBloomLevel} Level Flashcards
                                </h3>
                                <div className="report-content">
                                  {flashcards.flashcards[selectedBloomLevel].map((card, i) => (
                                    <div 
                                      key={i} 
                                      style={{ 
                                        marginBottom: '20px',
                                        padding: '16px',
                                        backgroundColor: '#fff',
                                        borderRadius: '8px',
                                        border: '1px solid #dee2e6',
                                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                                      }}
                                    >
                                      <div style={{ 
                                        marginBottom: '12px',
                                        fontSize: '1.1rem',
                                        fontWeight: '600',
                                        color: '#336db0'
                                      }}>
                                        <strong>Q{i + 1}:</strong> {card.question}
                                      </div>
                                      <div style={{ 
                                        fontSize: '1rem',
                                        color: '#495057',
                                        lineHeight: '1.6'
                                      }}>
                                        <strong style={{ color: '#28a745' }}>Answer:</strong> {card.answer}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Show message if no level is selected */}
                            {!selectedBloomLevel && (
                              <div style={{ 
                                padding: '20px',
                                textAlign: 'center',
                                color: '#6c757d',
                                backgroundColor: '#f8f9fa',
                                borderRadius: '8px',
                                border: '1px solid #dee2e6'
                              }}>
                                <p style={{ fontSize: '1rem', margin: 0 }}>
                                  Select a Bloom's Taxonomy level above to view the flashcards.
                                </p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
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
