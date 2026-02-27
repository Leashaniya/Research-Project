import pickle
import os

MODEL_PATH = "bloom_model.pkl"

if os.path.exists(MODEL_PATH):
    with open(MODEL_PATH, "rb") as f:
        bloom_model = pickle.load(f)
else:
    bloom_model = None


def classify_bloom_level(question):
    if bloom_model is None:
        return "medium"

    return bloom_model.predict([question])[0]