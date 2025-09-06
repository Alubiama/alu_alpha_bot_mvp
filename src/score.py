from __future__ import annotations
import re, yaml
from typing import Dict

class Scorer:
    def __init__(self, weights: Dict[str, float]):
        self.weights = {k.lower(): float(v) for k, v in weights.items()}

    def score(self, text: str) -> tuple[float, list[str]]:
        t = text.lower()
        score = 0.0; reasons = []
        for k, w in self.weights.items():
            if k.startswith("re:"):
                if re.search(k[3:], t): score += w; reasons.append(k)
            else:
                if k in t: score += w; reasons.append(k)
        return score, reasons

def load_rules(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}
    data.setdefault("weights", {}); data.setdefault("threshold", 3.0); data.setdefault("top_n", 5)
    return data
