import pandas as pd

# Load Kaggle dataset
df = pd.read_csv("bloomsDataset/blooms_taxonomy_dataset.csv")

# Rename columns (if needed)
df.columns = ["question", "category"]

# Mapping Bloom levels → difficulty
mapping = {
    "BT1": "easy",
    "BT2": "easy",
    "BT3": "medium",
    "BT4": "medium",
    "BT5": "hard",
    "BT6": "hard"
}

df["label"] = df["category"].map(mapping)

# Keep only needed columns
df = df[["question", "label"]]
forbidden = ["draw", "diagram", "illustrate", "label the diagram"]
df = df[~df["question"].str.lower().str.contains("|".join(forbidden))]

# Drop missing values
df = df.dropna()

# Save cleaned dataset
df.to_csv("bloomsDataset/bloom_3class_dataset.csv", index=False)

print("Converted dataset saved as bloom_3class_dataset.csv")
print(df["label"].value_counts())