import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  FaGraduationCap,
  FaBook,
  FaFilePdf,
  FaRocket,
  FaClipboard,
  FaBookOpen,
  FaCheck,
  FaCopy,
  FaThumbsUp,
  FaThumbsDown,
  FaEdit,
  FaSpinner,
  FaDownload
} from 'react-icons/fa';
import { HiMiniSparkles } from 'react-icons/hi2';
import { BsDiagram3Fill } from 'react-icons/bs';
import { PiCardsFill } from 'react-icons/pi';
import { MdAssignment } from 'react-icons/md';
import CommonHeader from '../components/CommonHeader';
import { useAuth } from '../context/AuthContext';
import './GuidancePage.css';
import ERDiagramGeneratorPage from '../er/ERDiagramGeneratorPage';

const normalizeApiBase = (value, suffix) => {
  const raw = String(value || '').trim().replace(/\/+$/, '');
  if (!raw) return suffix;
  return raw.endsWith(suffix) ? raw : `${raw}${suffix}`;
};

// When behind gateway use /guidance; else VITE_API_URL (e.g. http://localhost:8000)
const API_URL = normalizeApiBase(import.meta.env.VITE_API_URL, '/guidance');

const getAuthHeaders = () => {
  const token = localStorage.getItem('authToken');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const authFetch = (input, init = {}) => {
  const headers = { ...(init.headers || {}), ...getAuthHeaders() };
  return fetch(input, { ...init, headers });
};

function GuidancePage() {
  const { user } = useAuth();
  const [assignmentFile, setAssignmentFile] = useState(null);
  const [sqlDatasetFiles, setSqlDatasetFiles] = useState([]);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [summaryTopic, setSummaryTopic] = useState('');
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryAudio, setSummaryAudio] = useState(null);
  const [flashcardTopic, setFlashcardTopic] = useState('');
  const [flashcards, setFlashcards] = useState(null);
  const [flashLoading, setFlashLoading] = useState(false);
  const [selectedBloomLevel, setSelectedBloomLevel] = useState(null);
  // Flashcard feedback state
  const [flashcardSetId, setFlashcardSetId] = useState(null);
  const [flashcardFeedbackOpen, setFlashcardFeedbackOpen] = useState({}); // {cardId: true/false}
  const [flashcardFeedbackType, setFlashcardFeedbackType] = useState({}); // {cardId: 'add_examples' | 'simplify' | etc}
  const [flashcardFeedbackComment, setFlashcardFeedbackComment] = useState({}); // {cardId: 'comment'}
  const [flashcardFeedbackLoading, setFlashcardFeedbackLoading] = useState({}); // {cardId: true/false}
  const [flashcardImproving, setFlashcardImproving] = useState({}); // {cardId: true/false}
  const [flashcardLiked, setFlashcardLiked] = useState({}); // {cardId: true/false} - tracks "Yes" clicks
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
  const [summaryFeedbackOpen, setSummaryFeedbackOpen] = useState(false); // Show feedback form
  const [summaryLiked, setSummaryLiked] = useState(false); // Track "Yes" clicks
  const [summaryFeedbackType, setSummaryFeedbackType] = useState(null); // add_examples, simplify, etc.
  const [loadedTopic, setLoadedTopic] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [baseSummary, setBaseSummary] = useState(null);
  const [reinforcedSummary, setReinforcedSummary] = useState(null);
  const [activeSummaryView, setActiveSummaryView] = useState('base'); // 'base' or 'reinforced'
  const [forceRegenerate, setForceRegenerate] = useState(false);
  const [forceRegenerateFlashcards, setForceRegenerateFlashcards] = useState(false);
  const [lastFeedbackId, setLastFeedbackId] = useState(null); // Store feedback_id after submission
  // Guidance reinforcement state (same style as summarization)
  const [guidanceId, setGuidanceId] = useState(null);
  const [baseGuidanceContent, setBaseGuidanceContent] = useState(null);
  const [baseGuidanceImages, setBaseGuidanceImages] = useState([]);
  const [reinforcedGuidanceContent, setReinforcedGuidanceContent] = useState(null);
  const [reinforcedGuidanceImages, setReinforcedGuidanceImages] = useState([]);
  const [activeGuidanceView, setActiveGuidanceView] = useState('base');
  const [guidanceFeedbackOpen, setGuidanceFeedbackOpen] = useState(false);
  const [guidanceLiked, setGuidanceLiked] = useState(false);
  const [guidanceFeedbackType, setGuidanceFeedbackType] = useState(null);
  const [guidanceConfusedConcept, setGuidanceConfusedConcept] = useState('');
  const [guidanceFeedbackComment, setGuidanceFeedbackComment] = useState('');
  const [guidanceDeadlineText, setGuidanceDeadlineText] = useState('');
  const [guidanceFeedbackRating, setGuidanceFeedbackRating] = useState(null);
  const [guidanceFeedbackLoading, setGuidanceFeedbackLoading] = useState(false);
  const [guidanceReinforceLoading, setGuidanceReinforceLoading] = useState(false);
  const [guidanceReinforceError, setGuidanceReinforceError] = useState(null);
  const [guidanceFeedbackError, setGuidanceFeedbackError] = useState(null);
  const [guidanceReinforceSuccess, setGuidanceReinforceSuccess] = useState(false);
  const [guidanceCalendarEventMessage, setGuidanceCalendarEventMessage] = useState(null);
  const [guidanceSessionId, setGuidanceSessionId] = useState(null);
  const [lastGuidanceFeedbackId, setLastGuidanceFeedbackId] = useState(null);
  const [guidancePdfLoading, setGuidancePdfLoading] = useState(false);
  const [guidancePdfError, setGuidancePdfError] = useState(null);
  const [modalOpen, setModalOpen] = useState(null); // 'guidance' | 'summarize' | 'flashcards' | 'er' | null
  const assignmentFileInputRef = useRef(null);
  const sqlDatasetInputRef = useRef(null);

  // Ensure bare URLs in markdown become clickable links [url](url)
  const ensureLinksInMarkdown = (text) => {
    if (!text || typeof text !== 'string') return text;
    return text.replace(/(?<!\]\()(https?:\/\/[^\s)\]>\"]+)/g, (url) => `[${url}](${url})`);
  };

  /** Only transform segments that are not inside ``` … ``` fences (avoids mangling SQL/HTML examples). */
  const transformOutsideFencedCode = (text, fn) => {
    if (!text || typeof text !== 'string') return text;
    const lines = text.split('\n');
    let i = 0;
    const parts = [];
    while (i < lines.length) {
      if (lines[i].trimStart().startsWith('```')) {
        const start = i;
        i += 1;
        while (i < lines.length && !/^`{3,}\s*$/.test(lines[i].trim())) {
          i += 1;
        }
        if (i < lines.length) {
          parts.push(lines.slice(start, i + 1).join('\n'));
          i += 1;
        } else {
          parts.push(lines.slice(start).join('\n'));
          break;
        }
      } else {
        const start = i;
        while (i < lines.length && !lines[i].trimStart().startsWith('```')) {
          i += 1;
        }
        const chunk = lines.slice(start, i).join('\n');
        parts.push(fn(chunk));
      }
    }
    return parts.join('\n');
  };

  // If the whole payload is wrapped in ```markdown … ```, unwrap using the *last* closing fence
  // so nested ```sql …``` blocks inside the report do not truncate the body.
  const unwrapMarkdownFromCodeBlock = (text) => {
    if (!text || typeof text !== 'string') return text;
    const trimmed = text.trim();
    if (!trimmed.startsWith('```')) return text;
    const firstNl = trimmed.indexOf('\n');
    if (firstNl === -1) return text;
    const opener = trimmed.slice(0, firstNl).trim();
    if (!/^```(?:markdown|md)?$/.test(opener)) return text;
    const afterOpen = trimmed.slice(firstNl + 1);
    const closeIdx = afterOpen.lastIndexOf('\n```');
    if (closeIdx === -1) return text;
    const afterClose = afterOpen.slice(closeIdx + 1).trim();
    // Closing fence only (optional whitespace / newlines after it) — no trailing junk
    if (!/^`{3,}\s*$/s.test(afterClose)) return text;
    return afterOpen.slice(0, closeIdx).trim();
  };

  // Convert backend <figure><img ...><figcaption>...</figcaption></figure> to markdown so
  // ensureLinksInMarkdown never corrupts src="https://..." and React/rehype do not see broken tags.
  const figureHtmlToGuidanceMarkdown = (figureHtml, apiBase) => {
    const srcMatch = figureHtml.match(/\bsrc=(["'])([^"']+)\1/i);
    if (!srcMatch) return figureHtml;
    let src = srcMatch[2].trim();
    const altMatch = figureHtml.match(/\balt=(["'])([^"']*)\1/i);
    let alt = (altMatch && altMatch[2] ? String(altMatch[2]) : 'Diagram').replace(/\]/g, '').trim() || 'Diagram';
    const capMatch = figureHtml.match(/<figcaption\b[^>]*>([\s\S]*?)<\/figcaption>/i);
    const cap = capMatch
      ? String(capMatch[1])
          .replace(/<[^>]+>/g, ' ')
          .replace(/\s+/g, ' ')
          .trim()
      : '';
    const b = String(apiBase || '').replace(/\/$/, '');
    if (b) {
      if (src.startsWith('/api/images/') && !src.startsWith(`${b}/`) && src !== b) {
        src = `${b}${src}`;
      }
      if (src.startsWith('/guidance/api/images/')) {
        src = `${b}${src.replace(/^\/guidance/, '')}`;
      }
    }
    let md = `![${alt}](${src})`;
    if (cap) md += `\n\n*${cap}*`;
    return md;
  };

  const standaloneImgHtmlToMarkdown = (imgTag, apiBase) => {
    const srcMatch = imgTag.match(/\bsrc=(["'])([^"']+)\1/i);
    if (!srcMatch) return imgTag;
    let src = srcMatch[2].trim();
    const altMatch = imgTag.match(/\balt=(["'])([^"']*)\1/i);
    let alt = (altMatch && altMatch[2] ? String(altMatch[2]) : 'Diagram').replace(/\]/g, '').trim() || 'Diagram';
    const b = String(apiBase || '').replace(/\/$/, '');
    if (b) {
      if (src.startsWith('/api/images/') && !src.startsWith(`${b}/`) && src !== b) {
        src = `${b}${src}`;
      }
      if (src.startsWith('/guidance/api/images/')) {
        src = `${b}${src.replace(/^\/guidance/, '')}`;
      }
    }
    return `![${alt}](${src})`;
  };

  const escapeUnsafeHtmlishSegment = (segment) =>
    String(segment || '')
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/<\/?[A-Za-z][A-Za-z0-9:-]*(?:\s[^<>]*)?>/g, (tag) => `\`${tag.replace(/`/g, '\\`')}\``)
      .replace(/<[^<>\n]{1,120}>/g, (tag) => `\`${tag.replace(/`/g, '\\`')}\``);

  // Guidance report: expand [IMAGE:file] to real markdown images; normalize HTML figures/images
  const prepareGuidanceMarkdown = (text) => {
    if (!text || typeof text !== 'string') return text;
    let out = unwrapMarkdownFromCodeBlock(text);
    const base = String(API_URL || '').replace(/\/$/, '');

    const applyFigureImgAndImageTokens = (segment) => {
      let s = segment;
      s = s.replace(/<figure>[\s\S]*?<\/figure>/gi, (block) => figureHtmlToGuidanceMarkdown(block, base));
      s = s.replace(/<img\b[^>]*\/?>/gi, (tag) => standaloneImgHtmlToMarkdown(tag, base));
      s = s.replace(/\[IMAGE:\s*([^\]]+)\]/gi, (_, raw) => {
        const name = String(raw).trim();
        if (!name) return _;
        const enc = encodeURIComponent(name);
        const path = `/api/images/${enc}`;
        const url = base ? `${base}${path}` : path;
        return `![Diagram](${url})`;
      });
      s = s
        .replace(/<imgsrc=/gi, '<img src=')
        .replace(/<img\/src=/gi, '<img src=')
        .replace(/<img\s+src=/gi, '<img src=');
      return s;
    };

    out = transformOutsideFencedCode(out, applyFigureImgAndImageTokens);
    out = transformOutsideFencedCode(out, escapeUnsafeHtmlishSegment);
    out = transformOutsideFencedCode(out, ensureLinksInMarkdown);

    return out;
  };

  // ✅ Helper: make a path absolute using API_URL
  const toAbsoluteUrl = (maybeRelativeUrl) => {
    if (!maybeRelativeUrl) return null;
    const url = String(maybeRelativeUrl).trim();
    if (!url) return null;

    if (url.startsWith('http://') || url.startsWith('https://')) return url;

    const base = String(API_URL || '').replace(/\/$/, '');
    if (!base) return url;

    if (url.startsWith('/')) {
      if (url === base || url.startsWith(`${base}/`)) return url;
      return `${base}${url}`;
    }
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

  const markdownAllowedElements = [
    'a', 'blockquote', 'br', 'code', 'del', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'hr', 'img', 'li', 'ol', 'p', 'pre', 'strong', 'table', 'tbody', 'td', 'th',
    'thead', 'tr', 'ul',
  ];

  // ✅ (AUDIO CHANGE) Remove markdown audio parsing - backend now returns audio_url separately
  // const extractAudioFromMarkdown = ...  ❌ REMOVED


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
    if (Array.isArray(sqlDatasetFiles) && sqlDatasetFiles.length > 0) {
      sqlDatasetFiles.forEach((f) => formData.append('sql_dataset', f));
    }

    try {
      const startedAt = Date.now();
      console.info('Guidance request started');
      const response = await authFetch(`${API_URL}/protected/run-guidance`, {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });
      console.info('Guidance response headers received:', {
        status: response.status,
        ok: response.ok,
        contentType: response.headers.get('content-type'),
        contentLength: response.headers.get('content-length'),
        elapsedMs: Date.now() - startedAt,
      });

      if (response.ok) {
        const responseText = await response.text();
        console.info('Guidance response body received:', {
          chars: responseText.length,
          elapsedMs: Date.now() - startedAt,
        });
        setLoading(false);

        let result;
        try {
          result = JSON.parse(responseText);
        } catch (parseError) {
          console.error('Guidance JSON parse failed:', parseError);
          setReport({
            error: `Guidance returned a non-JSON response (${responseText.length} chars). Check the gateway/backend terminal.`,
          });
          return;
        }

        const rep = (result?.report || result?.markdown_report || '').toString();
        if (!rep && result?.detail) {
          setReport({ error: typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail) });
          return;
        }
        console.log('Guidance API ok; report length (chars):', typeof rep === 'string' ? rep.length : 0);
        console.log('Guidance API query results count:', Array.isArray(result?.query_results) ? result.query_results.length : 0);

        const nextReport = {
          content: rep,
          images: result.images || [],
          query_results: result.query_results || [],
        };
        window.setTimeout(() => setReport(nextReport), 0);
        if (result.guidance_id) {
          setGuidanceId(result.guidance_id);
          setBaseGuidanceContent(rep);
          setBaseGuidanceImages(result.images || []);
          setReinforcedGuidanceContent(null);
          setReinforcedGuidanceImages([]);
          setActiveGuidanceView('base');
          setGuidanceSessionId(createSessionId());
          setGuidanceFeedbackOpen(false);
          setGuidanceLiked(false);
          setGuidanceFeedbackType(null);
          setGuidanceConfusedConcept('');
          setGuidanceFeedbackComment('');
          setGuidanceFeedbackRating(null);
          setGuidanceReinforceError(null);
          setGuidanceFeedbackError(null);
          setGuidanceReinforceSuccess(false);
          setGuidanceCalendarEventMessage(null);
          setGuidancePdfError(null);
        } else {
          setGuidanceId(null);
          setGuidanceCalendarEventMessage(null);
          setBaseGuidanceContent(null);
          setBaseGuidanceImages([]);
          setReinforcedGuidanceContent(null);
          setReinforcedGuidanceImages([]);
          setGuidancePdfError(null);
        }
      } else {
        let message = `Failed to run guidance (HTTP ${response.status}).`;
        try {
          const errData = await response.json();
          const d = errData?.detail;
          if (d !== undefined && d !== null) {
            message =
              typeof d === 'string'
                ? d
                : Array.isArray(d)
                  ? d
                      .map((x) => (x && typeof x === 'object' && x.msg != null ? x.msg : JSON.stringify(x)))
                      .join('; ')
                  : String(d);
          }
        } catch {
          /* non-JSON error body */
        }
        if (response.status === 504) {
          message =
            'The gateway timed out waiting for guidance (this can take many minutes). ' +
            'The backend may still be working—check its terminal, or restart the gateway with a higher GUIDANCE_PROXY_TIMEOUT. ' +
            'If the response eventually completes, try calling the service directly on port 8081.';
        }
        if (response.status === 401 || response.status === 403) {
          if (message.startsWith('Failed to run guidance (HTTP')) {
            message = 'Not authenticated. Sign in (e.g. with Google) and try again.';
          }
        }
        console.error('Failed to run guidance:', response.status, message);
        setReport({ error: message });
      }
    } catch (error) {
      console.error('Error running guidance:', error);
      setReport({ error: 'An error occurred while running the guidance.' });
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadGuidancePdf = async () => {
    const currentGuidanceContent =
      activeGuidanceView === 'reinforced' && reinforcedGuidanceContent
        ? reinforcedGuidanceContent
        : (baseGuidanceContent || report?.content || (typeof report === 'string' ? report : null));

    const currentGuidanceImages =
      activeGuidanceView === 'reinforced' && reinforcedGuidanceImages.length > 0
        ? reinforcedGuidanceImages
        : (baseGuidanceImages || report?.images || []);
    const currentQueryResults =
      Array.isArray(report?.query_results) ? report.query_results : [];

    if (!currentGuidanceContent) {
      setGuidancePdfError('No guidance content is available to download.');
      return;
    }

    setGuidancePdfLoading(true);
    setGuidancePdfError(null);

    try {
      const sourceName = assignmentFile?.name?.replace(/\.pdf$/i, '') || 'ca-guidance';
      const fileName = `${sourceName}-${activeGuidanceView || 'report'}.pdf`;
      const requestPayload = {
        report_content: currentGuidanceContent,
        images: currentGuidanceImages,
        query_results: currentQueryResults,
        title: activeGuidanceView === 'reinforced' ? 'Reinforced CA Guidance Report' : 'CA Guidance Report',
        file_name: fileName,
      };
      const imageTokenCount = (String(currentGuidanceContent || '').match(/\[IMAGE:\s*[^\]]+\]/gi) || []).length;
      console.info('Guidance PDF request payload:', {
        reportChars: String(currentGuidanceContent || '').length,
        imageCount: Array.isArray(currentGuidanceImages) ? currentGuidanceImages.length : 0,
        queryResultCount: currentQueryResults.length,
        imageTokenCount,
        activeGuidanceView,
        fileName,
      });

      const response = await authFetch(`${API_URL}/protected/guidance/download-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(requestPayload),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Failed to generate guidance PDF.' }));
        throw new Error(err.detail || 'Failed to generate guidance PDF.');
      }

      const blob = await response.blob();
      console.info('Guidance PDF response metadata:', {
        status: response.status,
        contentType: response.headers.get('content-type'),
        contentLength: response.headers.get('content-length'),
        blobSize: blob?.size ?? 0,
      });
      if ((blob?.size ?? 0) < 2500) {
        console.warn('Guidance PDF diagnostic: unusually small PDF blob size', {
          blobSize: blob?.size ?? 0,
          reportChars: String(currentGuidanceContent || '').length,
          imageCount: Array.isArray(currentGuidanceImages) ? currentGuidanceImages.length : 0,
          imageTokenCount,
        });
      }
      if (!blob || blob.size === 0) {
        throw new Error('Generated PDF is empty. Please try again.');
      }

      const url = window.URL.createObjectURL(blob);

      // Show PDF on screen (new tab) while still allowing a direct download fallback.
      let opened = null;
      try {
        opened = window.open(url, '_blank', 'noopener,noreferrer');
      } catch {
        opened = null;
      }

      // If popup/new-tab is blocked, force file download.
      if (!opened) {
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }

      // Keep object URL alive briefly so new-tab viewer can read it before cleanup.
      window.setTimeout(() => {
        try {
          window.URL.revokeObjectURL(url);
        } catch {
          // no-op
        }
      }, 30000);
    } catch (error) {
      console.error('Error downloading guidance PDF:', error);
      setGuidancePdfError(error.message || 'An error occurred while downloading the PDF.');
    } finally {
      setGuidancePdfLoading(false);
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
    setSummaryFeedbackOpen(false);
    setSummaryLiked(false);
    setSummaryFeedbackType(null);
    setSummary(null);
    setSummaryAudio(null); // ✅ clear old audio immediately

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
      const response = await authFetch(`${API_URL}/protected/summarize`, {
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

        // Fetch summaries and show the recent summary (reinforced if available, else base)
        try {
          const allSummariesResponse = await authFetch(`${API_URL}/protected/summaries/topic/${encodeURIComponent(requestedTopic)}`, {
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
            const reinforced = allSummaries.reinforced ? {
              ...allSummaries.reinforced,
              content: allSummaries.reinforced.summary_text,
              summary_id: allSummaries.reinforced.summary_id || allSummaries.reinforced._id,
              audio_url: toAbsoluteUrl(allSummaries.reinforced.audio_url),
              created_at: allSummaries.reinforced.created_at,
              audio_duration_seconds: allSummaries.reinforced.audio_duration_seconds ?? null
            } : null;

            if (base) setBaseSummary(base);
            if (reinforced) {
              setReinforcedSummary(reinforced);
              setReinforcementVisible(true);
            } else {
              setReinforcedSummary(null);
              setReinforcementVisible(false);
            }

            // Show recent summary: reinforced if available, else base
            const toShow = reinforced || base;
            if (toShow) {
              setActiveSummaryView(reinforced ? 'reinforced' : 'base');
              setSummary(toShow);
              setSummaryAudio(toShow.audio_url);
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
        let detail = errorData.detail || 'Failed to create summary. Make sure you are logged in.';
        if (response.status === 504) {
          detail =
            'The gateway timed out while summarizing (this can take many minutes). ' +
            'Check the academic-guidance service terminal or increase GUIDANCE_PROXY_TIMEOUT on the gateway.';
        }
        setSummary({ error: typeof detail === 'string' ? detail : JSON.stringify(detail) });
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
      const response = await authFetch(`${API_URL}/protected/summaries/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          topic: summary.topic,
          summary_id: summaryId,
          rating: feedbackRating,
          confused_concept: confusedConcept.trim() || null,
          comment: feedbackComment.trim() || null,
          feedback_type: summaryFeedbackType || null
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
      const feedbackResp = await authFetch(`${API_URL}/protected/summaries/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          topic: loadedTopic,
          summary_id: baseId,
          rating: feedbackRating,
          confused_concept: confusedConcept.trim() || null,
          comment: feedbackComment.trim() || null,
          feedback_type: summaryFeedbackType || null,
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
      setSummaryFeedbackOpen(false);
      setSummaryLiked(false);
      setSummaryFeedbackType(null);
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

  const handleSubmitGuidanceFeedbackAndReinforce = async () => {
    if (!guidanceId || !baseGuidanceContent) {
      alert('No guidance available to improve.');
      return;
    }
    if (!guidanceFeedbackRating) {
      alert('Please select whether the guidance was helpful or not.');
      return;
    }
    setGuidanceFeedbackLoading(true);
    setGuidanceReinforceLoading(true);
    setGuidanceFeedbackError(null);
    setGuidanceReinforceError(null);
    setGuidanceReinforceSuccess(false);
    try {
      const feedbackResp = await authFetch(`${API_URL}/protected/guidance/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          guidance_id: guidanceId,
          rating: guidanceFeedbackRating,
          confused_concept: guidanceConfusedConcept.trim() || null,
          comment: guidanceFeedbackComment.trim() || null,
          feedback_type: guidanceFeedbackType,
          deadline_text: guidanceFeedbackType === 'new_deadline_event' ? (guidanceDeadlineText.trim() || null) : null,
          session_id: guidanceSessionId,
        }),
      });
      if (!feedbackResp.ok) {
        const errData = await feedbackResp.json().catch(() => ({ detail: 'Failed to submit feedback' }));
        setGuidanceFeedbackError(errData.detail || 'Failed to submit feedback.');
        return;
      }
      const feedbackResult = await feedbackResp.json().catch(() => ({}));
      if (feedbackResult.feedback_id) setLastGuidanceFeedbackId(feedbackResult.feedback_id);

      const reinforceResp = await authFetch(`${API_URL}/protected/guidance/reinforce`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          guidance_id: guidanceId,
          force: true,
          feedback_id: feedbackResult.feedback_id,
          session_id: guidanceSessionId,
        }),
      });
      if (!reinforceResp.ok) {
        const errData = await reinforceResp.json().catch(() => ({ detail: 'Failed to generate reinforced guidance' }));
        setGuidanceReinforceError(errData.detail || 'Failed to generate reinforced guidance.');
        return;
      }
      const result = await reinforceResp.json();
      setReinforcedGuidanceContent(result.report);
      setReinforcedGuidanceImages(result.images || []);
      setReport({ content: result.report, images: result.images || [] });
      setActiveGuidanceView('reinforced');
      setGuidanceReinforceSuccess(true);
      setGuidanceCalendarEventMessage(result.calendar_event_message || null);
      setTimeout(() => { setGuidanceReinforceSuccess(false); setGuidanceCalendarEventMessage(null); }, 6000);
      setGuidanceFeedbackRating(null);
      setGuidanceConfusedConcept('');
      setGuidanceFeedbackComment('');
      setGuidanceDeadlineText('');
      setGuidanceFeedbackType(null);
      setGuidanceFeedbackOpen(false);
      setGuidanceLiked(false);
      setGuidancePdfError(null);
    } catch (error) {
      console.error('Error submitting guidance feedback and reinforcing:', error);
      setGuidanceReinforceError('An error occurred while generating reinforced guidance.');
    } finally {
      setGuidanceFeedbackLoading(false);
      setGuidanceReinforceLoading(false);
    }
  };

  const handleGenerateFlashcards = async (e) => {
    e.preventDefault();
    setFlashLoading(true);
    setFlashcards(null);
    setSelectedBloomLevel(null);
    setFlashcardSetId(null);
    setFlashcardFeedbackOpen({});
    setFlashcardFeedbackType({});
    setFlashcardFeedbackComment({});
    setFlashcardLiked({});

    if (!flashcardTopic || !flashcardTopic.trim()) {
      setFlashcards({ error: 'Please enter a topic to generate flashcards.' });
      setFlashLoading(false);
      return;
    }

    try {
      // Backend returns saved set or generates new based on force flag
      const response = await authFetch(`${API_URL}/protected/generate-flashcards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          topic: flashcardTopic.trim(),
          force: forceRegenerateFlashcards,
        }),
      });

      if (response.ok) {
        const result = await response.json();

        // Backend returned saved set (same concept as summarization from_cache — no need to save again)
        if ((result.from_saved || result.from_cache) && result.flashcard_set_id) {
          setFlashcardSetId(result.flashcard_set_id);
          setFlashcards({ topic: result.topic, flashcards: result.flashcards });
          const levels = Object.keys(result.flashcards || {});
          if (levels.length > 0) setSelectedBloomLevel(levels[0]);
          setFlashLoading(false);
          return;
        }

        // Newly generated: add unique IDs and save to database
        const flashcardsWithIds = {};
        for (const level of Object.keys(result.flashcards)) {
          flashcardsWithIds[level] = result.flashcards[level].map((card, i) => ({
            id: `${level}-${i}-${Date.now()}`,
            question: card.question,
            answer: card.answer
          }));
        }

        try {
          const saveResponse = await authFetch(`${API_URL}/protected/flashcards/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              topic: result.topic,
              flashcards: flashcardsWithIds
            }),
          });

          if (saveResponse.ok) {
            const savedData = await saveResponse.json();
            console.log('Flashcards saved successfully:', savedData.flashcard_set_id);
            setFlashcardSetId(savedData.flashcard_set_id);
            setFlashcards({ topic: result.topic, flashcards: savedData.flashcards });
          } else {
            const saveError = await saveResponse.json().catch(() => ({}));
            console.warn('Failed to save flashcards:', saveError);
            setFlashcards({ topic: result.topic, flashcards: flashcardsWithIds });
          }
        } catch (saveErr) {
          console.warn('Error saving flashcards:', saveErr);
          setFlashcards({ topic: result.topic, flashcards: flashcardsWithIds });
        }
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

  // Submit flashcard feedback (thumbs up/down)
  const handleFlashcardFeedback = async (cardId, bloomLevel, rating) => {
    if (!flashcardSetId) {
      console.error('No flashcard set ID available');
      return;
    }

    setFlashcardFeedbackLoading(prev => ({ ...prev, [cardId]: true }));
    
    // Immediately show visual feedback for "Yes" clicks
    if (rating === 'thumbs_up') {
      setFlashcardLiked(prev => ({ ...prev, [cardId]: true }));
    }

    try {
      const feedbackType = flashcardFeedbackType[cardId] || null;
      const comment = flashcardFeedbackComment[cardId] || null;

      const response = await authFetch(`${API_URL}/protected/flashcards/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          flashcard_set_id: flashcardSetId,
          flashcard_id: cardId,
          bloom_level: bloomLevel,
          rating: rating,
          feedback_type: feedbackType,
          comment: comment
        }),
      });

      if (response.ok) {
        const result = await response.json();
        
        // If thumbs down with feedback, automatically improve the card
        if (rating === 'thumbs_down' && (feedbackType || comment)) {
          await handleImproveFlashcard(cardId, bloomLevel, result.feedback_id);
        }

        // Close the feedback form
        setFlashcardFeedbackOpen(prev => ({ ...prev, [cardId]: false }));
        setFlashcardFeedbackType(prev => ({ ...prev, [cardId]: null }));
        setFlashcardFeedbackComment(prev => ({ ...prev, [cardId]: '' }));
      } else {
        console.error('Failed to submit feedback');
        // Revert the like if the API call failed
        if (rating === 'thumbs_up') {
          setFlashcardLiked(prev => ({ ...prev, [cardId]: false }));
        }
      }
    } catch (error) {
      console.error('Error submitting flashcard feedback:', error);
      // Revert the like if the API call failed
      if (rating === 'thumbs_up') {
        setFlashcardLiked(prev => ({ ...prev, [cardId]: false }));
      }
    } finally {
      setFlashcardFeedbackLoading(prev => ({ ...prev, [cardId]: false }));
    }
  };

  // Improve a flashcard based on feedback
  const handleImproveFlashcard = async (cardId, bloomLevel, feedbackId) => {
    if (!flashcardSetId) return;

    setFlashcardImproving(prev => ({ ...prev, [cardId]: true }));

    try {
      const response = await authFetch(`${API_URL}/protected/flashcards/improve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          flashcard_set_id: flashcardSetId,
          flashcard_id: cardId,
          bloom_level: bloomLevel,
          feedback_id: feedbackId
        }),
      });

      if (response.ok) {
        const result = await response.json();
        
        // Update the flashcard in state immediately (real-time update)
        setFlashcards(prev => {
          if (!prev || !prev.flashcards) return prev;
          
          const updatedFlashcards = { ...prev.flashcards };
          if (updatedFlashcards[bloomLevel]) {
            updatedFlashcards[bloomLevel] = updatedFlashcards[bloomLevel].map(card => {
              if (card.id === cardId) {
                return {
                  ...card,
                  question: result.updated_question,
                  answer: result.updated_answer,
                  improved: true,
                  improvement_notes: result.improvement_notes
                };
              }
              return card;
            });
          }
          
          return { ...prev, flashcards: updatedFlashcards };
        });
      } else {
        console.error('Failed to improve flashcard');
      }
    } catch (error) {
      console.error('Error improving flashcard:', error);
    } finally {
      setFlashcardImproving(prev => ({ ...prev, [cardId]: false }));
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
        <code className={className}>
          {children}
        </code>
      );
    },

    img({ node, src, alt, ...props }) {
      // ✅ Use the same absolute-url function for images too
      // Ensure /api/images/ paths are preserved
      let imageSrc = src;
      
      // If src doesn't start with http/https, make it absolute
      if (imageSrc && !imageSrc.startsWith('http://') && !imageSrc.startsWith('https://')) {
        if (imageSrc.startsWith('/guidance/api/images/')) {
          imageSrc = toAbsoluteUrl(imageSrc.replace(/^\/guidance/, ''));
        } else if (imageSrc.startsWith('/api/images/')) {
          imageSrc = toAbsoluteUrl(imageSrc);
        } else if (imageSrc.startsWith('/')) {
          // Other absolute paths
          imageSrc = toAbsoluteUrl(imageSrc);
        } else {
          // Relative paths - assume they're in /api/images/
          imageSrc = toAbsoluteUrl(`/api/images/${imageSrc}`);
        }
      }

      return (
        <img
          src={imageSrc}
          alt={alt || 'Image'}
          className="markdown-image"
          style={{ maxWidth: '100%', width: 'auto', height: 'auto' }}
          onError={(e) => {
            console.error('Failed to load image:', imageSrc, 'Original src:', src);
            e.target.style.display = 'none';
          }}
        />
      );
    },

    a({ node, href, children, ...props }) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: '#336db0', textDecoration: 'underline' }}
        >
          {children}
        </a>
      );
    },
  };

  const SafeMarkdown = ({ children }) => (
    <ReactMarkdown
      components={CodeBlock}
      remarkPlugins={[remarkGfm]}
      skipHtml
      unwrapDisallowed
      allowedElements={markdownAllowedElements}
    >
      {children}
    </ReactMarkdown>
  );

  const clearStateOnLogout = () => {
    setReport(null);
    setAssignmentFile(null);
    setSqlDatasetFiles([]);
    if (assignmentFileInputRef.current) assignmentFileInputRef.current.value = '';
    if (sqlDatasetInputRef.current) sqlDatasetInputRef.current.value = '';
    setSummary(null);
    setSummaryTopic('');
    setSummaryAudio(null);
    setGuidanceId(null);
    setBaseGuidanceContent(null);
    setReinforcedGuidanceContent(null);
  };

  return (
    <>
      <CommonHeader onLogout={clearStateOnLogout} />
      <div className="app-content">
          <div className="app-header">
            <h1>Educational Support and Guidance</h1>
            <p className="app-header-subtitle">Assignment guidance, lecture summaries, flashcards, and ER diagrams for your Continuous Assessment</p>
          </div>

          {user ? (
          <div>
            <div className="guidance-cards">
              <div className="guidance-card" onClick={() => setModalOpen('guidance')}>
                <div className="guidance-card-icon"><MdAssignment /></div>
                <h2 className="guidance-card-title">Assignment Guidance</h2>
                <p className="guidance-card-desc">Upload your assignment PDF and get personalized guidance and feedback.</p>
              </div>
              <div className="guidance-card" onClick={() => setModalOpen('summarize')}>
                <div className="guidance-card-icon"><FaBook /></div>
                <h2 className="guidance-card-title">Lecture Summaries</h2>
                <p className="guidance-card-desc">Enter a topic to get comprehensive summaries with relevant diagrams.</p>
              </div>
              <div className="guidance-card" onClick={() => setModalOpen('flashcards')}>
                <div className="guidance-card-icon"><PiCardsFill /></div>
                <h2 className="guidance-card-title">Flashcard Generator</h2>
                <p className="guidance-card-desc">Generate flashcards by topic with Bloom's Taxonomy levels.</p>
              </div>
              <div className="guidance-card" onClick={() => setModalOpen('er')}>
                <div className="guidance-card-icon"><BsDiagram3Fill /></div>
                <h2 className="guidance-card-title">ER Diagram Generator</h2>
                <p className="guidance-card-desc">Create and edit Entity-Relationship diagrams for your database course.</p>
              </div>
            </div>

            {modalOpen && (
              <div className="guidance-modal-overlay" onClick={() => setModalOpen(null)}>
                <div className="guidance-modal" onClick={(e) => e.stopPropagation()}>
                  <div className="guidance-modal-header">
                    <h2>
                      {modalOpen === 'guidance' && <><MdAssignment /> Assignment Guidance</>}
                      {modalOpen === 'summarize' && <><FaBook /> Lecture Summaries</>}
                      {modalOpen === 'flashcards' && <><PiCardsFill /> Flashcard Generator</>}
                      {modalOpen === 'er' && <><BsDiagram3Fill /> ER Diagram Generator</>}
                    </h2>
                    <button type="button" className="guidance-modal-close" onClick={() => setModalOpen(null)}>Close</button>
                  </div>
                  <div className="guidance-modal-body">
            {modalOpen === 'guidance' && (
              <div className="content-area">
                <form onSubmit={handleRunGuidance} className="form-container">
                  <div className="form-group">
                    <label className="form-label" htmlFor="assignment-file">
                      <FaFilePdf style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Upload Assignment PDF
                    </label>
                    <input
                      ref={assignmentFileInputRef}
                      id="assignment-file"
                      type="file"
                      accept="application/pdf"
                      onChange={(e) => setAssignmentFile(e.target.files[0])}
                      className="file-input"
                      required
                    />
                    {assignmentFile && (
                      <div className="info-message file-selected-message" style={{ marginTop: '10px' }}>
                        Selected: <strong>{assignmentFile.name}</strong>
                        <button
                          type="button"
                          className="file-clear-btn"
                          aria-label="Clear selected assignment file"
                          title="Clear file"
                          onClick={() => {
                            setAssignmentFile(null);
                            if (assignmentFileInputRef.current) assignmentFileInputRef.current.value = '';
                          }}
                        >
                          ×
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="sql-dataset-file">
                      Upload SQL Dataset (optional: .sql or .csv)
                    </label>
                    <input
                      ref={sqlDatasetInputRef}
                      id="sql-dataset-file"
                      type="file"
                      multiple
                      accept=".sql,.csv,text/csv,application/sql"
                      onChange={(e) => setSqlDatasetFiles(Array.from(e.target.files || []))}
                      className="file-input"
                    />
                    {sqlDatasetFiles.length > 0 && (
                      <div className="info-message file-selected-message" style={{ marginTop: '10px' }}>
                        SQL Datasets: <strong>{sqlDatasetFiles.map((f) => f.name).join(', ')}</strong>
                        <button
                          type="button"
                          className="file-clear-btn"
                          aria-label="Clear selected SQL dataset file"
                          title="Clear file"
                          onClick={() => {
                            setSqlDatasetFiles([]);
                            if (sqlDatasetInputRef.current) sqlDatasetInputRef.current.value = '';
                          }}
                        >
                          ×
                        </button>
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
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', marginBottom: '20px' }}>
                      <h2 style={{ marginBottom: 0, color: '#495057' }}>
                        <FaClipboard style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Guidance Report
                      </h2>
                      {!report.error && (report.content != null || typeof report === 'string') && (
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={handleDownloadGuidancePdf}
                          disabled={guidancePdfLoading}
                        >
                          {guidancePdfLoading ? (
                            <>
                              <FaSpinner className="loading-spinner" />
                              Preparing PDF...
                            </>
                          ) : (
                            <>
                              <FaDownload />
                              Download PDF
                            </>
                          )}
                        </button>
                      )}
                    </div>

                    {guidancePdfError && (
                      <div className="error-message" style={{ marginBottom: '16px' }}>
                        {guidancePdfError}
                      </div>
                    )}

                    {typeof report === 'string' ? (
                      <div className="report-content">
                        <SafeMarkdown>{prepareGuidanceMarkdown(report)}</SafeMarkdown>
                      </div>
                    ) : report.content ? (
                      <div className="report-content">
                        <SafeMarkdown>{prepareGuidanceMarkdown(report.content)}</SafeMarkdown>
                      </div>
                    ) : report.markdown_report ? (
                      <div className="report-content">
                        <SafeMarkdown>{prepareGuidanceMarkdown(report.markdown_report)}</SafeMarkdown>
                      </div>
                    ) : report.error ? (
                      <div className="error-message">{report.error}</div>
                    ) : (
                      <div className="report-content">
                        <SafeMarkdown>
                          {JSON.stringify(report, null, 2)}
                        </SafeMarkdown>
                      </div>
                    )}

                    {/* Feedback and reinforcement (same style as summarization) - show whenever guidance report is displayed */}
                    {!report.error && (report.content != null || typeof report === 'string') && (
                      <div style={{
                        marginTop: '30px',
                        padding: '16px 20px',
                        border: '1px solid #dee2e6',
                        borderRadius: '8px',
                        backgroundColor: guidanceLiked ? '#e8f5e9' : '#f8f9fa',
                        borderColor: guidanceLiked ? '#4caf50' : '#dee2e6',
                      }}>
                        {guidanceLiked && !guidanceFeedbackOpen && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <FaCheck style={{ color: '#2e7d32' }} />
                            <span style={{ color: '#2e7d32', fontWeight: '500', fontSize: '0.95rem' }}>
                              Thanks for your feedback!
                            </span>
                            <button
                              type="button"
                              onClick={() => setGuidanceFeedbackOpen(true)}
                              style={{
                                marginLeft: 'auto',
                                padding: '4px 10px',
                                backgroundColor: 'transparent',
                                border: '1px solid #6c757d',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                fontSize: '0.8rem',
                                color: '#6c757d',
                              }}
                            >
                              Still want to improve?
                            </button>
                          </div>
                        )}

                        {!guidanceLiked && !guidanceFeedbackOpen && !guidanceReinforceLoading && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <span style={{ fontSize: '0.9rem', color: '#6c757d' }}>Was this helpful?</span>
                            <button
                              type="button"
                              onClick={() => {
                                setGuidanceLiked(true);
                                setGuidanceFeedbackRating('helpful');
                              }}
                              disabled={guidanceFeedbackLoading}
                              style={{
                                padding: '6px 14px',
                                backgroundColor: guidanceFeedbackLoading ? '#c8e6c9' : '#e8f5e9',
                                border: '1px solid #4caf50',
                                borderRadius: '4px',
                                cursor: guidanceFeedbackLoading ? 'not-allowed' : 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                color: '#2e7d32',
                                fontWeight: '500',
                                transition: 'all 0.2s ease',
                              }}
                            >
                              <FaThumbsUp size={14} /> Yes
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setGuidanceFeedbackOpen(true);
                                setGuidanceFeedbackRating('not_helpful');
                              }}
                              disabled={guidanceFeedbackLoading}
                              style={{
                                padding: '6px 14px',
                                backgroundColor: '#ffebee',
                                border: '1px solid #f44336',
                                borderRadius: '4px',
                                cursor: guidanceFeedbackLoading ? 'not-allowed' : 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                color: '#c62828',
                                fontWeight: '500',
                              }}
                            >
                              <FaThumbsDown size={14} /> Improve
                            </button>
                          </div>
                        )}

                        {guidanceReinforceLoading && (
                          <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            color: '#1976d2',
                            fontSize: '0.9rem',
                          }}
                          >
                            <FaSpinner className="loading-spinner" style={{ animation: 'spin 1s linear infinite' }} />
                            Improving guidance based on your feedback...
                          </div>
                        )}

                        {guidanceFeedbackOpen && !guidanceReinforceLoading && (
                          <div style={{ marginTop: guidanceLiked ? '12px' : '0' }}>
                            {!guidanceId && (
                              <p style={{ fontSize: '0.9rem', marginBottom: '12px', color: '#856404', backgroundColor: '#fff3cd', padding: '10px', borderRadius: '6px', border: '1px solid #ffeaa7' }}>
                                Improvement is not available for this run. Generate guidance again to enable feedback and improved guidance.
                              </p>
                            )}
                            <p style={{ fontSize: '0.95rem', fontWeight: '600', marginBottom: '12px', color: '#495057' }}>
                              How can we improve this guidance?
                            </p>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
                              {[
                                { id: 'add_more_links', label: 'Add more links' },
                                { id: 'new_deadline_event', label: 'Set new deadline / Create event' },
                                { id: 'doubt_on_questions', label: 'Ask doubt on questions' },
                                { id: 'simplify_language', label: 'Simplify language' },
                              ].map((type) => (
                                <button
                                  key={type.id}
                                  type="button"
                                  onClick={() => setGuidanceFeedbackType(guidanceFeedbackType === type.id ? null : type.id)}
                                  style={{
                                    padding: '6px 12px',
                                    backgroundColor: guidanceFeedbackType === type.id ? '#336db0' : '#fff',
                                    color: guidanceFeedbackType === type.id ? '#fff' : '#495057',
                                    border: `1px solid ${guidanceFeedbackType === type.id ? '#336db0' : '#dee2e6'}`,
                                    borderRadius: '16px',
                                    cursor: 'pointer',
                                    fontSize: '0.85rem',
                                    transition: 'all 0.2s ease',
                                  }}
                                >
                                  {type.label}
                                </button>
                              ))}
                            </div>
                            {guidanceFeedbackType === 'new_deadline_event' && (
                              <input
                                type="text"
                                value={guidanceDeadlineText}
                                onChange={(e) => setGuidanceDeadlineText(e.target.value)}
                                placeholder="New deadline (e.g. 15th March 2025 11:59 PM)"
                                disabled={guidanceFeedbackLoading}
                                style={{
                                  width: '100%',
                                  padding: '10px',
                                  border: '1px solid #dee2e6',
                                  borderRadius: '6px',
                                  fontSize: '0.9rem',
                                  marginBottom: '10px',
                                }}
                              />
                            )}
                            <input
                              type="text"
                              value={guidanceConfusedConcept}
                              onChange={(e) => setGuidanceConfusedConcept(e.target.value)}
                              placeholder="Confused about? Or specify your doubt / question (e.g. normalization steps, ER design...)"
                              disabled={guidanceFeedbackLoading}
                              style={{
                                width: '100%',
                                padding: '10px',
                                border: '1px solid #dee2e6',
                                borderRadius: '6px',
                                fontSize: '0.9rem',
                                marginBottom: '10px',
                              }}
                            />
                            <textarea
                              value={guidanceFeedbackComment}
                              onChange={(e) => setGuidanceFeedbackComment(e.target.value)}
                              placeholder="Add specific feedback (optional)..."
                              disabled={guidanceFeedbackLoading}
                              rows={2}
                              style={{
                                width: '100%',
                                padding: '10px',
                                border: '1px solid #dee2e6',
                                borderRadius: '6px',
                                fontSize: '0.9rem',
                                fontFamily: 'inherit',
                                resize: 'vertical',
                                marginBottom: '12px',
                              }}
                            />
                            <div style={{ display: 'flex', gap: '8px' }}>
                              <button
                                type="button"
                                onClick={handleSubmitGuidanceFeedbackAndReinforce}
                                disabled={!guidanceId || guidanceFeedbackLoading || !(guidanceFeedbackType || guidanceConfusedConcept.trim() || guidanceFeedbackComment.trim() || (guidanceFeedbackType === 'new_deadline_event' && guidanceDeadlineText.trim()))}
                                className="btn btn-primary"
                                style={{
                                  padding: '8px 16px',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '6px',
                                  opacity: !guidanceId || guidanceFeedbackLoading || !(guidanceFeedbackType || guidanceConfusedConcept.trim() || guidanceFeedbackComment.trim() || (guidanceFeedbackType === 'new_deadline_event' && guidanceDeadlineText.trim())) ? 0.6 : 1,
                                  cursor: !guidanceId || guidanceFeedbackLoading || !(guidanceFeedbackType || guidanceConfusedConcept.trim() || guidanceFeedbackComment.trim() || (guidanceFeedbackType === 'new_deadline_event' && guidanceDeadlineText.trim())) ? 'not-allowed' : 'pointer',
                                }}
                              >
                                {guidanceFeedbackLoading ? (
                                  <>
                                    <FaSpinner className="loading-spinner" style={{ animation: 'spin 1s linear infinite' }} />
                                    Submitting...
                                  </>
                                ) : (
                                  <>
                                    <FaEdit size={14} />
                                    Submit & Improve
                                  </>
                                )}
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setGuidanceFeedbackOpen(false);
                                  setGuidanceFeedbackType(null);
                                  setGuidanceDeadlineText('');
                                  if (!guidanceLiked) setGuidanceFeedbackRating(null);
                                }}
                                style={{
                                  padding: '8px 16px',
                                  backgroundColor: '#fff',
                                  color: '#495057',
                                  border: '1px solid #dee2e6',
                                  borderRadius: '4px',
                                  cursor: 'pointer',
                                }}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}

                        {guidanceReinforceSuccess && !guidanceFeedbackOpen && (
                          <div style={{ marginTop: '12px' }}>
                            <div style={{
                              padding: '10px',
                              backgroundColor: '#d4edda',
                              border: '1px solid #c3e6cb',
                              borderRadius: '6px',
                              color: '#155724',
                              fontSize: '0.9rem',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px',
                            }}>
                              <FaCheck /> Guidance improved successfully!
                            </div>
                            {guidanceCalendarEventMessage && (
                              <div style={{
                                marginTop: '8px',
                                padding: '10px',
                                backgroundColor: '#e7f3ff',
                                border: '1px solid #b3d9ff',
                                borderRadius: '6px',
                                color: '#004085',
                                fontSize: '0.9rem',
                              }}>
                                {guidanceCalendarEventMessage}
                              </div>
                            )}
                          </div>
                        )}
                        {guidanceFeedbackError && (
                          <div className="error-message" style={{ marginTop: '12px' }}>{guidanceFeedbackError}</div>
                        )}
                        {guidanceReinforceError && (
                          <div className="error-message" style={{ marginTop: '12px' }}>{guidanceReinforceError}</div>
                        )}
                      </div>
                    )}

                  </div>
                )}
              </div>
            )}

            {modalOpen === 'summarize' && (
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
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', flex: '1 1 auto' }}>
                            <h2 style={{ margin: 0, color: '#495057' }}>
                              <FaBookOpen style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Summary:{' '}
                              <span style={{ color: '#336db0' }}>{summary.topic}</span>
                            </h2>
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
                        </div>
                      </div>
                    )}

                    {summary.error ? (
                      <div className="error-message">{summary.error}</div>
                    ) : summary.content ? (
                      <div>
                        <div className="report-content">
                          {(() => {
                            const content = ensureLinksInMarkdown(unwrapMarkdownFromCodeBlock(summary.content));
                            // Debug: Check if HTML figure tags are present
                            if (content.includes('<figure>')) {
                              console.log('✅ HTML figure tags detected in summary content');
                              const figureCount = (content.match(/<figure>/g) || []).length;
                              const figcaptionCount = (content.match(/<figcaption>/g) || []).length;
                              const imgCount = (content.match(/<img/g) || []).length;
                              console.log(`📊 Found ${figureCount} <figure> tags, ${figcaptionCount} <figcaption> tags, and ${imgCount} <img> tags`);
                              
                              // Extract and log sample captions
                              const figcaptionMatches = content.match(/<figcaption>.*?<\/figcaption>/gs);
                              if (figcaptionMatches) {
                                console.log(`✅ Found ${figcaptionMatches.length} image descriptions:`);
                                figcaptionMatches.slice(0, 3).forEach((caption, idx) => {
                                  const textOnly = caption.replace(/<[^>]+>/g, '').substring(0, 100);
                                  console.log(`   Image ${idx + 1} description: ${textOnly}...`);
                                });
                              }
                              
                              // Check image sources
                              const imgSrcMatches = content.match(/<img[^>]+src=["']([^"']+)["']/g);
                              if (imgSrcMatches) {
                                console.log(`✅ Found ${imgSrcMatches.length} image sources:`);
                                imgSrcMatches.slice(0, 3).forEach((src, idx) => {
                                  const srcMatch = src.match(/src=["']([^"']+)["']/);
                                  if (srcMatch) {
                                    console.log(`   Image ${idx + 1} src: ${srcMatch[1]}`);
                                  }
                                });
                              }
                            } else {
                              console.warn('⚠ No HTML figure tags found in summary content');
                              console.log('Content preview (first 500 chars):', content.substring(0, 500));
                              // Check if there are [IMAGE:...] references that weren't converted
                              const imageRefs = content.match(/\[IMAGE:[^\]]+\]/g);
                              if (imageRefs) {
                                console.warn(`⚠ Found ${imageRefs.length} [IMAGE:...] references that weren't converted to HTML!`);
                                console.log('Image references:', imageRefs.slice(0, 3));
                              }
                            }
                            return (
                              <SafeMarkdown>
                                {content}
                              </SafeMarkdown>
                            );
                          })()}
                        </div>

                        <div style={{ marginTop: '14px' }}>
                          <strong>Listen to the Audio of the summarization: </strong>
                          {summaryAudio ? (
                            <div style={{ marginTop: '8px' }}>
                              <audio
                                key={summaryAudio}
                                controls
                                src={summaryAudio}
                                preload="auto"
                                style={{ width: '100%' }}
                              >
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
                        <div style={{ 
                          marginTop: '30px', 
                          padding: '16px 20px', 
                          border: '1px solid #dee2e6', 
                          borderRadius: '8px', 
                          backgroundColor: summaryLiked ? '#e8f5e9' : '#f8f9fa',
                          borderColor: summaryLiked ? '#4caf50' : '#dee2e6'
                        }}>
                          {/* Show confirmed state if user clicked "Yes" */}
                          {summaryLiked && !summaryFeedbackOpen && (
                            <div style={{ 
                              display: 'flex', 
                              alignItems: 'center', 
                              gap: '8px'
                            }}>
                              <FaCheck style={{ color: '#2e7d32' }} />
                              <span style={{ color: '#2e7d32', fontWeight: '500', fontSize: '0.95rem' }}>
                                Thanks for your feedback!
                              </span>
                              <button
                                onClick={() => setSummaryFeedbackOpen(true)}
                                style={{
                                  marginLeft: 'auto',
                                  padding: '4px 10px',
                                  backgroundColor: 'transparent',
                                  border: '1px solid #6c757d',
                                  borderRadius: '4px',
                                  cursor: 'pointer',
                                  fontSize: '0.8rem',
                                  color: '#6c757d'
                                }}
                              >
                                Still want to improve?
                              </button>
                            </div>
                          )}

                          {/* Quick feedback buttons - only show if not yet liked and form not open */}
                          {!summaryLiked && !summaryFeedbackOpen && !reinforceLoading && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                              <span style={{ fontSize: '0.9rem', color: '#6c757d' }}>Was this helpful?</span>
                              <button
                                onClick={() => {
                                  setSummaryLiked(true);
                                  setFeedbackRating('helpful');
                                }}
                                disabled={feedbackLoading}
                                style={{
                                  padding: '6px 14px',
                                  backgroundColor: feedbackLoading ? '#c8e6c9' : '#e8f5e9',
                                  border: '1px solid #4caf50',
                                  borderRadius: '4px',
                                  cursor: feedbackLoading ? 'not-allowed' : 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '6px',
                                  color: '#2e7d32',
                                  fontWeight: '500',
                                  transition: 'all 0.2s ease'
                                }}
                              >
                                <FaThumbsUp size={14} /> Yes
                              </button>
                              <button
                                onClick={() => {
                                  setSummaryFeedbackOpen(true);
                                  setFeedbackRating('not_helpful');
                                }}
                                disabled={feedbackLoading}
                                style={{
                                  padding: '6px 14px',
                                  backgroundColor: '#ffebee',
                                  border: '1px solid #f44336',
                                  borderRadius: '4px',
                                  cursor: feedbackLoading ? 'not-allowed' : 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '6px',
                                  color: '#c62828',
                                  fontWeight: '500'
                                }}
                              >
                                <FaThumbsDown size={14} /> Improve
                              </button>
                            </div>
                          )}

                          {/* Improving indicator */}
                          {reinforceLoading && (
                            <div style={{ 
                              display: 'flex', 
                              alignItems: 'center', 
                              gap: '8px',
                              color: '#1976d2',
                              fontSize: '0.9rem'
                            }}>
                              <FaSpinner className="loading-spinner" style={{ animation: 'spin 1s linear infinite' }} />
                              Improving summary based on your feedback...
                            </div>
                          )}

                          {/* Expanded feedback form */}
                          {summaryFeedbackOpen && !reinforceLoading && (
                            <div style={{ marginTop: summaryLiked ? '12px' : '0' }}>
                              <p style={{ fontSize: '0.95rem', fontWeight: '600', marginBottom: '12px', color: '#495057' }}>
                                How can we improve this summary?
                              </p>
                              
                              {/* Feedback type buttons */}
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
                                {[
                                  { id: 'add_examples', label: 'Add Examples' },
                                  { id: 'simplify', label: 'Simplify Language' },
                                  { id: 'more_detail', label: 'More Detail' },
                                  { id: 'clarify', label: 'Clarify Concepts' }
                                ].map(type => (
                                  <button
                                    key={type.id}
                                    onClick={() => setSummaryFeedbackType(summaryFeedbackType === type.id ? null : type.id)}
                                    style={{
                                      padding: '6px 12px',
                                      backgroundColor: summaryFeedbackType === type.id ? '#336db0' : '#fff',
                                      color: summaryFeedbackType === type.id ? '#fff' : '#495057',
                                      border: `1px solid ${summaryFeedbackType === type.id ? '#336db0' : '#dee2e6'}`,
                                      borderRadius: '16px',
                                      cursor: 'pointer',
                                      fontSize: '0.85rem',
                                      transition: 'all 0.2s ease'
                                    }}
                                  >
                                    {type.label}
                                  </button>
                                ))}
                              </div>

                              {/* Confused concept input */}
                              <input
                                type="text"
                                value={confusedConcept}
                                onChange={(e) => setConfusedConcept(e.target.value)}
                                placeholder="Confused about? (e.g., normalization steps...)"
                                disabled={feedbackLoading}
                                style={{
                                  width: '100%',
                                  padding: '10px',
                                  border: '1px solid #dee2e6',
                                  borderRadius: '6px',
                                  fontSize: '0.9rem',
                                  marginBottom: '10px'
                                }}
                              />

                              {/* Comment textarea */}
                              <textarea
                                value={feedbackComment}
                                onChange={(e) => setFeedbackComment(e.target.value)}
                                placeholder="Add specific feedback (optional)..."
                                disabled={feedbackLoading}
                                rows={2}
                                style={{
                                  width: '100%',
                                  padding: '10px',
                                  border: '1px solid #dee2e6',
                                  borderRadius: '6px',
                                  fontSize: '0.9rem',
                                  fontFamily: 'inherit',
                                  resize: 'vertical',
                                  marginBottom: '12px'
                                }}
                              />

                              {/* Action buttons */}
                              <div style={{ display: 'flex', gap: '8px' }}>
                                <button
                                  onClick={handleSubmitFeedbackAndReinforce}
                                  disabled={feedbackLoading || (!summaryFeedbackType && !confusedConcept && !feedbackComment)}
                                  className="btn btn-primary"
                                  style={{
                                    padding: '8px 16px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '6px',
                                    opacity: feedbackLoading || (!summaryFeedbackType && !confusedConcept && !feedbackComment) ? 0.6 : 1,
                                    cursor: feedbackLoading || (!summaryFeedbackType && !confusedConcept && !feedbackComment) ? 'not-allowed' : 'pointer'
                                  }}
                                >
                                  {feedbackLoading ? (
                                    <>
                                      <FaSpinner className="loading-spinner" style={{ animation: 'spin 1s linear infinite' }} />
                                      Submitting...
                                    </>
                                  ) : (
                                    <>
                                      <FaEdit size={14} />
                                      Submit & Improve
                                    </>
                                  )}
                                </button>
                                <button
                                  onClick={() => {
                                    setSummaryFeedbackOpen(false);
                                    setSummaryFeedbackType(null);
                                    if (!summaryLiked) {
                                      setFeedbackRating(null);
                                    }
                                  }}
                                  style={{
                                    padding: '8px 16px',
                                    backgroundColor: '#fff',
                                    color: '#495057',
                                    border: '1px solid #dee2e6',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          )}

                          {/* Success/Error messages */}
                          {reinforceSuccess && !summaryFeedbackOpen && (
                            <div style={{ 
                              marginTop: '12px', 
                              padding: '10px', 
                              backgroundColor: '#d4edda', 
                              border: '1px solid #c3e6cb',
                              borderRadius: '6px',
                              color: '#155724',
                              fontSize: '0.9rem',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px'
                            }}>
                              <FaCheck /> Summary improved successfully!
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
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}

                
              </div>
            )}

            {modalOpen === 'flashcards' && (
              <div className="content-area">
                <form onSubmit={handleGenerateFlashcards} className="form-container">
                  <div className="form-group">
                    <label className="form-label" htmlFor="flashcard-topic">
                      <PiCardsFill style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Enter Topic for Flashcards
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
                    <div style={{ marginTop: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input
                          type="checkbox"
                          id="force-regenerate-flashcards"
                          checked={forceRegenerateFlashcards}
                          onChange={(e) => setForceRegenerateFlashcards(e.target.checked)}
                          disabled={flashLoading}
                        />
                        <label htmlFor="force-regenerate-flashcards" style={{ fontSize: '0.9rem', color: '#495057', cursor: 'pointer' }}>
                          Force regenerate (generate new and save for future access)
                        </label>
                      </div>
                    </div>
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={flashLoading}>
                    {flashLoading ? (
                      <>
                        <span className="loading-spinner"></span>
                        Generating...
                      </>
                    ) : (
                      <>
                        <PiCardsFill style={{ marginRight: '8px' }} />
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
                            <PiCardsFill style={{ marginRight: '8px', verticalAlign: 'middle' }} /> Flashcards: <span style={{ color: '#336db0' }}>{flashcards.topic}</span>
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
                                      key={card.id || i} 
                                      style={{ 
                                        marginBottom: '20px',
                                        padding: '16px',
                                        backgroundColor: card.improved ? '#e8f5e9' : '#fff',
                                        borderRadius: '8px',
                                        border: card.improved ? '2px solid #4caf50' : '1px solid #dee2e6',
                                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                                        position: 'relative'
                                      }}
                                    >
                                      {/* Improved badge */}
                                      {card.improved && (
                                        <div style={{
                                          position: 'absolute',
                                          top: '-8px',
                                          right: '16px',
                                          backgroundColor: '#4caf50',
                                          color: 'white',
                                          padding: '2px 8px',
                                          borderRadius: '4px',
                                          fontSize: '0.75rem',
                                          fontWeight: 'bold'
                                        }}>
                                          Improved
                                        </div>
                                      )}
                                      
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
                                        lineHeight: '1.6',
                                        marginBottom: '16px'
                                      }}>
                                        <strong style={{ color: '#28a745' }}>Answer:</strong> {card.answer}
                                      </div>
                                      
                                      {/* Improvement notes if available */}
                                      {card.improvement_notes && (
                                        <div style={{
                                          backgroundColor: '#e3f2fd',
                                          padding: '8px 12px',
                                          borderRadius: '4px',
                                          fontSize: '0.85rem',
                                          color: '#1565c0',
                                          marginBottom: '12px'
                                        }}>
                                          <strong>Improvement:</strong> {card.improvement_notes}
                                        </div>
                                      )}
                                      
                                      {/* Feedback section */}
                                      <div style={{ 
                                        borderTop: '1px solid #dee2e6',
                                        paddingTop: '12px',
                                        marginTop: '8px'
                                      }}>
                                        {/* Show confirmed state if user clicked "Yes" */}
                                        {flashcardLiked[card.id] && !flashcardFeedbackOpen[card.id] && !flashcardImproving[card.id] && (
                                          <div style={{ 
                                            display: 'flex', 
                                            alignItems: 'center', 
                                            gap: '8px',
                                            padding: '8px 12px',
                                            backgroundColor: '#e8f5e9',
                                            borderRadius: '6px',
                                            border: '1px solid #4caf50'
                                          }}>
                                            <FaCheck style={{ color: '#2e7d32' }} />
                                            <span style={{ color: '#2e7d32', fontWeight: '500', fontSize: '0.9rem' }}>
                                              Thanks for your feedback!
                                            </span>
                                            <button
                                              onClick={() => setFlashcardFeedbackOpen(prev => ({ ...prev, [card.id]: true }))}
                                              style={{
                                                marginLeft: 'auto',
                                                padding: '4px 8px',
                                                backgroundColor: 'transparent',
                                                border: '1px solid #6c757d',
                                                borderRadius: '4px',
                                                cursor: 'pointer',
                                                fontSize: '0.75rem',
                                                color: '#6c757d'
                                              }}
                                            >
                                              Still want to improve?
                                            </button>
                                          </div>
                                        )}
                                        
                                        {/* Quick feedback buttons - only show if not yet liked */}
                                        {!flashcardLiked[card.id] && !flashcardFeedbackOpen[card.id] && !flashcardImproving[card.id] && (
                                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                            <span style={{ fontSize: '0.85rem', color: '#6c757d' }}>Was this helpful?</span>
                                            <button
                                              onClick={() => flashcardSetId ? handleFlashcardFeedback(card.id, selectedBloomLevel, 'thumbs_up') : alert('Feedback requires saving flashcards. Please try regenerating.')}
                                              disabled={flashcardFeedbackLoading[card.id]}
                                              style={{
                                                padding: '6px 12px',
                                                backgroundColor: flashcardFeedbackLoading[card.id] ? '#c8e6c9' : '#e8f5e9',
                                                border: '1px solid #4caf50',
                                                borderRadius: '4px',
                                                cursor: flashcardSetId && !flashcardFeedbackLoading[card.id] ? 'pointer' : 'not-allowed',
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '4px',
                                                color: '#2e7d32',
                                                opacity: flashcardSetId ? 1 : 0.6,
                                                transition: 'all 0.2s ease'
                                              }}
                                            >
                                              {flashcardFeedbackLoading[card.id] ? (
                                                <>
                                                  <FaSpinner size={14} style={{ animation: 'spin 1s linear infinite' }} />
                                                  Saving...
                                                </>
                                              ) : (
                                                <>
                                                  <FaThumbsUp size={14} /> Yes
                                                </>
                                              )}
                                            </button>
                                            <button
                                              onClick={() => flashcardSetId ? setFlashcardFeedbackOpen(prev => ({ ...prev, [card.id]: true })) : alert('Feedback requires saving flashcards. Please try regenerating.')}
                                              disabled={flashcardFeedbackLoading[card.id]}
                                              style={{
                                                padding: '6px 12px',
                                                backgroundColor: '#ffebee',
                                                border: '1px solid #f44336',
                                                borderRadius: '4px',
                                                cursor: flashcardSetId && !flashcardFeedbackLoading[card.id] ? 'pointer' : 'not-allowed',
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '4px',
                                                color: '#c62828',
                                                opacity: flashcardSetId ? 1 : 0.6
                                              }}
                                            >
                                              <FaThumbsDown size={14} /> Improve
                                            </button>
                                            {!flashcardSetId && (
                                              <span style={{ fontSize: '0.75rem', color: '#dc3545', marginLeft: '8px' }}>
                                                (Save required for feedback)
                                              </span>
                                            )}
                                          </div>
                                        )}
                                          
                                          {/* Improving indicator */}
                                          {flashcardImproving[card.id] && (
                                            <div style={{ 
                                              display: 'flex', 
                                              alignItems: 'center', 
                                              gap: '8px',
                                              color: '#1976d2',
                                              fontSize: '0.9rem'
                                            }}>
                                              <FaSpinner className="loading-spinner" style={{ animation: 'spin 1s linear infinite' }} />
                                              Improving flashcard based on your feedback...
                                            </div>
                                          )}
                                          
                                          {/* Expanded feedback form */}
                                          {flashcardFeedbackOpen[card.id] && !flashcardImproving[card.id] && (
                                            <div style={{ 
                                              backgroundColor: '#f8f9fa',
                                              padding: '12px',
                                              borderRadius: '8px',
                                              marginTop: '8px'
                                            }}>
                                              <p style={{ fontSize: '0.9rem', fontWeight: '600', marginBottom: '8px' }}>
                                                How can we improve this flashcard?
                                              </p>
                                              
                                              {/* Feedback type buttons */}
                                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
                                                {[
                                                  { id: 'add_examples', label: 'Add Examples' },
                                                  { id: 'simplify', label: 'Simplify Language' },
                                                  { id: 'more_detail', label: 'More Detail' },
                                                  { id: 'clarify', label: 'Clarify' }
                                                ].map(type => (
                                                  <button
                                                    key={type.id}
                                                    onClick={() => setFlashcardFeedbackType(prev => ({
                                                      ...prev,
                                                      [card.id]: flashcardFeedbackType[card.id] === type.id ? null : type.id
                                                    }))}
                                                    style={{
                                                      padding: '6px 12px',
                                                      backgroundColor: flashcardFeedbackType[card.id] === type.id ? '#336db0' : '#fff',
                                                      color: flashcardFeedbackType[card.id] === type.id ? '#fff' : '#495057',
                                                      border: `1px solid ${flashcardFeedbackType[card.id] === type.id ? '#336db0' : '#dee2e6'}`,
                                                      borderRadius: '16px',
                                                      cursor: 'pointer',
                                                      fontSize: '0.85rem'
                                                    }}
                                                  >
                                                    {type.label}
                                                  </button>
                                                ))}
                                              </div>
                                              
                                              {/* Comment input */}
                                              <textarea
                                                placeholder="Add specific feedback (optional)..."
                                                value={flashcardFeedbackComment[card.id] || ''}
                                                onChange={(e) => setFlashcardFeedbackComment(prev => ({
                                                  ...prev,
                                                  [card.id]: e.target.value
                                                }))}
                                                style={{
                                                  width: '100%',
                                                  padding: '8px',
                                                  borderRadius: '4px',
                                                  border: '1px solid #dee2e6',
                                                  minHeight: '60px',
                                                  fontSize: '0.9rem',
                                                  marginBottom: '12px',
                                                  resize: 'vertical'
                                                }}
                                              />
                                              
                                              {/* Action buttons */}
                                              <div style={{ display: 'flex', gap: '8px' }}>
                                                <button
                                                  onClick={() => handleFlashcardFeedback(card.id, selectedBloomLevel, 'thumbs_down')}
                                                  disabled={flashcardFeedbackLoading[card.id] || (!flashcardFeedbackType[card.id] && !flashcardFeedbackComment[card.id])}
                                                  style={{
                                                    padding: '8px 16px',
                                                    backgroundColor: '#336db0',
                                                    color: '#fff',
                                                    border: 'none',
                                                    borderRadius: '4px',
                                                    cursor: flashcardFeedbackLoading[card.id] || (!flashcardFeedbackType[card.id] && !flashcardFeedbackComment[card.id]) ? 'not-allowed' : 'pointer',
                                                    opacity: flashcardFeedbackLoading[card.id] || (!flashcardFeedbackType[card.id] && !flashcardFeedbackComment[card.id]) ? 0.6 : 1,
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '6px'
                                                  }}
                                                >
                                                  {flashcardFeedbackLoading[card.id] ? (
                                                    <>
                                                      <FaSpinner className="loading-spinner" style={{ animation: 'spin 1s linear infinite' }} />
                                                      Submitting...
                                                    </>
                                                  ) : (
                                                    <>
                                                      <FaEdit size={14} />
                                                      Submit & Improve
                                                    </>
                                                  )}
                                                </button>
                                                <button
                                                  onClick={() => {
                                                    setFlashcardFeedbackOpen(prev => ({ ...prev, [card.id]: false }));
                                                    setFlashcardFeedbackType(prev => ({ ...prev, [card.id]: null }));
                                                    setFlashcardFeedbackComment(prev => ({ ...prev, [card.id]: '' }));
                                                  }}
                                                  style={{
                                                    padding: '8px 16px',
                                                    backgroundColor: '#fff',
                                                    color: '#495057',
                                                    border: '1px solid #dee2e6',
                                                    borderRadius: '4px',
                                                    cursor: 'pointer'
                                                  }}
                                                >
                                                  Cancel
                                                </button>
                                              </div>
                                            </div>
                                          )}
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

            {modalOpen === 'er' && (
              <div className="content-area">
                <ERDiagramGeneratorPage />
              </div>
            )}
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </>
  );
}

export default GuidancePage;
