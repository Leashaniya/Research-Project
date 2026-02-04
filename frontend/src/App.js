import React, { useState } from 'react';
import './App.css';

const API_BASE = "http://localhost:8000";

function App() {
  const [logs, setLogs] = useState(["Welcome to AI Paper Generator. Ready to start."]);
  const [processing, setProcessing] = useState(false);
  const [paper, setPaper] = useState(null);
  const [status, setStatus] = useState("Idle");
  const [files, setFiles] = useState({ past_papers: [], lecture_slides: [] });
  const [showFiles, setShowFiles] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);

  const addLog = (msg) => {
    setLogs(prev => [...prev.slice(-50), `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  const fetchFiles = async (showErrors = true) => {
    setLoadingFiles(true);
    try {
      console.log('Fetching files from:', `${API_BASE}/files`);
      const resp = await fetch(`${API_BASE}/files`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
        mode: 'cors',
      });
      console.log('Response status:', resp.status, resp.statusText);
      
      if (!resp.ok) {
        throw new Error(`HTTP error! status: ${resp.status}`);
      }
      const data = await resp.json();
      console.log('Files API response:', data);
      
      // Ensure we have the expected structure
      if (data && typeof data === 'object') {
        const pastPapers = Array.isArray(data.past_papers) ? data.past_papers : [];
        const lectureSlides = Array.isArray(data.lecture_slides) ? data.lecture_slides : [];
        
        setFiles({
          past_papers: pastPapers,
          lecture_slides: lectureSlides
        });
        
        console.log('Files state updated:', {
          past_papers: pastPapers,
          lecture_slides: lectureSlides
        });
        
        if (pastPapers.length > 0 || lectureSlides.length > 0) {
          if (showErrors) {
            addLog(`Found ${pastPapers.length} past papers and ${lectureSlides.length} lecture slides`);
          }
        }
      } else {
        console.error('Unexpected data format:', data);
        setFiles({ past_papers: [], lecture_slides: [] });
        if (showErrors) {
          addLog('Error: Unexpected response format from server');
        }
      }
    } catch (err) {
      // Only log error if showErrors is true (user-initiated) or if it's not a network error
      const isNetworkError = err.message.includes('Failed to fetch') || 
                            err.message.includes('NetworkError') ||
                            err.message.includes('Network request failed') ||
                            err.name === 'TypeError';
      
      if (showErrors) {
        if (isNetworkError) {
          // Show user-friendly message only when user explicitly requests files
          addLog(`Cannot connect to backend server. Error: ${err.message}`);
          console.error('Backend server not reachable. Full error:', err);
          console.error('Trying to connect to:', `${API_BASE}/files`);
        } else {
          addLog(`Error fetching files: ${err.message}`);
          console.error('Fetch error details:', err);
        }
      } else {
        // Silent failure on initial load - just log to console
        console.warn('Initial file fetch failed (backend may be starting):', err.message);
      }
    } finally {
      setLoadingFiles(false);
    }
  };

  const checkLatestPaper = async () => {
    try {
      const resp = await fetch(`${API_BASE}/model-paper/paper-json`);
      if (resp.ok) {
        const data = await resp.json();
        setPaper(data);
        setStatus("Ready (Retrieved existing paper)");
      }
    } catch (err) {
      // Ignore if no paper found
    }
  };

  React.useEffect(() => {
    // Silently fetch files on initial load (don't show errors to user)
    // User can explicitly click "View Processed Files" to see errors if backend is down
    const timer = setTimeout(() => {
      fetchFiles(false); // false = don't show errors in logs
      checkLatestPaper();
    }, 100);
    return () => clearTimeout(timer);
  }, []);

  const handleUpload = async (file, type) => {
    const formData = new FormData();
    formData.append("file", file);

    const endpoint = type === "past" ? "/past-papers/upload" : "/lecture-slides/upload";

    addLog(`Uploading ${file.name}...`);
    try {
      const resp = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        body: formData
      });
      const data = await resp.json();
      addLog(`Success: ${data.message}`);
      fetchFiles(); // Refresh list after upload
    } catch (err) {
      addLog(`Error: ${err.message}`);
    }
  };

  const generatePaper = async () => {
    setProcessing(true);
    setStatus("Running End-to-End Pipeline...");
    addLog("Analyzing documents and deploying AI Agents...");
    try {
      const resp = await fetch(`${API_BASE}/model-paper/generate-paper`, {
        method: "POST",
        headers: { 'Cache-Control': 'no-cache' }
      });

      if (!resp.ok) {
        const errData = await resp.json();
        throw new Error(errData.detail || "Server Error");
      }

      const data = await resp.json();

      // Log steps from backend
      if (data.steps) {
        data.steps.forEach(step => addLog(step));
      }

      if (data.status === "success") {
        setPaper(data.paper);
        addLog("Success! Model paper generated with latest data.");
        setStatus("Done");
      } else {
        addLog(`Failed: ${data.message}`);
        setStatus("Error");
      }
    } catch (err) {
      addLog(`Error: ${err.message}`);
      setStatus("Timed out or Connection Lost. Check backend console.");
      // Check if a checkpoint exists and we can resume later
      addLog("Retrying may resume from the last saved question.");
    } finally {
      setProcessing(false);
    }
  };

  const downloadPDF = () => {
    window.open(`${API_BASE}/model-paper/download-pdf`, "_blank");
  };

  return (
    <div className="Dashboard">
      <header>
        <h1>Agentic AI Paper Generator</h1>
        <p>Pro-Level Exam Question Generation with Self-Correcting Agents</p>
      </header>

      <div className="ActionGrid">
        <div className="Card">
          <div className="IconBox">📄</div>
          <h3>Past Papers</h3>
          <p>Upload PDF past papers to establish the exam style and structure.</p>
          <label className="Btn">
            Upload PDF
            <input type="file" className="UploadInput" onChange={(e) => handleUpload(e.target.files[0], "past")} />
          </label>
        </div>

        <div className="Card">
          <div className="IconBox">📚</div>
          <h3>Lecture Slides</h3>
          <p>Upload slides to provide context for the local researcher agent.</p>
          <label className="Btn">
            Upload PDF
            <input type="file" className="UploadInput" onChange={(e) => handleUpload(e.target.files[0], "slides")} />
          </label>
        </div>

        <div className="Card">
          <div className="IconBox">🤖</div>
          <h3>AI Generation</h3>
          <p>Extract knowledge from all new uploads and generate the final paper.</p>
          <button className="Btn" onClick={generatePaper} disabled={processing}>
            {processing ? "Generating..." : "Generate Paper"}
          </button>
        </div>
      </div>

      <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <button 
          className="Btn" 
          onClick={() => { 
            if (!showFiles) {
              fetchFiles(true); // true = show errors in logs
            }
            setShowFiles(!showFiles); 
          }} 
          style={{ background: '#475569' }}
          disabled={loadingFiles}
        >
          {loadingFiles ? "Loading..." : showFiles ? "Hide Processed Files" : "View Processed Files"}
        </button>
      </div>

      {showFiles && (
        <div className="Card" style={{ maxWidth: '800px', margin: '0 auto 2rem auto', textAlign: 'left' }}>
          <h3>Processed Files</h3>
          {loadingFiles ? (
            <p style={{ color: '#94a3b8', textAlign: 'center' }}>Loading files...</p>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <h4 style={{ color: '#6366f1' }}>Past Papers ({files.past_papers.length})</h4>
                <ul style={{ fontSize: '0.9rem', color: '#94a3b8', listStyle: 'none', padding: 0 }}>
                  {files.past_papers.length > 0 ? (
                    files.past_papers.map((f, i) => <li key={i} style={{ marginBottom: '0.5rem' }}>• {f}</li>)
                  ) : (
                    <li style={{ fontStyle: 'italic' }}>No papers found.</li>
                  )}
                </ul>
              </div>
              <div>
                <h4 style={{ color: '#6366f1' }}>Lecture Slides ({files.lecture_slides.length})</h4>
                <ul style={{ fontSize: '0.9rem', color: '#94a3b8', listStyle: 'none', padding: 0 }}>
                  {files.lecture_slides.length > 0 ? (
                    files.lecture_slides.map((f, i) => <li key={i} style={{ marginBottom: '0.5rem' }}>• {f}</li>)
                  ) : (
                    <li style={{ fontStyle: 'italic' }}>No slides found.</li>
                  )}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="StatusSection">
        <h3>System Status: <span style={{ color: '#6366f1' }}>{status}</span></h3>
        <div className="LogBox">
          {logs.map((log, i) => (
            <div key={i} className="LogLine">{log}</div>
          ))}
        </div>
      </div>

      {paper && (
        <div className="PaperPreview">
          <div className="PaperHeader">
            <h2>Generated Paper Preview</h2>
            <button className="Btn DownloadBtn" onClick={downloadPDF}>Download PDF</button>
          </div>
          {paper.questions?.map((q, i) => (
            <div key={i} className="Question">
              <strong>Question {q.question_no} ({q.marks} Marks)</strong>
              <div style={{ whiteSpace: 'pre-wrap', marginTop: '1rem', color: '#cbd5e1' }}>
                {q.text}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default App;
