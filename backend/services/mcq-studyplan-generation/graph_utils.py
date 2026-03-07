from pyvis.network import Network
from nlp_utils import shorten
import openai
import os
import re
import networkx as nx
import numpy as np

# OPENAI CONFIG (keep for graph enrichment only) - use env
openai.api_key = openai.api_key or os.getenv("OPENAI_API_KEY", "").strip()

# LLM ENRICHMENT (keep for graph visualization only)
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
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        return response["choices"][0]["message"]["content"]
    
    except Exception as e:
        print(" LLM error:", e)
        return "Explanation unavailable\nTopic: unknown"

# GRAPH BUILDER
def build_pyvis_graph(lecture_data, mcq_data, sims, output_html, threshold=0.3, open_browser=True):
    from pyvis.network import Network

    net = Network(
        height="900px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#222222"
    )
    net.force_atlas_2based()
    
    # ---- lectures ----
    for lecture in lecture_data:
        lid = f"lecture_{lecture['id']}"
        net.add_node(
            lid,
            label=shorten(lecture["title"], 30),
            title=lecture["title"],
            shape="circle",
            size=35,
            color="#FF6B6B"
        )
    
    # ---- topics ----
    for lecture in lecture_data:
        for topic in lecture.get("topics", []):
            tid = f"topic_{topic['topic_id']}_{lecture['id']}"
            net.add_node(
                tid,
                label="/".join(topic["keywords"][:2]),
                title=", ".join(topic["keywords"]),
                shape="ellipse",
                size=25,
                color="#4ECDC4"
            )
            net.add_edge(
                f"lecture_{lecture['id']}",
                tid,
                title="Contains topic"
            )
    
    # ---- QUESTION NODES + LLM ----
    for idx, row in mcq_data.iterrows():
        qid = f"question_{row['id']}"
        
        lecture_topics = next(
            (l.get("topics", []) for l in lecture_data if l["id"] == row["lecture_id"]),
            []
        )
        
        llm_text = llm_enrich_question(row["question"], lecture_topics)
        
        net.add_node(
            qid,
            label=f"Q{idx + 1}",
            title=(
                f"<b>Question</b><br>{row['question']}<br><br>"
                f"<b>LLM Insight</b><br>{llm_text}"
            ),
            shape="box",
            size=20,
            color="#FFD93D"
        )
        
        # Connect question to its lecture
        net.add_edge(
            f"lecture_{row['lecture_id']}",
            qid,
            title="Question from lecture"
        )
        
        # 🔥 Intelligent topic linking
        for topic in lecture_topics:
            for kw in topic.get("keywords", [])[:2]:
                if kw.lower() in llm_text.lower():
                    net.add_edge(
                        qid,
                        f"topic_{topic['topic_id']}_{row['lecture_id']}",
                        title="LLM semantic relevance",
                        width=3,
                        color="#1A73E8"
                    )
                    break
    
    # ---- physics ----
    net.set_options("""
    var options = {
      "physics": {
        "stabilization": {"iterations": 200},
        "barnesHut": {
          "gravitationalConstant": -8000,
          "springLength": 200
        }
      },
      "interaction": {
        "hover": true
      }
    }
    """)
    
    # ---- SAVE & OPEN ----
    output_html = os.path.abspath(output_html)
    os.makedirs(os.path.dirname(output_html), exist_ok=True)
    
    net.write_html(output_html, cdn_resources="remote")

    print(" Graph saved successfully:", output_html)
    if open_browser:
        import webbrowser
        webbrowser.open("file://" + output_html)

def create_similarity_heatmap(similarity_matrix, lecture_names, question_ids, output_file="similarity_heatmap.html"):
    try:
        import plotly.graph_objects as go
        
        fig = go.Figure(data=go.Heatmap(
            z=similarity_matrix,
            x=question_ids[:20],  # Limit to first 20 for readability
            y=lecture_names,
            colorscale='Viridis',
            hoverongaps=False
        ))
        
        fig.update_layout(
            title='Lecture-Question Similarity Heatmap',
            xaxis_title='Questions',
            yaxis_title='Lectures',
            height=600
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
            label=shorten(lecture['title'], 25),
            title=lecture['title'],
            color="#FF6B6B",
            size=30
        )
    
    # Add topic nodes
    for topic in topics:
        topic_id = f"T_{topic['topic_id']}"
        net.add_node(
            topic_id,
            label="/".join(topic['keywords'][:2]),
            title=", ".join(topic['keywords']),
            color="#4ECDC4",
            size=20
        )
        
        # Connect topic to its lecture
        net.add_edge(
            f"L_{topic['lecture_id']}",
            topic_id,
            title="Topic from lecture"
        )
    
    # Add edges between related topics
    for i, topic1 in enumerate(topics):
        for topic2 in topics[i + 1:]:
            # Check if topics share keywords
            shared_keywords = set(topic1['keywords']) & set(topic2['keywords'])
            if shared_keywords:
                net.add_edge(
                    f"T_{topic1['topic_id']}",
                    f"T_{topic2['topic_id']}",
                    title=f"Shared: {', '.join(list(shared_keywords)[:3])}",
                    width=2
                )
    
    net.set_options("""
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
    """)
    
    net.write_html(output_file, cdn_resources="remote")
    print(f" Topic graph saved to {output_file}")