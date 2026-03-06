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

dataset_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "bloomsDataset",
    "bloom_3class_dataset.csv"
)

df = pd.read_csv(dataset_path)

print("\nTotal rows in dataset:", len(df))

# -------------------------------
# Clean dataset
# -------------------------------

df = df.dropna()
df = df.reset_index(drop=True)

print("Rows after cleaning:", len(df))

X = df["question"]
y = df["label"]


# -------------------------------
# Train/Test Split (for evaluation)
# -------------------------------

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

print("\nTrain size:", len(X_train))
print("Test size:", len(X_test))


# -------------------------------
# Models
# -------------------------------

models = {
    "LinearSVC": LinearSVC(class_weight="balanced"),
    "LogisticRegression": LogisticRegression(max_iter=2000, class_weight="balanced"),
    "MultinomialNB": MultinomialNB()
}

best_model = None
best_model_name = ""
best_test_acc = 0

print("\n=========== MODEL COMPARISON ===========")

for name, clf in models.items():

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1,2),
            stop_words="english",
            max_features=5000,
            min_df=3,
            max_df=0.85
        )),
        ("clf", clf)
    ])

    pipeline.fit(X_train, y_train)

    y_test_pred = pipeline.predict(X_test)

    test_acc = accuracy_score(y_test, y_test_pred)

    print(f"\n{name} Test Accuracy:", test_acc)

    if test_acc > best_test_acc:
        best_test_acc = test_acc
        best_model = pipeline
        best_model_name = name


print("\n================================")
print("Best Model Selected:", best_model_name)
print("Best Test Accuracy:", best_test_acc)


# -------------------------------
# Overfitting Check
# -------------------------------

train_pred = best_model.predict(X_train)
test_pred = best_model.predict(X_test)

train_acc = accuracy_score(y_train, train_pred)
test_acc = accuracy_score(y_test, test_pred)

print("\n=========== OVERFITTING CHECK ===========")
print("Train Accuracy:", train_acc)
print("Test Accuracy :", test_acc)

overfit = False

if train_acc - test_acc > 0.05:
    print("⚠ Overfitting detected. Applying Hyperparameter Tuning...")
    overfit = True


# -------------------------------
# Hyperparameter Tuning
# -------------------------------

if overfit:

    param_grid = {
        "tfidf__max_features": [5000, 8000],
        "tfidf__ngram_range": [(1,1), (1,2)]
    }

    if best_model_name == "LinearSVC":
        param_grid["clf__C"] = [0.1, 1, 10]

    elif best_model_name == "LogisticRegression":
        param_grid["clf__C"] = [0.1, 1, 10]

    elif best_model_name == "MultinomialNB":
        param_grid["clf__alpha"] = [0.1, 0.5, 1]

    grid = GridSearchCV(
        best_model,
        param_grid,
        cv=5,
        scoring="accuracy",
        n_jobs=-1
    )

    grid.fit(X_train, y_train)

    best_model = grid.best_estimator_

    print("Best Parameters:", grid.best_params_)


# -------------------------------
# Final Test Evaluation
# -------------------------------

print("\n=========== FINAL TEST PERFORMANCE ===========")

final_pred = best_model.predict(X_test)

print("\nFinal Accuracy:", accuracy_score(y_test, final_pred))

print("\nClassification Report")
print(classification_report(y_test, final_pred))

print("\nConfusion Matrix")
print(confusion_matrix(y_test, final_pred))


# -------------------------------
# Cross Validation (uses ALL rows)
# -------------------------------

print("\n=========== CROSS VALIDATION (ALL DATA) ===========")

cv_scores = cross_val_score(best_model, X, y, cv=5)

print("Cross Validation Scores:", cv_scores)
print("Average CV Accuracy:", cv_scores.mean())


# -------------------------------
# Train Final Model on FULL dataset
# -------------------------------

print("\nTraining final model on FULL dataset (8039 rows)...")

best_model.fit(X, y)


# -------------------------------
# Save Model
# -------------------------------

with open("bloom_model.pkl", "wb") as f:
    pickle.dump(best_model, f)

print("\nFinal model trained with FULL dataset and saved as bloom_model.pkl")


MODEL_PATH = "bloom_model.pkl"

if os.path.exists(MODEL_PATH):
    with open(MODEL_PATH, "rb") as f:
        bloom_model = pickle.load(f)
    print("✓ bloom_model.pkl successfully loaded")
else:
    bloom_model = None
    print("⚠ Model file not found")