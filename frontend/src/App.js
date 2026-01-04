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

  const addLog = (msg) => {
    setLogs(prev => [...prev.slice(-10), `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  const fetchFiles = async () => {
    try {
      const resp = await fetch(`${API_BASE}/files`);
      const data = await resp.json();
      setFiles(data);
    } catch (err) {
      addLog(`Error fetching files: ${err.message}`);
    }
  };

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
      const resp = await fetch(`${API_BASE}/model-paper/generate-paper`, { method: "POST" });
      const data = await resp.json();

      // Log steps from backend
      if (data.steps) {
        data.steps.forEach(step => addLog(step));
      }

      if (data.status === "success") {
        setPaper(data.paper);
        addLog("Success! Model paper generated with latest data.");
      } else {
        addLog(`Failed: ${data.message}`);
      }
    } catch (err) {
      addLog(`Error: ${err.message}`);
    } finally {
      setProcessing(false);
      setStatus("Done");
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
        <button className="Btn" onClick={() => { setShowFiles(!showFiles); if (!showFiles) fetchFiles(); }} style={{ background: '#475569' }}>
          {showFiles ? "Hide Processed Files" : "View Processed Files"}
        </button>
      </div>

      {showFiles && (
        <div className="Card" style={{ maxWidth: '800px', margin: '0 auto 2rem auto', textAlign: 'left' }}>
          <h3>Processed Files</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <h4 style={{ color: '#6366f1' }}>Past Papers</h4>
              <ul style={{ fontSize: '0.9rem', color: '#94a3b8' }}>
                {files.past_papers.map((f, i) => <li key={i}>{f}</li>)}
                {files.past_papers.length === 0 && <li>No papers found.</li>}
              </ul>
            </div>
            <div>
              <h4 style={{ color: '#6366f1' }}>Lecture Slides</h4>
              <ul style={{ fontSize: '0.9rem', color: '#94a3b8' }}>
                {files.lecture_slides.map((f, i) => <li key={i}>{f}</li>)}
                {files.lecture_slides.length === 0 && <li>No slides found.</li>}
              </ul>
            </div>
          </div>
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
