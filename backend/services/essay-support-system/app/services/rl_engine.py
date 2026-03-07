"""
Reinforcement Learning Engine  (from adaptive_learning.py / app.py / services.py)
"""

import pickle
from typing import Dict
from app.core.config import settings


class RLEngine:
    """Q-learning policy for adaptive difficulty selection."""

    def __init__(self):
        self.policy: Dict[str, float] = self._load()

    def _load(self) -> dict:
        if settings.RL_FILE.exists():
            try:
                with open(settings.RL_FILE, "rb") as f:
                    return pickle.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        with open(settings.RL_FILE, "wb") as f:
            pickle.dump(self.policy, f)

    def update(self, action_key: str, reward: float):
        old = self.policy.get(action_key, 0.0)
        max_val = max(self.policy.values()) if self.policy else 0
        self.policy[action_key] = old + settings.ALPHA * (
            reward + settings.GAMMA * max_val - old
        )
        self._save()

    def get_dict(self) -> dict:
        return {k: round(v, 4) for k, v in self.policy.items()}


rl_engine = RLEngine()
