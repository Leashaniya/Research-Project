# Retrieval Research Explanation Log

Per weak-topic comparison of TF-IDF vs Embedding vs Hybrid using identical query/candidate settings.

## Method-Level Summary
- tfidf_cosine: P@10=0.8500, R@10=0.1152, MRR@10=1.0000, NDCG@10=0.8861, final_score=0.7128. Strong across rank quality and early precision.
- embedding_cosine: P@10=0.8500, R@10=0.1135, MRR@10=1.0000, NDCG@10=0.8987, final_score=0.7156. Strong across rank quality and early precision.
- hybrid: P@10=0.9000, R@10=0.1194, MRR@10=1.0000, NDCG@10=0.9290, final_score=0.7371. Strong across rank quality and early precision.
- BEST_METHOD=hybrid

## Query weak topic: Relational Algebra
- tfidf_cosine: P@10=0.8000, R@10=0.0941, MRR@10=1.0000, NDCG@10=0.8572, weighted=0.6878
- embedding_cosine: P@10=0.9000, R@10=0.1059, MRR@10=1.0000, NDCG@10=0.9306, weighted=0.7341
- hybrid: P@10=1.0000, R@10=0.1176, MRR@10=1.0000, NDCG@10=1.0000, weighted=0.7794
- Winner: **hybrid**. Hybrid likely benefits from balancing lexical term match and semantic similarity.

## Query weak topic: Keys and Constraints
- tfidf_cosine: P@10=0.9000, R@10=0.1364, MRR@10=1.0000, NDCG@10=0.9149, weighted=0.7378
- embedding_cosine: P@10=0.8000, R@10=0.1212, MRR@10=1.0000, NDCG@10=0.8669, weighted=0.6970
- hybrid: P@10=0.8000, R@10=0.1212, MRR@10=1.0000, NDCG@10=0.8580, weighted=0.6948
- Winner: **tfidf_cosine**. TF-IDF likely wins where query wording overlaps strongly with MCQ lexical terms.

## Example Cases
- tfidf_cosine wins on: Keys and Constraints
- embedding_cosine wins on: None
- hybrid wins on: Relational Algebra
