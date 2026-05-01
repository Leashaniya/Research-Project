from pyvis.network import Network
from nlp_utils import shorten
import openai
import os
import re
import json
import base64
import html as html_module
from datetime import datetime, timezone
import numpy as np

from analysis_utils import classify_quiz_accuracy_band
from topic_labels import clean_topic_display_name

from graphrag import graph_builder as gb
from graphrag.graph_retriever import (
    lecture_accuracy_map,
    load_quiz_state,
    retrieve_recommended_mcqs,
    save_recommendations,
)
from graphrag.graph_view_transform import (
    best_topic_id_for_mcq_column,
    build_learning_map_bundle,
    mcq_column_index_for_row,
    topic_learning_label,
)

# OPENAI CONFIG (keep for graph enrichment only) - use env
openai.api_key = openai.api_key or os.getenv("OPENAI_API_KEY", "").strip()

STUDENT_CONTEXT_PATH = os.path.join("outputs", "student_learning_context.json")


def llm_enrich_question(question, topics):
    """
    Uses LLM to:
    1. Explain the MCQ briefly
    2. Identify the most relevant topic keywords
    """
    if not topics:
        return "Explanation unavailable\nTopic: unknown"

    topic_text = ", ".join(
        [" / ".join(t["keywords"][:3]) for t in topics if t.get("keywords")]
    )

    prompt = f"""
Question:
{question}

Topics:
{topic_text}

1. Give a 1-line explanation of the question.
2. Say which topic fits best.

Format:
Explanation: ...
Topic: ...
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful educational assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        return response["choices"][0]["message"]["content"]

    except Exception as e:
        print(" LLM error:", e)
        return "Explanation unavailable\nTopic: unknown"


def _lecture_file_basename(lecture: dict) -> str:
    return os.path.basename(lecture.get("file", ""))


def _topic_color_for_center(kind: str) -> str:
    if kind == "weak":
        return gb.COLOR_TOPIC_WEAK
    if kind == "related":
        return gb.COLOR_TOPIC_PRIORITY
    if kind == "priority":
        return gb.COLOR_TOPIC_PRIORITY
    return gb.COLOR_TOPIC_NEUTRAL


def _exam_frequency_label(is_priority: bool) -> str:
    return "High" if is_priority else "Moderate"


def _confidence_label(score: float | None) -> str:
    if score is None:
        return "Medium"
    if score >= 0.72:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


def _inject_student_summary_panel(
    html_path: str,
    weak_topics_with_scores: list[dict],
    prerequisite_topics: list[str],
    top3_question_texts: list[str],
) -> None:
    try:
        with open(html_path, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
    except OSError:
        return

    if "mcq-student-summary-panel" in html:
        return

    def _li(items: list[str], empty_msg: str) -> str:
        if not items:
            return f"<li><em>{html_module.escape(empty_msg)}</em></li>"
        return "".join(f"<li>{html_module.escape(str(x))}</li>" for x in items)

    weak_lines = []
    for row in weak_topics_with_scores[:10]:
        topic = str(row.get("topic") or "").strip()
        score = row.get("score")
        if not topic:
            continue
        if score is None:
            weak_lines.append(topic)
        else:
            weak_lines.append(f"{topic} ({float(score):.0f}%)")

    summary_html = (
        '<div id="mcq-student-summary-panel" style="font-family:Arial; max-width:800px; margin:20px auto; '
        'padding:20px; border:1px solid #ddd; border-radius:10px;">'
        '<h3 style="color:#FF4444;">⚠️ Your Weak Topics</h3>'
        f"<ul>{_li(weak_lines, 'No weak topics detected')}</ul>"
        '<h3 style="color:#FF9900;">📚 Study These Prerequisites First</h3>'
        f"<ul>{_li(prerequisite_topics[:10], 'No prerequisite topics detected')}</ul>"
        '<h3 style="color:#4488FF;">❓ Recommended Practice Questions</h3>'
        f"<ul>{_li(top3_question_texts[:3], 'No recommended practice questions found')}</ul>"
        '<h3 style="color:#44BB44;">🎯 Your Study Priority Order</h3>'
        "<ol>"
        "<li>Review prerequisite topics (orange nodes)</li>"
        "<li>Focus on weak topics (red nodes)</li>"
        "<li>Practice recommended MCQs (blue nodes)</li>"
        "<li>Maintain strong topics (green nodes)</li>"
        "</ol>"
        "</div>"
    )

    updated = html.replace("</body>", summary_html + "\n</body>", 1)
    if updated != html:
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(updated)
        except OSError:
            return


def _mcq_options_display(row) -> str:
    opts = row.get("options")
    if opts is None or (isinstance(opts, float) and np.isnan(opts)):
        return ""
    if isinstance(opts, str):
        parts = [p.strip() for p in opts.split("|") if p.strip()]
        return "\n".join(_clean_display_text(p) for p in parts) if parts else _clean_display_text(str(opts))
    return _clean_display_text(str(opts))


def _mcq_explanation_text(row) -> str:
    for key in ("explanation", "rationale", "notes"):
        v = row.get(key)
        if v is not None and str(v).strip():
            return _clean_display_text(str(v))
    ans = row.get("answer")
    if ans is not None and str(ans).strip():
        return _clean_display_text(f"Correct answer: {ans}")
    return ""


def _clean_display_text(text: str) -> str:
    """Normalize mojibake/noise from PDF extraction for student-facing graph panel."""
    t = str(text or "")
    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": '"',
        "â€\x9d": '"',
        "â€“": "-",
        "â€”": "-",
        "â€¢": "-",
        "Â": " ",
        "Ã—": "x",
        "→": "->",
        "\ufffd": " ",
    }
    for bad, good in replacements.items():
        t = t.replace(bad, good)
    t = re.sub(r"[\uE000-\uF8FF]", " ", t)
    t = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _related_topic_label_for_mcq(
    link_tid: str,
    centers: list,
    topics_order: list,
) -> str:
    if not link_tid:
        return ""
    for c in centers:
        if c["tid"] == link_tid:
            return topic_learning_label(c["kind"], c["topic"])
    for item in topics_order:
        if gb.topic_node_id(item["topic"], item["lecture_id"]) == link_tid:
            return _topic_kw_line(item["topic"])
    return ""


def _topic_kw_line(topic: dict) -> str:
    return ", ".join(topic.get("keywords", [])[:6]) or "Main ideas"


def _build_learning_map_intro_html(meta: dict, bundle: dict, practice_recs: list) -> str:
    weak = list(meta.get("weak_topics_confirmed") or [])
    if not weak:
        weak = [
            c.get("student_label")
            for c in bundle.get("centers") or []
            if c.get("kind") == "weak" and c.get("student_label")
        ]
    related = []
    for p in meta.get("related_concept_links") or []:
        rc = (p.get("related_concept") or "").strip()
        if rc and rc not in related:
            related.append(rc)
    if not related:
        related = [
            c.get("student_label")
            for c in bundle.get("centers") or []
            if c.get("kind") == "related" and c.get("student_label")
        ]
    n_practice = len(practice_recs)
    def li(items):
        if not items:
            return "<li><em>—</em></li>"
        return "".join(f"<li>{html_module.escape(str(x))}</li>" for x in items[:8])
    return (
        '<div id="mcq-graphrag-intro" style="margin:12px 16px 16px;padding:14px 18px;'
        "background:#f0f7ff;border:1px solid #90caf9;border-radius:10px;"
        'font-family:system-ui,Segoe UI,sans-serif;font-size:14px;color:#1a237e;line-height:1.45;">'
        "<strong>How this map helps you (GraphRAG)</strong>"
        "<ul style=\"margin:8px 0 10px 18px;padding:0;\">"
        "<li>See <strong style='color:#c62828'>where you are weak</strong> (red topics from your quiz)</li>"
        "<li>See <strong style='color:#ef6c00'>related ideas</strong> to revise next (orange)</li>"
        "<li>Practice <strong style='color:#1565c0'>blue questions</strong> picked from your real question bank</li>"
        "</ul>"
        "<p style='margin:0 0 6px 0;'><strong>Weak topics</strong></p><ul style='margin:0 0 10px 18px;'>"
        f"{li(weak)}</ul>"
        "<p style='margin:0 0 6px 0;'><strong>Related concepts</strong></p><ul style='margin:0 0 10px 18px;'>"
        f"{li(related)}</ul>"
        f"<p style='margin:0;'><strong>Practice next:</strong> {n_practice} suggested MCQs on this map "
        "(click a <span style='color:#1565c0'>blue</span> node).</p>"
        "</div>"
    )


def _build_student_learning_context(
    quiz_state: dict | None,
    recommendations: list,
    practice_recs: list,
    meta: dict,
) -> dict:
    topic_wise_accuracy = quiz_state.get("topic_wise_accuracy") if isinstance(quiz_state, dict) else {}
    topic_accuracy_summary = []
    if isinstance(topic_wise_accuracy, dict):
        for topic_name, row in topic_wise_accuracy.items():
            topic_accuracy_summary.append(
                {
                    "topic_name": topic_name,
                    "accuracy": float(row.get("accuracy", 0.0)),
                    "total": int(row.get("total", 0)),
                    "band": row.get("band", "moderate"),
                }
            )
    topic_accuracy_summary.sort(key=lambda x: (x["accuracy"], -x["total"], x["topic_name"]))

    rec_source = practice_recs if practice_recs else recommendations[:10]
    recommended_mcqs = []
    for r in rec_source[:10]:
        qid = str(r.get("question_id", ""))
        if not qid:
            continue
        recommended_mcqs.append(
            {
                "question_id": qid,
                "score": float(r.get("score", 0.0)),
                "reason_trace": r.get("reason_trace") or {},
            }
        )

    related_topics = []
    seen_related = set()
    for item in (meta.get("related_concept_links") or []):
        weak = (item.get("from_weak") or "").strip()
        rel = (item.get("related_concept") or "").strip()
        if not weak and not rel:
            continue
        key = (weak.lower(), rel.lower())
        if key in seen_related:
            continue
        seen_related.add(key)
        related_topics.append(
            {
                "weak_topic": weak,
                "related_topic": rel,
                "link_type": item.get("link_type", ""),
            }
        )
    for item in (meta.get("prerequisite_concept_links") or []):
        weak = (item.get("from_weak") or "").strip()
        prereq = (item.get("prerequisite_concept") or item.get("related_concept") or "").strip()
        if not weak and not prereq:
            continue
        key = (weak.lower(), prereq.lower())
        if key in seen_related:
            continue
        seen_related.add(key)
        related_topics.append(
            {
                "weak_topic": weak,
                "related_topic": prereq,
                "link_type": item.get("link_type", "Prerequisite concept"),
            }
        )

    return {
        "weak_topics_confirmed": list(meta.get("weak_topics_confirmed") or []),
        "topic_accuracy": topic_accuracy_summary[:12],
        "priority_lectures": list(meta.get("priority_files") or []),
        "related_topics": related_topics[:5],
        "recommended_mcqs": recommended_mcqs,
        "study_plan_settings": {
            "total_hours": None,
            "study_days": None,
            "alpha": None,
            "max_increase": None,
            "max_decrease": None,
        },
        "quiz_accuracy_overall": float((quiz_state or {}).get("overall_accuracy_pct", 0.0)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _save_student_learning_context(context: dict, output_path: str = STUDENT_CONTEXT_PATH) -> None:
    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(context, f, indent=2)
    except OSError:
        pass


def _inject_mcq_click_panel(html_path: str, mcq_click_data: dict, intro_html: str = "") -> None:
    with open(html_path, encoding="utf-8", errors="replace") as f:
        html = f.read()
    # Replace any previously injected panel so UI changes actually propagate.
    html = re.sub(
        r'<script>window\.MCQ_CLICK_DATA = JSON\.parse\(atob\(".*?"\)\);</script>\s*',
        "",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'<div id="mcq-learn-overlay"[\s\S]*?</div>\s*',
        "",
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r'<div id="mcq-learn-panel"[\s\S]*?<div id="mcq-learn-panel-body"></div></div>\s*',
        "",
        html,
        flags=re.DOTALL,
    )
    raw = json.dumps(mcq_click_data, ensure_ascii=False).encode("utf-8")
    b64 = base64.b64encode(raw).decode("ascii")
    intro_block = intro_html or ""
    script_and_panel = (
        f'<script>window.MCQ_CLICK_DATA = JSON.parse(atob("{b64}"));</script>\n'
        f"{intro_block}"
        '<div id="mcq-map-header" style="position:fixed;top:12px;left:12px;z-index:9997;'
        'background:rgba(255,255,255,0.95);border:1px solid #e2e8f0;border-radius:12px;padding:10px 12px;'
        'box-shadow:0 8px 20px rgba(15,23,42,0.12);font-family:system-ui,sans-serif;">'
        '<h3 style="margin:0 0 6px;color:#0f172a;font-size:16px;">My Personal Learning Map</h3>'
        '<div style="display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:#334155;">'
        '<span><b style="color:#ef4444;">●</b> Weak Topic</span>'
        '<span><b style="color:#f59e0b;">●</b> Related Concept</span>'
        '<span><b style="color:#3b82f6;">●</b> Practice MCQ</span>'
        "</div></div>"
        '<div id="mcq-map-controls" style="position:fixed;top:14px;right:18px;z-index:9997;display:flex;gap:8px;">'
        '<button id="btn-reset-view" type="button" style="border:none;background:#0f172a;color:#fff;padding:8px 10px;cursor:pointer;border-radius:8px;font-weight:600;">Reset View</button>'
        '<button id="btn-focus-weak" type="button" style="border:none;background:#ef4444;color:#fff;padding:8px 10px;cursor:pointer;border-radius:8px;font-weight:600;">Focus on Weak Topics</button>'
        "</div>"
        '<div id="mcq-learn-overlay" '
        'onclick="if(event.target===this){document.getElementById(\'mcq-learn-overlay\').style.display=\'none\';}" '
        'style="display:none;position:fixed;inset:0;background:rgba(15,23,42,0.28);z-index:9998;"></div>'
        '<div id="mcq-learn-panel" style="display:none;position:fixed;top:0;right:0;height:100vh;width:min(460px,94vw);'
        'overflow:auto;background:#ffffff;border-left:2px solid #1E88E5;box-shadow:-10px 0 24px rgba(0,0,0,0.16);'
        'padding:20px 20px 28px;font-family:system-ui,sans-serif;font-size:14px;z-index:9999;">'
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;gap:12px;">'
        '<div><p id="mcq-panel-type" style="margin:0;color:#1E88E5;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;">Node details</p>'
        '<h3 id="mcq-panel-title" style="margin:4px 0 0;font-size:20px;line-height:1.2;color:#0f172a;">Learning details</h3></div>'
        '<button type="button" onclick="document.getElementById(\'mcq-learn-panel\').style.display=\'none\';document.getElementById(\'mcq-learn-overlay\').style.display=\'none\'" '
        'style="border:none;background:#eef2f7;color:#334155;padding:8px 12px;cursor:pointer;border-radius:8px;font-weight:600;">Close</button>'
        '</div>'
        '<div id="mcq-learn-panel-body"></div></div>'
    )
    html = re.sub(
        r"<body[^>]*>",
        lambda m: m.group(0) + "\n" + script_and_panel,
        html,
        count=1,
    )

    click_hook = r"""
                  var __baseNodeStyles = {};
                  var __baseEdgeStyles = {};
                  function __cacheBaseStyles() {
                    if (!network || !network.body || !network.body.data) return;
                    var n = network.body.data.nodes && network.body.data.nodes.get ? network.body.data.nodes.get() : [];
                    var e = network.body.data.edges && network.body.data.edges.get ? network.body.data.edges.get() : [];
                    for (var i = 0; i < n.length; i++) {
                      var node = n[i];
                      __baseNodeStyles[node.id] = {
                        color: node.color,
                        opacity: typeof node.opacity === "number" ? node.opacity : 1,
                        borderWidth: node.borderWidth || 1,
                        shadow: node.shadow || false
                      };
                    }
                    for (var j = 0; j < e.length; j++) {
                      var edge = e[j];
                      __baseEdgeStyles[edge.id] = {
                        color: edge.color,
                        width: edge.width || 1,
                        opacity: typeof edge.opacity === "number" ? edge.opacity : 1
                      };
                    }
                  }
                  function __restoreFocusMode() {
                    if (!network || !network.body || !network.body.data) return;
                    var nodeUpdates = [];
                    var edgeUpdates = [];
                    var nodeIds = Object.keys(__baseNodeStyles);
                    for (var i = 0; i < nodeIds.length; i++) {
                      var nid = nodeIds[i];
                      var ns = __baseNodeStyles[nid];
                      nodeUpdates.push({ id: nid, color: ns.color, opacity: ns.opacity, borderWidth: ns.borderWidth, shadow: ns.shadow });
                    }
                    var edgeIds = Object.keys(__baseEdgeStyles);
                    for (var j = 0; j < edgeIds.length; j++) {
                      var eid = edgeIds[j];
                      var es = __baseEdgeStyles[eid];
                      edgeUpdates.push({ id: eid, color: es.color, width: es.width, opacity: es.opacity });
                    }
                    if (nodeUpdates.length) network.body.data.nodes.update(nodeUpdates);
                    if (edgeUpdates.length) network.body.data.edges.update(edgeUpdates);
                  }
                  function __applyFocusMode(selectedNodeId) {
                    if (!network || !network.body || !network.body.data || !selectedNodeId) return;
                    var connected = network.getConnectedNodes(selectedNodeId) || [];
                    var connectedSet = {};
                    connectedSet[selectedNodeId] = true;
                    for (var i = 0; i < connected.length; i++) connectedSet[connected[i]] = true;
                    var allNodes = network.body.data.nodes.get();
                    var allEdges = network.body.data.edges.get();
                    var nodeUpdates = [];
                    var edgeUpdates = [];
                    for (var n = 0; n < allNodes.length; n++) {
                      var node = allNodes[n];
                      var focused = !!connectedSet[node.id];
                      var base = __baseNodeStyles[node.id] || {};
                      nodeUpdates.push({
                        id: node.id,
                        opacity: focused ? 1 : 0.28,
                        borderWidth: node.id === selectedNodeId ? 4 : (base.borderWidth || 1),
                        shadow: node.id === selectedNodeId ? { enabled: true, color: "rgba(30,136,229,0.45)", size: 14, x: 0, y: 0 } : (base.shadow || false)
                      });
                    }
                    for (var e = 0; e < allEdges.length; e++) {
                      var edge = allEdges[e];
                      var focusedEdge = !!connectedSet[edge.from] && !!connectedSet[edge.to];
                      var edgeBase = __baseEdgeStyles[edge.id] || {};
                      edgeUpdates.push({
                        id: edge.id,
                        opacity: focusedEdge ? 0.95 : 0.16,
                        width: focusedEdge ? Math.max(2, edgeBase.width || 1) : 1
                      });
                    }
                    if (nodeUpdates.length) network.body.data.nodes.update(nodeUpdates);
                    if (edgeUpdates.length) network.body.data.edges.update(edgeUpdates);
                  }
                  __cacheBaseStyles();
                  var __allNodes = network.body && network.body.data && network.body.data.nodes ? network.body.data.nodes.get() : [];
                  document.getElementById("btn-reset-view")?.addEventListener("click", function () {
                    __restoreFocusMode();
                    network.fit({animation:{duration:500,easingFunction:'easeInOutQuad'}});
                  });
                  document.getElementById("btn-focus-weak")?.addEventListener("click", function () {
                    var weakIds = [];
                    for (var i=0;i<__allNodes.length;i++) {
                      var lbl = String(__allNodes[i].label || "").toLowerCase();
                      if (lbl.indexOf("weak:") === 0 || lbl.indexOf("relational algebra") >= 0) weakIds.push(__allNodes[i].id);
                    }
                    if (weakIds.length) network.fit({nodes: weakIds, animation:{duration:500,easingFunction:'easeInOutQuad'}});
                  });
                  network.on("click", function (params) {
                    if (params.nodes.length > 0) {
                      var id = params.nodes[0];
                      var d = window.MCQ_CLICK_DATA && window.MCQ_CLICK_DATA[id];
                      var panel = document.getElementById("mcq-learn-panel");
                      var body = document.getElementById("mcq-learn-panel-body");
                      if (!panel || !body) return;
                      __applyFocusMode(id);
                      if (d) {
                        var panelType = document.getElementById("mcq-panel-type");
                        var panelTitle = document.getElementById("mcq-panel-title");
                        if (panelType) panelType.textContent = d.kind === "mcq" ? "Practice MCQ" : "Topic Node";
                        if (panelTitle) panelTitle.textContent = d.title || (d.kind === "mcq" ? "Question details" : "Topic details");
                        var esc = function (s) {
                          var x = document.createElement("div");
                          x.textContent = s == null ? "" : String(s);
                          return x.innerHTML;
                        };
                        var overlay = document.getElementById("mcq-learn-overlay");
                        var lines = [];
                        if (d.kind === "mcq") {
                          lines.push("<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:14px 14px 10px;margin:0 0 14px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Question</p>");
                          lines.push("<p style='margin:0;color:#0f172a;line-height:1.55;font-size:14px;'>" + esc(d.question) + "</p>");
                          lines.push("</div>");
                        } else {
                          lines.push("<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:14px;margin:0 0 14px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Why this is recommended for you</p>");
                          lines.push("<p style='margin:0;color:#0f172a;line-height:1.55;font-size:14px;'>" + esc(d.why_useful_now || d.description || "Revise this concept to improve your next quiz performance.") + "</p>");
                          lines.push("</div>");
                        }
                        if (d.options && d.kind === "mcq") {
                          lines.push("<div style='margin:0 0 14px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Options</p>");
                          lines.push("<pre style='white-space:pre-wrap;margin:0;background:#f8fafc;border:1px solid #e2e8f0;padding:12px;border-radius:10px;line-height:1.55;color:#0f172a;'>" + esc(d.options) + "</pre>");
                          lines.push("</div>");
                        }
                        if (d.correct_answer) {
                          lines.push("<div style='margin:0 0 14px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Correct answer</p>");
                          lines.push("<p style='display:inline-block;margin:0;padding:6px 10px;background:#ecfdf5;color:#166534;border:1px solid #bbf7d0;border-radius:999px;font-weight:700;'>" + esc(d.correct_answer) + "</p>");
                          lines.push("</div>");
                        }
                        if (d.confidence) {
                          var confColor = d.confidence === "High" ? "#166534" : (d.confidence === "Low" ? "#991b1b" : "#92400e");
                          var confBg = d.confidence === "High" ? "#ecfdf5" : (d.confidence === "Low" ? "#fef2f2" : "#fffbeb");
                          var confBorder = d.confidence === "High" ? "#bbf7d0" : (d.confidence === "Low" ? "#fecaca" : "#fde68a");
                          lines.push("<div style='margin:0 0 14px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Recommendation confidence</p>");
                          lines.push("<span style='display:inline-block;padding:6px 10px;border-radius:999px;border:1px solid " + confBorder + ";background:" + confBg + ";color:" + confColor + ";font-weight:700;'>" + esc(d.confidence) + "</span>");
                          lines.push("</div>");
                        }
                        if (d.weak_topic) {
                          lines.push("<div style='margin:0 0 12px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Weak topic this supports</p>");
                          lines.push("<p style='margin:0;'><span style='display:inline-flex;align-items:center;gap:6px;padding:8px 12px;background:#fef2f2;border:1px solid #fecaca;border-radius:999px;color:#991b1b;font-weight:700;'>Weak Topic: " + esc(d.weak_topic) + "</span></p>");
                          lines.push("</div>");
                        }
                        if (d.related_topic) {
                          lines.push("<div style='margin:0 0 12px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Related concept</p>");
                          lines.push("<p style='margin:0;'><span style='display:inline-flex;align-items:center;gap:6px;padding:8px 12px;background:#fff7ed;border:1px solid #fed7aa;border-radius:999px;color:#9a3412;font-weight:700;'>Related Concept: " + esc(d.related_topic) + "</span></p>");
                          lines.push("</div>");
                        }
                        if (d.why_useful_now || (d.graph_reasoning && d.graph_reasoning.length)) {
                          lines.push("<div style='margin:0 0 14px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Why recommended</p>");
                          lines.push("<ul style='margin:0;padding:12px 12px 12px 28px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;color:#1e3a8a;line-height:1.55;'>");
                          if (d.why_useful_now) {
                            lines.push("<li>" + esc(d.why_useful_now) + "</li>");
                          }
                          if (d.graph_reasoning && d.graph_reasoning.length) {
                            for (var r = 0; r < d.graph_reasoning.length; r++) {
                              lines.push("<li>" + esc(d.graph_reasoning[r]) + "</li>");
                            }
                          }
                          lines.push("</ul>");
                          lines.push("</div>");
                        }
                        if (d.lecture_source) {
                          lines.push("<div style='margin:0 0 14px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Lecture source</p>");
                          lines.push("<p style='margin:0;color:#334155;line-height:1.5;'>" + esc(d.lecture_source) + "</p>");
                          lines.push("</div>");
                        }
                        if (d.graph_reasoning && d.graph_reasoning.length) {
                          lines.push("<div style='margin:0 0 14px;'>");
                          lines.push("<p style='margin:0 0 8px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Why this was selected</p>");
                          lines.push("<ul style='margin:0 0 0 18px;padding:0;color:#334155;line-height:1.5;'>");
                          for (var i = 0; i < d.graph_reasoning.length; i++) {
                            lines.push("<li>" + esc(d.graph_reasoning[i]) + "</li>");
                          }
                          lines.push("</ul>");
                          lines.push("</div>");
                        }
                        lines.push("<div style='margin-top:18px;padding:14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;'>");
                        lines.push("<p style='margin:0 0 6px;color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;'>Next step</p>");
                        lines.push("<p style='margin:0 0 10px;color:#0f172a;font-weight:600;'>" + esc(d.kind === "mcq" ? "Practice this question, then review the weak topic again." : "Revise this concept and then attempt linked practice MCQs.") + "</p>");
                        if (d.kind === "mcq") {
                          lines.push("<button type='button' style='border:none;background:#2563eb;color:#fff;padding:8px 12px;border-radius:8px;font-weight:700;cursor:pointer;'>Attempt this Question</button>");
                        }
                        lines.push("</div>");
                        body.innerHTML = lines.join("");
                        if (overlay) overlay.style.display = "block";
                        panel.style.display = "block";
                      } else {
                        __restoreFocusMode();
                        var overlay2 = document.getElementById("mcq-learn-overlay");
                        if (overlay2) overlay2.style.display = "none";
                        panel.style.display = "none";
                      }
                    } else {
                      __restoreFocusMode();
                      var overlay3 = document.getElementById("mcq-learn-overlay");
                      if (overlay3) overlay3.style.display = "none";
                      var panel2 = document.getElementById("mcq-learn-panel");
                      if (panel2) panel2.style.display = "none";
                    }
                  });
