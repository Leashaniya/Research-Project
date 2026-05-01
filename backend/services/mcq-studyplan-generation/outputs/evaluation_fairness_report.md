# Evaluation Fairness Report

## Dataset Fairness Check
**Pass** - Same weak-topic set and same MCQ pool are used across methods per topic.

## Ranking Fairness Check
**Pass** - All methods are scored on full candidate pools, sorted descending, and evaluated at K=10.

## Metric Consistency Check
**Pass**
- Precision@10: hits in top-10 divided by K=10 (fixed denominator).
- Recall@10: hits in top-10 divided by total relevant in pool.
- MRR: reciprocal of first relevant rank.
- NDCG@10: binary relevance DCG normalized by ideal DCG.
- Diversity@10: unique topic count among top-10.

## Bias Analysis
- Weak topic selection bias: evaluated topics come from current quiz weak-topic state, not all syllabus topics.
- Topic imbalance: relevant-item counts vary by topic, affecting Recall and NDCG comparability.
- Label bias: relevance is topic-alignment based on auto-assigned MCQ topics (not manual relevance judgments).
- Hybrid weight bias: 0.4/0.6 is fixed and not sensitivity-tested in this run.

## Best Model Selection Validity
Result: **scientifically valid**. Current best method is `hybrid`. Best-method score is based on explicit weighted metrics: 0.25*Precision@10 + 0.25*Recall@10 + 0.25*MRR@10 + 0.25*NDCG@10.

## Recommended Improvements
- Add stratified topic evaluation (group by low/medium/high relevant pool size).
- Run sensitivity analysis for hybrid weights (e.g., 0.2/0.8, 0.5/0.5, 0.7/0.3).
- Add manual relevance validation set for a subset of MCQs.
- Report both macro and micro averages explicitly.
- Add confidence intervals via bootstrap over weak topics.

## Final Conclusion
The comparison protocol is methodologically fair (same pool, same ranking protocol, same K), but scientific reliability is partially constrained by topic imbalance and auto-derived relevance labels.
