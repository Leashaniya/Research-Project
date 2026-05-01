import pandas as pd
import pickle
import os

from sklearn.model_selection import train_test_split, GridSearchCV, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

from sklearn.svm import LinearSVC
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB


# -------------------------------
# Load dataset
# -------------------------------

DATASET_PATH = "../mergedDataset/final_merged_dataset.csv"   # <-- update path if needed
MODEL_OUTPUT  = "../bloom_model.pkl"

VALID_BLOOM_LABELS = [
    "Remember",
    "Understand",
    "Apply",
    "Analyze",
    "Evaluate",
    "Create"
]


df = pd.read_csv(DATASET_PATH)

print("\nTotal rows in dataset:", len(df))
print("Label distribution:")
print(df["bloom_label"].value_counts())


# -------------------------------
# Clean dataset
# -------------------------------

df = df.dropna(subset=["question", "bloom_label"])
df = df[df["bloom_label"].isin(VALID_BLOOM_LABELS)]
df = df.reset_index(drop=True)

print("\nRows after cleaning:", len(df))

X = df["question"]
y = df["bloom_label"]


# -------------------------------
# Train/Test Split
# -------------------------------

X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,
    random_state=42,
    stratify=y          # keeps bloom class balance
)

print("\nTrain size:", len(X_train))
print("Test size :", len(X_test))


# -------------------------------
# Models
# -------------------------------

models = {
    "LinearSVC": LinearSVC(class_weight="balanced", max_iter=2000),
    "LogisticRegression": LogisticRegression(max_iter=2000, class_weight="balanced",random_state=42),
    "MultinomialNB": MultinomialNB()
}

best_model      = None
best_model_name = ""
best_test_acc   = 0

print("\n=========== MODEL COMPARISON ===========")

for name, clf in models.items():

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            max_features=10000,   # bumped up — dataset is now larger
            min_df=2,
            max_df=0.90,
            sublinear_tf=True
        )),
        ("clf", clf)
    ])

    pipeline.fit(X_train, y_train)

    y_pred    = pipeline.predict(X_test)
    test_acc  = accuracy_score(y_test, y_pred)

    print(f"\n{name}")
    print(f"  Test Accuracy: {test_acc:.4f}")
    print(classification_report(y_test, y_pred, target_names=["Remember","Understand","Apply","Analyze","Evaluate","Create"]))

    if test_acc > best_test_acc:
        best_test_acc   = test_acc
        best_model      = pipeline
        best_model_name = name


print("\n================================")
print("Best Model Selected:", best_model_name)
print("Best Test Accuracy :", best_test_acc)


# -------------------------------
# Overfitting Check
# -------------------------------

train_pred = best_model.predict(X_train)
test_pred  = best_model.predict(X_test)

train_acc = accuracy_score(y_train, train_pred)
test_acc  = accuracy_score(y_test,  test_pred)

print("\n=========== OVERFITTING CHECK ===========")
print("Train Accuracy:", train_acc)
print("Test Accuracy :", test_acc)

overfit = train_acc - test_acc > 0.05

if overfit:
    print("⚠ Overfitting detected. Applying Hyperparameter Tuning...")


# -------------------------------
# Hyperparameter Tuning (if needed)
# -------------------------------

if overfit:

    param_grid = {
        "tfidf__max_features": [5000, 10000],
        "tfidf__ngram_range":  [(1, 1), (1, 2)]
    }

    if best_model_name == "LinearSVC":
        param_grid["clf__C"] = [0.1, 1, 10]
    elif best_model_name == "LogisticRegression":
        param_grid["clf__C"] = [0.1, 1, 10]
    elif best_model_name == "MultinomialNB":
        param_grid["clf__alpha"] = [0.1, 0.5, 1.0]

    grid = GridSearchCV(
        best_model,
        param_grid,
        cv=5,
        scoring="accuracy",
        n_jobs=-1,
        verbose=1
    )
    grid.fit(X_train, y_train)

    best_model = grid.best_estimator_
    print("Best Parameters:", grid.best_params_)


# -------------------------------
# Final Test Evaluation
# -------------------------------

print("\n=========== FINAL TEST PERFORMANCE ===========")

final_pred = best_model.predict(X_test)

print("Final Accuracy:", accuracy_score(y_test, final_pred))
print("\nClassification Report:")
print(classification_report(y_test, final_pred,labels=VALID_BLOOM_LABELS,
        target_names=VALID_BLOOM_LABELS,
        zero_division=0))
print("\nConfusion Matrix:")
print(confusion_matrix(y_test, final_pred,labels=VALID_BLOOM_LABELS))


# -------------------------------
# Cross Validation (all data)
# -------------------------------

print("\n=========== CROSS VALIDATION (ALL DATA) ===========")

cv_scores = cross_val_score(best_model, X, y, cv=5, n_jobs=-1)

print("CV Scores :", cv_scores)
print("Average CV:", cv_scores.mean().round(4))


# -------------------------------
# Train Final Model on FULL dataset
# -------------------------------

print(f"\nTraining final model on full dataset ({len(df)} rows)...")
best_model.fit(X, y)


# -------------------------------
# Save Model
# -------------------------------

with open(MODEL_OUTPUT, "wb") as f:
    pickle.dump(best_model, f)

print(f"\n✓ Model saved as {MODEL_OUTPUT}")

# -------------------------------
# BLOOM → DIFFICULTY FUNCTION
# -------------------------------

def map_bloom_to_difficulty(bloom):
    if bloom in ["Remember", "Understand"]:
        return "easy"
    elif bloom in ["Apply", "Analyze"]:
        return "medium"
    else:
        return "hard"

# -------------------------------
# TEST
# -------------------------------

sample = [
    "What is a primary key?",
    "Explain normalization process",
    "Analyze SQL query optimization",
    "Design a database system"
]

print("\nTEST OUTPUT")

for q in sample:
    bloom = best_model.predict([q])[0]
    difficulty = map_bloom_to_difficulty(bloom)

    print(f"{q}")
    print(f" → Bloom: {bloom}")
    print(f" → Difficulty: {difficulty}\n")        

# Quick load-check
with open(MODEL_OUTPUT, "rb") as f:
    loaded = pickle.load(f)

sample_questions = [
    "What is a linked list?",
    "Design a system that handles 1 million requests per second.",
    "Analyze the trade-offs between SQL and NoSQL databases."
]

print("\n=========== QUICK SMOKE TEST ===========")
for q in sample_questions:
    pred = loaded.predict([q])[0]
    print(f"  [{pred.upper():6}]  {q}")
