import { useState, useEffect } from 'react';
import CommonHeader from '../components/CommonHeader';
import './ModelPaperPage.css';

// When behind gateway use /papers; else VITE_PAPERS_API_URL (e.g. http://localhost:8001)
const API_BASE = import.meta.env.VITE_PAPERS_API_URL || '/papers';

function ModelPaperPage() {
  const [logs, setLogs] = useState(["Welcome to AI Paper Generator. Ready to start."]);
  const [processing, setProcessing] = useState(false);
  const [paper, setPaper] = useState(null);
  const [status, setStatus] = useState("Idle");
  const [showNotesModal, setShowNotesModal] = useState(false);
  const [selectedQuestion, setSelectedQuestion] = useState(null);
  const [shortNotes, setShortNotes] = useState(null);
  const [loadingNotes, setLoadingNotes] = useState(false);
  const [notification, setNotification] = useState(null);
  const [files, setFiles] = useState({ past_papers: [], lecture_slides: [] });

  // User-configurable generation parameters
  const [numSlots, setNumSlots] = useState(4); // stepper: 1–8
  const [semesterBias, setSemesterBias] = useState('both'); // 'both' | 'sem1' | 'sem2'
  const [paperFileSelection, setPaperFileSelection] = useState({}); // { [filename]: boolean } (default true)

  const parsePastPaper = (file) => {
    const name = String(file || "");
    const match = name.match(/(20\d{2})/);
    const year = match ? Number(match[1]) : null;
    const isSem2 = /\bII\b/i.test(name) || /sem\s*ii/i.test(name) || /semester\s*ii/i.test(name);
    const sem = isSem2 ? "sem2" : "sem1";
    return { year, sem, file: name };
  };

  const computeSelectedPapers = () => {
    const parsed = (files.past_papers || [])
      .filter((f) => paperFileSelection[String(f)] !== false)
      .map(parsePastPaper)
      .filter((p) => p.year !== null);

    // Group by year to know if a year has both sems or only one.
    const byYear = parsed.reduce((acc, p) => {
      acc[p.year] = acc[p.year] || { sem1: [], sem2: [] };
      acc[p.year][p.sem].push(p);
      return acc;
    }, {});

    const years = Object.keys(byYear).map((y) => Number(y)).sort((a, b) => a - b);

    const selected = [];

    for (const year of years) {
      const g = byYear[year];
      const hasSem1 = (g.sem1 || []).length > 0;
      const hasSem2 = (g.sem2 || []).length > 0;

      // If only one semester exists for that year, always include it.
      if (hasSem1 && !hasSem2) {
        selected.push(...g.sem1);
        continue;
      }
      if (hasSem2 && !hasSem1) {
        selected.push(...g.sem2);
        continue;
      }

      // If both exist, apply semesterBias.
      if (semesterBias === "both") {
        selected.push(...g.sem1, ...g.sem2);
      } else if (semesterBias === "sem1") {
        selected.push(...g.sem1);
      } else if (semesterBias === "sem2") {
        selected.push(...g.sem2);
      }
    }

    // Stable order: year asc, sem1 before sem2, then filename asc
    selected.sort((a, b) => {
      if (a.year !== b.year) return a.year - b.year;
      if (a.sem !== b.sem) return a.sem === "sem1" ? -1 : 1;
      return a.file.localeCompare(b.file);
    });

    return selected;
  };

  const showNotification = (message) => {
    setNotification(message);
  };

  const addLog = (msg) => {
    setLogs(prev => [...prev.slice(-50), `[${new Date().toLocaleTimeString()}] ${msg}`]);
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

  const fetchFiles = async () => {
    try {
      const resp = await fetch(`${API_BASE}/files`);
      if (resp.ok) {
        const data = await resp.json();
        setFiles({
          past_papers: data.past_papers || [],
          lecture_slides: data.lecture_slides || [],
        });
      }
    } catch (err) {
      // Ignore if files endpoint fails
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      checkLatestPaper();
      fetchFiles();
    }, 100);
    return () => clearTimeout(timer);
  }, []);

  // Keep selection synced with uploads: new files default to selected.
  useEffect(() => {
    const list = files.past_papers || [];
    setPaperFileSelection((prev) => {
      const next = { ...prev };
      for (const f of list) {
        const key = String(f);
        if (next[key] === undefined) next[key] = true;
      }
      // Remove stale keys
      for (const k of Object.keys(next)) {
        if (!list.includes(k)) delete next[k];
      }
      return next;
    });
  }, [files.past_papers]);

  const handleUpload = async (file, type) => {
    if (!file) return;
    const name = (file.name || "").toLowerCase();
    if (!name.endsWith(".pdf")) {
      addLog(`Error: Only PDF format is allowed. Rejected: ${file.name}`);
      showNotification("Only PDF format is acceptable. Please select a .pdf file.");
      return;
    }

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
      if (!resp.ok) {
        addLog(`Error: ${data.detail || "Upload failed"}`);
        showNotification(data.detail || "Upload failed. Only PDF format is acceptable.");
        return;
      }
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

    const selectedPapers = computeSelectedPapers().map(({ year, sem, file }) => ({ year, sem, file }));

    const payload = {
      num_slots: numSlots,
      selected_papers: selectedPapers,
      semester_bias: semesterBias,
    };

    try {
      const resp = await fetch(`${API_BASE}/model-paper/generate-paper`, {
        method: "POST",
        headers: {
          'Cache-Control': 'no-cache',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
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
      // Try to load the latest paper from disk anyway (it may exist from a prior run)
      try {
        const fallbackResp = await fetch(`${API_BASE}/model-paper/paper-json`);
        if (fallbackResp.ok) {
          const fallbackData = await fallbackResp.json();
          setPaper(fallbackData);
          addLog("Loaded latest paper from disk.");
          setStatus("Paper loaded (from disk)");
        }
      } catch (_) {
        // Ignore fallback errors
      }
    } finally {
      setProcessing(false);
    }
  };

  const downloadPDF = () => {
    window.open(`${API_BASE}/model-paper/download-pdf`, "_blank");
  };

  const fetchShortNotes = async (questionNo, question) => {
    setSelectedQuestion({ questionNo, question });
    setShowNotesModal(true);
    setLoadingNotes(true);
    setShortNotes(null);
    
    try {
      const resp = await fetch(`${API_BASE}/model-paper/short-notes/${questionNo}`);
      if (!resp.ok) {
        throw new Error("Failed to fetch short notes");
      }
      const data = await resp.json();
      setShortNotes(data.short_notes);
    } catch (err) {
      setShortNotes(`Error loading short notes: ${err.message}`);
    } finally {
      setLoadingNotes(false);
    }
  };

  useEffect(() => {
    if (!notification) return;
    const t = setTimeout(() => setNotification(null), 5000);
    return () => clearTimeout(t);
  }, [notification]);

  return (
    <>
      <CommonHeader />
      {notification && (
        <div className="NotificationOverlay" onClick={() => setNotification(null)}>
          <div className="NotificationBox" onClick={(e) => e.stopPropagation()}>
            <p className="NotificationMessage">{notification}</p>
            <button type="button" className="Btn NotificationBtn" onClick={() => setNotification(null)}>OK</button>
          </div>
        </div>
      )}
      <div className="Dashboard">
        <header>
          <h1>Agentic AI Paper Generator</h1>
          <p>Pro-Level Exam Question Generation with Self-Correcting Agents</p>
        </header>

        <div className="ActionGrid UploadGrid">
          <div className="Card CardCompact">
            <div className="IconBox">📄</div>
            <h3>Past Papers</h3>
            <p>Upload PDF past papers to establish the exam style and structure.</p>
            <label className="Btn">
              Upload PDF
              <input type="file" className="UploadInput" accept=".pdf,application/pdf" onChange={(e) => handleUpload(e.target.files[0], "past")} />
            </label>
          </div>

          <div className="Card CardCompact">
            <div className="IconBox">📚</div>
            <h3>Lecture Slides</h3>
            <p>Upload slides to provide context for the local researcher agent.</p>
            <label className="Btn">
              Upload PDF
              <input type="file" className="UploadInput" accept=".pdf,application/pdf" onChange={(e) => handleUpload(e.target.files[0], "slides")} />
            </label>
          </div>
        </div>

        <div className="FullWidthSection">
          <div className="Card CardFocus">
            <div className="IconBox">⚙️</div>
            <h3>Generation Settings</h3>
            <p>Customize how the model paper is structured and sourced.</p>

            <div className="SettingsGroup">
              <div className="SettingsRow">
                <div className="SettingsRowTitle">Number of main questions</div>
                <div className="Stepper">
                  <button
                    type="button"
                    className="StepperBtn"
                    onClick={() => setNumSlots((n) => Math.max(1, n - 1))}
                    disabled={processing || numSlots <= 1}
                    aria-label="Decrease number of questions"
                  >
                    −
                  </button>
                  <div className="StepperValue">
                    <div className="StepperNumber">{numSlots}</div>
                    <div className="StepperHint">Q1 – Q{numSlots}</div>
                  </div>
                  <button
                    type="button"
                    className="StepperBtn"
                    onClick={() => setNumSlots((n) => Math.min(8, n + 1))}
                    disabled={processing || numSlots >= 8}
                    aria-label="Increase number of questions"
                  >
                    +
                  </button>
                </div>
              </div>

              <div className="SettingsRow">
                <div className="SettingsRowTitle">Past papers to consider</div>
                <div className="PaperPickerHeader">
                  <div className="SettingsHint" style={{ marginTop: 0 }}>
                    Uploaded past papers appear here automatically. New uploads are selected by default.
                  </div>
                  <div className="PaperPickerActions">
                    <button
                      type="button"
                      className="MiniBtn"
                      disabled={processing || (files.past_papers || []).length === 0}
                      onClick={() => {
                        const list = files.past_papers || [];
                        const next = {};
                        list.forEach((f) => { next[String(f)] = true; });
                        setPaperFileSelection(next);
                      }}
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      className="MiniBtn"
                      disabled={processing || (files.past_papers || []).length === 0}
                      onClick={() => {
                        const list = files.past_papers || [];
                        const next = {};
                        list.forEach((f) => { next[String(f)] = false; });
                        setPaperFileSelection(next);
                      }}
                    >
                      Clear
                    </button>
                  </div>
                </div>

                {(files.past_papers || []).length === 0 ? (
                  <div className="SettingsHint" style={{ marginTop: 0.5 }}>
                    No past papers uploaded yet.
                  </div>
                ) : (
                  <div className="PaperList" role="list" aria-label="Past papers list">
                    {(files.past_papers || []).map((f) => {
                      const key = String(f);
                      const checked = paperFileSelection[key] !== false;
                      return (
                        <label key={key} className="PaperRow" role="listitem">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={processing}
                            onChange={() =>
                              setPaperFileSelection((prev) => ({ ...prev, [key]: !(prev[key] !== false) }))
                            }
                          />
                          <span className="PaperName">{key}</span>
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="SettingsRow">
                <div className="SettingsRowTitle">Semester style</div>
                <div className="PillRow" role="tablist" aria-label="Semester style">
                  <button
                    type="button"
                    className={`Pill ${semesterBias === 'both' ? 'PillOn' : ''}`}
                    onClick={() => setSemesterBias('both')}
                    disabled={processing}
                  >
                    Both semesters
                  </button>
                  <button
                    type="button"
                    className={`Pill ${semesterBias === 'sem1' ? 'PillOn' : ''}`}
                    onClick={() => setSemesterBias('sem1')}
                    disabled={processing}
                  >
                    Semester I only
                  </button>
                  <button
                    type="button"
                    className={`Pill ${semesterBias === 'sem2' ? 'PillOn' : ''}`}
                    onClick={() => setSemesterBias('sem2')}
                    disabled={processing}
                  >
                    Semester II only
                  </button>
                </div>
                <div className="SettingsHint">
                  Years with only one semester available are always included regardless of this setting
                </div>
              </div>

              {(() => {
                const selected = computeSelectedPapers();
                const total = selected.length;
                const semStyle =
                  semesterBias === "both" ? "Sem I + II" : semesterBias === "sem1" ? "Sem I only" : "Sem II only";

                return (
                  <div className="StatsRow" aria-label="Selection summary">
                    <div className="StatChip">
                      <div className="StatLabel">Papers</div>
                      <div className="StatValue">{total}</div>
                    </div>
                    <div className="StatChip">
                      <div className="StatLabel">Questions</div>
                      <div className="StatValue">{numSlots}</div>
                    </div>
                    <div className="StatChip">
                      <div className="StatLabel">Semester style</div>
                      <div className="StatValue">{semStyle}</div>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        </div>

        <div className="GenerationCardWrap">
          <div className="Card">
            <div className="IconBox">🤖</div>
            <h3>AI Generation</h3>
            <p>Extract knowledge from all new uploads and generate the final paper.</p>
            <button className="Btn" onClick={generatePaper} disabled={processing}>
              {processing ? "Generating..." : "Generate Paper"}
            </button>
          </div>
        </div>

      <div className="ProcessedFilesSection">
        <h3>Existing Files</h3>
        <div className="ProcessedFilesGrid">
          <div className="ProcessedFilesCard">
            <h4>📄 Past Papers</h4>
            {files.past_papers.length === 0 ? (
              <p className="ProcessedFilesEmpty">No past papers uploaded yet.</p>
            ) : (
              <ul className="ProcessedFilesList">
                {files.past_papers.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="ProcessedFilesCard">
            <h4>📚 Lecture Slides</h4>
            {files.lecture_slides.length === 0 ? (
              <p className="ProcessedFilesEmpty">No lecture slides uploaded yet.</p>
            ) : (
              <ul className="ProcessedFilesList">
                {files.lecture_slides.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      <div className="StatusSection">
        <h3>System Status: <span style={{ color: '#2a5a94' }}>{status}</span></h3>
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <strong>Question {q.question_no} ({q.marks} Marks)</strong>
                <button
                  onClick={() => fetchShortNotes(q.question_no, q)}
                  style={{
                    background: 'transparent',
                    border: '1px solid #2a5a94',
                    borderRadius: '0.5rem',
                    padding: '0.5rem 0.75rem',
                    cursor: 'pointer',
                    color: '#2a5a94',
                    fontSize: '1.2rem',
                    transition: 'all 0.2s',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}
                  onMouseEnter={(e) => {
                    e.target.style.background = 'rgba(42, 90, 148, 0.1)';
                    e.target.style.borderColor = '#234a7a';
                  }}
                  onMouseLeave={(e) => {
                    e.target.style.background = 'transparent';
                    e.target.style.borderColor = '#2a5a94';
                  }}
                  title="View Short Notes"
                >
                  <span>✉️</span>
                  <span style={{ fontSize: '0.9rem' }}>Short Notes</span>
                </button>
              </div>
              <div style={{ 
                whiteSpace: 'pre-wrap', 
                marginTop: '1rem', 
                color: '#000',
                wordWrap: 'break-word',
                overflowWrap: 'break-word',
                maxHeight: 'none',
                overflow: 'visible',
                lineHeight: '1.6'
              }}>
                {q.text}
              </div>
              {/* Display diagram if available */}
              {q.diagram_image_path && q.diagram_generated && (
                <div style={{ marginTop: '1.5rem', textAlign: 'center' }}>
                  <img 
                    src={`${API_BASE}/model-paper/diagram-image?question_no=${q.question_no}`}
                    alt={`${q.diagram_type || 'Diagram'} for ${q.question_no}`}
                    style={{
                      maxWidth: '100%',
                      height: 'auto',
                      borderRadius: '0.5rem',
                      border: '1px solid #e2e8f0',
                      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)'
                    }}
                    onError={(e) => {
                      console.error('Failed to load diagram image');
                      e.target.style.display = 'none';
                    }}
                  />
                  {q.diagram_type && (
                    <p style={{ 
                      marginTop: '0.5rem', 
                      color: '#000', 
                      fontSize: '0.9rem',
                      fontStyle: 'italic'
                    }}>
                      Figure: {q.diagram_type} Diagram
                    </p>
                  )}
                </div>
              )}
              {/* Show subquestions if they exist */}
              {q.subquestions && q.subquestions.length > 0 && (
                <div style={{ marginTop: '1rem', paddingLeft: '1rem' }}>
                  {q.subquestions.map((sq, sqIdx) => (
                    <div key={sqIdx} style={{ marginBottom: '0.75rem', color: '#000' }}>
                      <strong style={{ color: '#000' }}>
                        {sq.label ? `${sq.label})` : ''} 
                        {sq.marks ? ` (${sq.marks} marks)` : ''}
                      </strong>
                      <div style={{ 
                        marginTop: '0.5rem',
                        whiteSpace: 'pre-wrap',
                        wordWrap: 'break-word',
                        overflowWrap: 'break-word',
                        color: '#000'
                      }}>
                        {sq.text}
                      </div>
                      {/* Handle nested subquestions (for Q4 part a with i, ii, iii) */}
                      {sq.subquestions && sq.subquestions.length > 0 && (
                        <div style={{ marginTop: '0.5rem', paddingLeft: '1rem' }}>
                          {sq.subquestions.map((nsq, nsqIdx) => (
                            <div key={nsqIdx} style={{ marginBottom: '0.5rem', color: '#000' }}>
                              <strong style={{ color: '#000' }}>
                                {nsq.label ? `${nsq.label})` : ''} 
                                {nsq.marks ? ` (${nsq.marks} marks)` : ''}
                              </strong>
                              <div style={{ 
                                marginTop: '0.25rem',
                                whiteSpace: 'pre-wrap',
                                wordWrap: 'break-word',
                                overflowWrap: 'break-word',
                                color: '#000'
                              }}>
                                {nsq.text}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Short Notes Modal */}
      {showNotesModal && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '2rem'
          }}
          onClick={() => setShowNotesModal(false)}
        >
          <div 
            style={{
              background: '#fff',
              border: '1px solid #e2e8f0',
              borderRadius: '1.5rem',
              padding: '2rem',
              maxWidth: '800px',
              maxHeight: '80vh',
              overflowY: 'auto',
              width: '100%',
              position: 'relative',
              boxShadow: '0 20px 40px rgba(0, 0, 0, 0.15)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <h2 style={{ margin: 0, color: '#2a5a94' }}>
                Short Notes: Question {selectedQuestion?.questionNo}
              </h2>
              <button
                onClick={() => setShowNotesModal(false)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#000',
                  fontSize: '1.5rem',
                  cursor: 'pointer',
                  padding: '0.5rem',
                  borderRadius: '0.5rem',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.target.style.background = '#f1f5f9';
                  e.target.style.color = '#000';
                }}
                onMouseLeave={(e) => {
                  e.target.style.background = 'transparent';
                  e.target.style.color = '#000';
                }}
              >
                ✕
              </button>
            </div>
            
            {loadingNotes ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#000' }}>
                <p>Generating short notes from lecture slides...</p>
                <p style={{ fontSize: '0.9rem', marginTop: '0.5rem' }}>This may take a few seconds</p>
              </div>
            ) : shortNotes ? (
              <div 
                style={{
                  color: '#000',
                  lineHeight: '1.8',
                  whiteSpace: 'pre-wrap',
                  wordWrap: 'break-word'
                }}
                dangerouslySetInnerHTML={{
                  __html: shortNotes
                    .replace(/\*\*(.*?)\*\*/g, '<strong style="color: #000;">$1</strong>')
                    .replace(/\*(.*?)\*/g, '<em>$1</em>')
                    .replace(/^### (.*$)/gm, '<h3 style="color: #2a5a94; margin-top: 1.5rem; margin-bottom: 0.5rem;">$1</h3>')
                    .replace(/^## (.*$)/gm, '<h2 style="color: #2a5a94; margin-top: 2rem; margin-bottom: 1rem;">$1</h2>')
                    .replace(/^# (.*$)/gm, '<h1 style="color: #2a5a94; margin-top: 2rem; margin-bottom: 1rem;">$1</h1>')
                    .replace(/^- (.*$)/gm, '<li style="margin-left: 1.5rem; margin-bottom: 0.5rem; color: #000;">$1</li>')
                    .replace(/\n/g, '<br>')
                }}
              />
            ) : null}
          </div>
        </div>
      )}
      </div>
    </>
  );
}

export default ModelPaperPage;