"""

    if "network.on(\"click\"" not in html and "return network;" in html:
        html = html.replace("return network;", click_hook.strip() + "\n                  return network;", 1)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


def build_pyvis_graph(
    lecture_data,
    mcq_data,
    sims,
    output_html,
    threshold=0.3,
    open_browser=True,
    enable_llm_enrichment=False,
):
    """
    Learning map: small clusters (weak / important topics, top recommended MCQs).
    Retrieval and scoring are unchanged; only visualization is filtered.
    Full retrieval scores still saved to graphrag_recommendations.json.
    """
    from pyvis.network import Network

    sims_arr = np.asarray(sims) if sims is not None else np.array([])

    quiz_state = load_quiz_state()
    recommendations, meta = retrieve_recommended_mcqs(
        mcq_data,
        lecture_data,
        sims_arr,
        quiz_state=quiz_state,
    )

    priority_files = set(meta.get("priority_files", []))

    acc_map = lecture_accuracy_map(quiz_state, lecture_data)
    bundle = build_learning_map_bundle(
        lecture_data, mcq_data, sims_arr, recommendations, meta, acc_map
    )
    centers = bundle["centers"]
    topic_ids: set = bundle["topic_ids"]
    lecture_ids_to_show: set = bundle["lecture_ids_to_show"]
    practice_recs = bundle["practice_recs"]
    topics_order = bundle["topics_order"]
    related_edges = bundle["related_edges"]
    prerequisite_links = meta.get("prerequisite_concept_links") or []
    weak_topics_confirmed = [str(w).strip() for w in (meta.get("weak_topics_confirmed") or []) if str(w).strip()]
    weak_topics_norm = {w.lower() for w in weak_topics_confirmed}
    prereq_topic_names = []
    prereq_topic_norm = set()
    for p in prerequisite_links:
        p_name = str(p.get("prerequisite_concept") or p.get("related_concept") or "").strip()
        if p_name and p_name.lower() not in prereq_topic_norm:
            prereq_topic_norm.add(p_name.lower())
            prereq_topic_names.append(p_name)

    reasons_by_qid = {r["question_id"]: r.get("reasons", []) for r in recommendations}
    trace_by_qid = {r["question_id"]: r.get("reason_trace") or {} for r in recommendations}

    meta["student_map_summary"] = {
        "weak_topics": list(meta.get("weak_topics_confirmed") or []),
        "related_concepts": [
            p.get("related_concept")
            for p in (meta.get("related_concept_links") or [])
            if p.get("related_concept")
        ],
        "practice_count": len(practice_recs),
        "uses_graphrag_topic_links": bool(meta.get("map_center_specs")),
    }
    student_learning_context = _build_student_learning_context(
        quiz_state=quiz_state,
        recommendations=recommendations,
        practice_recs=practice_recs,
        meta=meta,
    )
    meta["student_learning_context"] = student_learning_context
    _save_student_learning_context(student_learning_context)
    save_recommendations(recommendations, meta)

    net = Network(
        height="920px",
        width="100%",
        bgcolor="#f5f6fa",
        font_color="#1a1a1a",
    )
    net.force_atlas_2based()
    mcq_click_data: dict = {}
    added_nodes: set = set()
    node_kind_by_tid: dict[str, str] = {}
    weak_idx = 0
    related_idx = 0
    mcq_idx = 0

    def center_for_lecture(lid):
        for c in centers:
            if c["lecture"]["id"] == lid:
                return c
        return None

    # Lecture nodes intentionally omitted to keep the map compact for students.

    # ---- topic nodes (cluster centers only) ----
    for c in centers:
        t = c["topic"]
        lid_key = c["lecture"]["id"]
        lec_fn = c["lec_fn"]
        tid = c["tid"]
        lecture = c["lecture"]
        lecture_title = lecture.get("title") or lec_fn
        kw = ", ".join(t.get("keywords", [])[:6]) or "Main ideas"
        acc = acc_map.get(lec_fn) or acc_map.get(lec_fn.replace(".pdf", ""))
        kind_label = topic_learning_label(c["kind"], t)
        if c.get("student_label"):
            sl = c["student_label"]
            if c["kind"] == "weak":
                kind_label = f"Weak: {sl}"
            elif c["kind"] == "related":
                kind_label = f"Related: {sl}"
        topic_name = str(c.get("student_label") or kind_label).replace("Weak: ", "").replace("Related: ", "").strip()
        topic_norm = topic_name.lower()
        is_weak = topic_norm in weak_topics_norm or c["kind"] == "weak"
        is_related = c.get("kind") == "related"
        is_prereq = (not is_related) and (topic_norm in prereq_topic_norm)
        is_strong = not is_weak and not is_related and not is_prereq
        exam_freq_label = _exam_frequency_label(lec_fn in priority_files)

        if is_weak:
            node_style = {"background": "#ef4444", "border": "#b91c1c"}
            node_size = 48
            tooltip = (
                f"WEAK TOPIC: {topic_name}\n\n"
                f"Your score: {f'{acc:.0f}%' if acc is not None else 'N/A'}\n"
                f"Exam frequency: {exam_freq_label}\n"
                "Action: Study this topic first"
            )
            if "relational algebra" in topic_norm:
                node_size = 56
        elif is_related:
            node_style = {"background": "#f59e0b", "border": "#b45309"}
            node_size = 34
            tooltip = (
                f"RELATED CONCEPT: {topic_name}\n\n"
                f"Exam frequency: {exam_freq_label}\n"
                "Action: Revise this concept next to support your weak area"
            )
        elif is_prereq:
            required_before = ""
            for p in prerequisite_links:
                prereq_name = str(p.get("prerequisite_concept") or p.get("related_concept") or "").strip().lower()
                if prereq_name == topic_norm:
                    required_before = str(p.get("from_weak") or "").strip()
                    if required_before:
                        break
            node_style = {"background": "#f59e0b", "border": "#b45309"}
            node_size = 34
            tooltip = (
                f"PREREQUISITE TOPIC: {topic_name}\n\n"
                f"Required before: {required_before or 'your weak topic'}\n"
                "Action: Review this before your weak topic"
            )
        elif is_strong:
            node_style = {"background": "#44BB44", "border": "#228822"}
            node_size = 25
            tooltip = (
                f"STRONG TOPIC: {topic_name}\n\n"
                f"Your score: {f'{acc:.0f}%+' if acc is not None else '80%+'}\n"
                "Keep it up!"
            )
        else:
            node_style = {"background": "#44BB44", "border": "#228822"}
            node_size = 25
            tooltip = f"TOPIC: {topic_name}"

        if tid not in added_nodes:
            node_kind = "weak" if is_weak else ("related" if is_related or is_prereq else "other")
            node_kind_by_tid[tid] = node_kind
            x_pos = -260
            y_pos = 0
            if node_kind == "weak":
                x_pos = -260
                y_pos = -200 + (weak_idx * 120)
                weak_idx += 1
            elif node_kind == "related":
                x_pos = -20
                y_pos = -220 + (related_idx * 90)
                related_idx += 1
            net.add_node(
                tid,
                label=shorten(kind_label, 42),
                title=tooltip,
                shape="ellipse",
                size=node_size,
                color=node_style,
                shadow={"enabled": bool(is_weak), "color": "rgba(255,68,68,0.45)", "size": 22, "x": 0, "y": 0},
                x=x_pos,
                y=y_pos,
                font={"size": 18 if is_weak else 14, "bold": bool(is_weak), "color": "#111827"},
            )
            mcq_click_data[tid] = {
                "kind": "topic",
                "title": topic_name,
                "question": "",
                "description": tooltip.replace("\n", " "),
                "why_useful_now": "This concept is part of your personalized learning path.",
                "confidence": "High" if is_weak else "Medium",
                "weak_topic": topic_name if is_weak else "",
                "related_topic": topic_name if node_kind == "related" else "",
            }
            added_nodes.add(tid)
        # Lecture-link edges omitted for lower visual clutter.

    related_edge_count_by_topic: dict[str, int] = {}
    for src, dst, elabel in related_edges:
        if src in topic_ids and dst in topic_ids:
            if related_edge_count_by_topic.get(src, 0) >= 4:
                continue
            if related_edge_count_by_topic.get(dst, 0) >= 4:
                continue
            net.add_edge(
                src,
                dst,
                title=elabel,
                label="concept dependency",
                color="#ef4444",
                width=3,
                dashes=True,
            )
            related_edge_count_by_topic[src] = related_edge_count_by_topic.get(src, 0) + 1
            related_edge_count_by_topic[dst] = related_edge_count_by_topic.get(dst, 0) + 1

    # ---- prerequisite edges (distinct from similarity edges) ----
    label_to_tid = {}
    for c in centers:
        if c.get("student_label"):
            label_to_tid[str(c["student_label"]).strip().lower()] = c["tid"]
    prereq_edge_count_by_topic: dict[str, int] = {}
    for link in prerequisite_links:
        weak_label = str(link.get("from_weak", "")).strip().lower()
        prereq_label = str(link.get("prerequisite_concept") or link.get("related_concept") or "").strip().lower()
        src = label_to_tid.get(weak_label)
        dst = label_to_tid.get(prereq_label)
        if not src or not dst or src == dst:
            continue
        if prereq_edge_count_by_topic.get(src, 0) >= 3:
            continue
        if prereq_edge_count_by_topic.get(dst, 0) >= 3:
            continue
        net.add_edge(
            src,
            dst,
            title=f"Prerequisite: {link.get('from_weak', '')} -> {link.get('prerequisite_concept') or link.get('related_concept') or ''}",
            label="concept dependency",
            color="#ef4444",
            width=3,
            dashes=True,
        )
        prereq_edge_count_by_topic[src] = prereq_edge_count_by_topic.get(src, 0) + 1
        prereq_edge_count_by_topic[dst] = prereq_edge_count_by_topic.get(dst, 0) + 1

    # ---- practice MCQs (topic → MCQ only; no lecture → MCQ) ----
    practice_edge_count_by_topic: dict[str, int] = {}
    edge_pairs_added: set[tuple[str, str]] = set()
    weak_topic_ids = [c["tid"] for c in centers if node_kind_by_tid.get(c["tid"]) == "weak"]
    related_topic_ids = [c["tid"] for c in centers if node_kind_by_tid.get(c["tid"]) == "related"]

    def _connect_topic_to_mcq(topic_id: str, qid: str) -> bool:
        if not topic_id or (topic_id, qid) in edge_pairs_added:
            return False
        if practice_edge_count_by_topic.get(topic_id, 0) >= 4:
            return False
        net.add_edge(
            topic_id,
            qid,
            title="Practice this question for this topic",
            label="practice recommendation",
            color="#93c5fd",
            width=2.5,
            arrows="to",
        )
        practice_edge_count_by_topic[topic_id] = practice_edge_count_by_topic.get(topic_id, 0) + 1
        edge_pairs_added.add((topic_id, qid))
        return True
    for n, rec in enumerate(practice_recs):
        j = int(rec.get("row_index", 0))
        if j < 0 or j >= len(mcq_data):
            continue
        row = mcq_data.iloc[j]
        qid_str = str(row["id"])
        qid = f"question_{qid_str}"
        lid = row["lecture_id"]
        lecture = next((L for L in lecture_data if L["id"] == lid), None)
        lecture_title = (lecture or {}).get("title") or "Lecture"
        lec_fn = _lecture_file_basename(lecture) if lecture else ""
        reasons = reasons_by_qid.get(qid_str, rec.get("reasons", []))
        trace = trace_by_qid.get(qid_str) or rec.get("reason_trace") or {}
        col = mcq_column_index_for_row(mcq_data, j)
        link_tid = best_topic_id_for_mcq_column(
            col, lid, topics_order, sims_arr, topic_ids
        )
        cen = center_for_lecture(lid)
        if link_tid is None and cen is not None:
            link_tid = cen["tid"]

        if qid not in added_nodes:
            net.add_node(
                qid,
                label=f"Practice Q{n + 1}",
                title=(
                    "PRACTICE QUESTION\n"
                    f"Topic: {(trace.get('supports_weak_topic') or trace.get('related_concept') or 'DBMS Topic')}\n"
                    f"Why recommended: {(reasons[0] if reasons else 'You scored low in this topic')}\n"
                    "Action: Attempt this question"
                ),
                shape="box",
                size=20,
                color={"background": "#3b82f6", "border": "#1d4ed8"},
                borderWidth=2,
                shadow={"enabled": True, "color": "rgba(68,136,255,0.25)", "size": 10, "x": 0, "y": 0},
                x=280,
                y=-220 + (mcq_idx * 70),
                font={"size": 13, "color": "#0f172a"},
            )
            mcq_idx += 1
            added_nodes.add(qid)

        connected = False
        if link_tid:
            connected = _connect_topic_to_mcq(link_tid, qid) or connected
        # Ensure each MCQ is connected to at least one weak/related topic.
        if not connected:
            fallback_topics = weak_topic_ids + related_topic_ids
            for tid_fallback in fallback_topics:
                if _connect_topic_to_mcq(tid_fallback, qid):
                    connected = True
                    if not link_tid:
                        link_tid = tid_fallback
                    break
        # If linked to related, also connect to one weak topic when possible (flow weak -> related -> mcq and weak -> mcq)
        if link_tid and link_tid in related_topic_ids and weak_topic_ids:
            _connect_topic_to_mcq(weak_topic_ids[0], qid)

        rt = _related_topic_label_for_mcq(link_tid, centers, topics_order)
        wt = clean_topic_display_name((trace.get("supports_weak_topic") or "").strip())
        if not wt and link_tid:
            for cen in centers:
                if cen.get("tid") == link_tid and cen.get("kind") == "weak":
                    wt = clean_topic_display_name((cen.get("student_label") or "").strip())
                    break
        rc = clean_topic_display_name((trace.get("related_concept") or "").strip() or rt)
        explain_line = (
            f"You got low marks in {wt}. This question helps improve that concept."
            if wt
            else (trace.get("why_useful_now") or "Recommended for targeted revision.")
        )
        mcq_click_data[qid] = {
            "kind": "mcq",
            "title": f"Practice Q{n + 1}",
            "question": _clean_display_text(str(row.get("question", ""))),
            "options": _mcq_options_display(row),
            "correct_answer": _clean_display_text(str(row.get("answer", ""))),
            "weak_topic": wt,
            "related_topic": rc,
            "explanation": _mcq_explanation_text(row),
            "lecture_source": shorten(f"From Lecture {lecture_title}", 80),
            "reasons": [_clean_display_text(str(x)) for x in (reasons or []) if str(x).strip()],
            "graphrag_lines": [_clean_display_text(str(x)) for x in (trace.get("lines") or []) if str(x).strip()],
            "graph_reasoning": [_clean_display_text(str(x)) for x in ((trace.get("lines") or []) + (reasons or [])) if str(x).strip()][:6],
            "why_useful_now": _clean_display_text(explain_line),
            "confidence": _confidence_label(rec.get("score")),
        }

    # Ensure weak nodes are not isolated: each weak node must connect to a related node or MCQ.
    weak_topic_ids = [c["tid"] for c in centers if node_kind_by_tid.get(c["tid"]) == "weak"]
    related_topic_ids = [c["tid"] for c in centers if node_kind_by_tid.get(c["tid"]) == "related"]
    mcq_ids = [nid for nid in added_nodes if str(nid).startswith("question_")]
    connected_nodes = set()
    for e in net.edges:
        src = e.get("from")
        dst = e.get("to")
        if src:
            connected_nodes.add(src)
        if dst:
            connected_nodes.add(dst)
    for w_tid in weak_topic_ids:
        if w_tid in connected_nodes:
            continue
        linked = False
        for r_tid in related_topic_ids:
            if (w_tid, r_tid) in edge_pairs_added:
                continue
            net.add_edge(
                w_tid,
                r_tid,
                title="Related concept path from weak topic",
                label="concept dependency",
                color="#ef4444",
                width=3,
                dashes=True,
            )
            edge_pairs_added.add((w_tid, r_tid))
            linked = True
            break
        if linked:
            continue
        for qid in mcq_ids:
            if (w_tid, qid) in edge_pairs_added:
                continue
            net.add_edge(
                w_tid,
                qid,
                title="Practice this question for weak topic",
                label="practice recommendation",
                color="#93c5fd",
                width=2.5,
                arrows="to",
            )
            edge_pairs_added.add((w_tid, qid))
            linked = True
            break

    net.set_options(
        """
    var options = {
      "physics": {
        "enabled": true,
        "stabilization": {"iterations": 420},
        "barnesHut": {
          "gravitationalConstant": -5200,
          "springLength": 260,
          "springConstant": 0.025,
          "damping": 0.82,
          "avoidOverlap": 0.9
        }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 60,
        "hoverConnectedEdges": true,
        "selectConnectedEdges": true,
        "zoomView": true,
        "dragView": true
      },
      "nodes": {
        "font": {
          "size": 14,
          "face": "Inter, Segoe UI, sans-serif",
          "strokeWidth": 3,
          "strokeColor": "#ffffff"
        }
      },
      "edges": {
        "smooth": {
          "enabled": true,
          "type": "continuous"
        },
        "font": {
          "size": 11,
          "align": "middle",
          "strokeWidth": 3,
          "strokeColor": "#ffffff"
        }
      }
    }
    """
    )

    output_html = os.path.abspath(output_html)
    os.makedirs(os.path.dirname(output_html) or ".", exist_ok=True)

    try:
        net.write_html(output_html, cdn_resources="remote")
    except TypeError:
        net.write_html(output_html)
    try:
        with open(output_html, "r", encoding="utf-8", errors="replace") as f:
            _content = f.read()
        # PyVis can emit a local helper include (lib/bindings/utils.js) that is not
        # available under /outputs in API serving mode. Strip it to avoid 404 noise.
        _content = re.sub(
            r'\s*<script\s+src="lib/bindings/utils\.js"></script>\s*',
            "\n",
            _content,
            flags=re.IGNORECASE,
        )
        with open(output_html, "w", encoding="utf-8") as f:
            f.write(_content)
    except OSError:
        pass

    _inject_mcq_click_panel(output_html, mcq_click_data, intro_html="")
    weak_topics_with_scores = []
    twa = (quiz_state or {}).get("topic_wise_accuracy") or {}
    for wt in weak_topics_confirmed:
        score = None
        if isinstance(twa, dict):
            for topic_name, row in twa.items():
                if str(topic_name).strip().lower() == wt.lower():
                    score = float((row or {}).get("accuracy", 0.0))
                    break
        weak_topics_with_scores.append({"topic": wt, "score": score})

    top3_question_texts = []
    for rec in practice_recs[:3]:
        j = int(rec.get("row_index", -1))
        if 0 <= j < len(mcq_data):
            top3_question_texts.append(shorten(str(mcq_data.iloc[j].get("question", "")), 140))

    # Keep graph page minimal; summary cards are rendered in React.

    print(" Graph saved successfully:", output_html)
    if open_browser:
        import webbrowser

        webbrowser.open("file://" + output_html)


def create_similarity_heatmap(similarity_matrix, lecture_names, question_ids, output_file="similarity_heatmap.html"):
    try:
        import plotly.graph_objects as go

        fig = go.Figure(
            data=go.Heatmap(
                z=similarity_matrix,
                x=question_ids[:20],  # Limit to first 20 for readability
                y=lecture_names,
                colorscale="Viridis",
                hoverongaps=False,
            )
        )

        fig.update_layout(
            title="Lecture-Question Similarity Heatmap",
            xaxis_title="Questions",
            yaxis_title="Lectures",
            height=600,
        )

        fig.write_html(output_file)
        print(f"✓ Heatmap saved to {output_file}")

    except Exception as e:
        print(f"Error creating heatmap: {e}")


def create_interactive_topic_graph(lecture_data, topics, output_file="topic_graph.html"):
    net = Network(height="750px", width="100%", bgcolor="#ffffff", font_color="#222222")

    # Add lecture nodes
    for lecture in lecture_data:
        net.add_node(
            f"L_{lecture['id']}",
            label=shorten(lecture["title"], 25),
            title=lecture["title"],
            color="#FF6B6B",
            size=30,
        )

    # Add topic nodes
    for topic in topics:
        topic_id = f"T_{topic['topic_id']}"
        net.add_node(
            topic_id,
            label="/".join(topic["keywords"][:2]),
            title=", ".join(topic["keywords"]),
            color="#4ECDC4",
            size=20,
        )

        # Connect topic to its lecture
        net.add_edge(
            f"L_{topic['lecture_id']}",
            topic_id,
            title="Topic from lecture",
        )

    # Add edges between related topics
    for i, topic1 in enumerate(topics):
        for topic2 in topics[i + 1 :]:
            # Check if topics share keywords
            shared_keywords = set(topic1["keywords"]) & set(topic2["keywords"])
            if shared_keywords:
                net.add_edge(
                    f"T_{topic1['topic_id']}",
                    f"T_{topic2['topic_id']}",
                    title=f"Shared: {', '.join(list(shared_keywords)[:3])}",
                    width=2,
                )

    net.set_options(
        """
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "springLength": 100
        },
        "minVelocity": 0.75,
        "solver": "forceAtlas2Based"
      }
    }
    """
    )

    net.write_html(output_file, cdn_resources="remote")
    print(f" Topic graph saved to {output_file}")
