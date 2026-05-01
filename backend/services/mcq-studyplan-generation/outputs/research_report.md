# Retrieval Comparison Research Report

## Dataset Summary
- Total MCQs: **501**
- Weak topics evaluated: **2**
- Weak topic list: Relational Algebra, Keys and Constraints

## Method Comparison
| Method | Description |
|---|---|
| tfidf_cosine | Sparse lexical retrieval using TF-IDF + cosine similarity |
| embedding_cosine | Dense semantic retrieval using Sentence-BERT + cosine similarity |
| hybrid | Weighted fusion: 0.4 TF-IDF + 0.6 embedding |

## Metric Comparison (Average Across Weak Topics)
| Method | P@10 | R@10 | MRR@10 | NDCG@10 |
|---|---:|---:|---:|---:|
| tfidf_cosine | 0.8500 | 0.1152 | 1.0000 | 0.8861 |
| embedding_cosine | 0.8500 | 0.1135 | 1.0000 | 0.8987 |
| hybrid | 0.9000 | 0.1194 | 1.0000 | 0.9290 |

## Final Score (Data-Driven)
| Method | Final Score |
|---|---:|
| tfidf_cosine | 0.7128 |
| embedding_cosine | 0.7156 |
| hybrid | 0.7371 |

## Best Method
- **Best performing method:** `hybrid`
- Weighted score used: `0.25*precision@10 + 0.25*recall@10 + 0.25*mrr@10 + 0.25*ndcg@10`.

## Research Interpretation
- Hybrid generally balances lexical precision (TF-IDF) with semantic matching (embedding), improving ranking quality while preserving topic relevance.
- In this offline protocol, relevance is topic-alignment based over the full MCQ candidate pool for each weak topic.
