"""Trial memory helper: persist and replay prior Q&A runs with fuzzy matching."""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.print_utils import cprint


DEFAULT_TRIALS_PATH = Path(__file__).resolve().parent.parent / "my_trials.json"


def _normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy matching."""
    lowered = text.lower()
    # Replace non-word chars with space; \w covers unicode letters/numbers/underscore
    cleaned = re.sub(r"[^\w]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


class TrialMemory:
    """Load/save trials so similar questions reuse the same flow."""

    def __init__(self, path: Optional[Path] = None, match_threshold: float = 0.6):
        self.path = path or DEFAULT_TRIALS_PATH
        self.match_threshold = match_threshold
        self.records: Dict[str, Dict[str, Any]] = {}
        # Map normalized text -> original question for exact fast lookup
        self._norm_index: Dict[str, str] = {}
        # Preserve file order to allow question aliases like "question1"
        self._ordered_questions: List[str] = []
        self._load()

    def _normalize_record(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ensure a record has the expected fields."""
        if not isinstance(entry, dict):
            return None

        question = str(entry.get("question", "")).strip()
        if not question:
            return None

        answer = str(entry.get("answer", "")).strip()
        raw_cues = entry.get("thinking_cues") or []
        thinking_cues: List[str] = []
        if isinstance(raw_cues, list):
            for cue in raw_cues:
                cue_text = str(cue).strip()
                if cue_text:
                    thinking_cues.append(cue_text)

        decision = entry.get("decision") if isinstance(entry.get("decision"), dict) else {}
        if not decision:
            # Legacy support: carry over top-level hints if present
            for key in ("need_thinking", "confidence", "thinking_behavior_plan"):
                if key in entry:
                    decision[key] = entry[key]

        final_confidence = str(entry.get("final_confidence", "")).strip()
        if not final_confidence:
            raw_conf = decision.get("confidence")
            if isinstance(raw_conf, str):
                raw_conf = raw_conf.strip()
                if raw_conf:
                    final_confidence = raw_conf

        return {
            "question": question,
            "answer": answer,
            "thinking_cues": thinking_cues,
            "decision": decision,
            "final_confidence": final_confidence,
        }

    def _load(self):
        """Load trials from disk."""
        if not self.path.exists():
            self.records = {}
            self._norm_index = {}
            self._ordered_questions = []
            return

        try:
            with self.path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception as err:
            cprint(f"[TrialMemory] Failed to load {self.path.name}: {err}")
            self.records = {}
            self._norm_index = {}
            self._ordered_questions = []
            return

        records: Dict[str, Dict[str, Any]] = {}
        ordered_questions: List[str] = []

        def upsert(entry: Dict[str, Any], fallback_question: Optional[str] = None):
            if fallback_question and isinstance(entry, dict) and "question" not in entry:
                entry = dict(entry)
                entry["question"] = fallback_question
            normalized = self._normalize_record(entry)
            if normalized:
                records[normalized["question"]] = normalized
                ordered_questions.append(normalized["question"])

        if isinstance(data, list):
            for entry in data:
                upsert(entry)
        elif isinstance(data, dict):
            container = data.get("records") or data.get("trials") or data
            if isinstance(container, dict):
                for key, entry in container.items():
                    upsert(entry, fallback_question=key)
            elif isinstance(container, list):
                for entry in container:
                    upsert(entry)

        self.records = records
        self._ordered_questions = ordered_questions
        self._reindex()

    def _reindex(self):
        """Build normalized index for quick exact/fuzzy matching."""
        self._norm_index = {}
        for question in self.records:
            norm = _normalize_text(question)
            if norm:
                self._norm_index[norm] = question

    def _best_fuzzy_match(self, norm_question: str) -> Optional[Tuple[str, float]]:
        """Return the closest match if above threshold."""
        best_question = None
        best_score = 0.0
        for norm_candidate, original_question in self._norm_index.items():
            score = SequenceMatcher(None, norm_question, norm_candidate).ratio()
            if score > best_score:
                best_score = score
                best_question = original_question
        if best_question is None:
            return None
        if best_score >= self.match_threshold:
            return best_question, best_score
        return None

    def _resolve_index_alias(self, text: str) -> Optional[str]:
        """Allow aliases like 'question1', 'q1' to map to nth stored item."""
        lowered = text.lower().strip()
        match = re.match(r"q(uestion)?\s*0*([0-9]+)", lowered)
        if not match:
            return None
        try:
            idx = int(match.group(2))
        except ValueError:
            return None
        if idx <= 0 or idx > len(self._ordered_questions):
            return None
        return self._ordered_questions[idx - 1]

    def get(self, question: str) -> Optional[Dict[str, Any]]:
        """Return a deep-ish copy of a stored record for the question (fuzzy)."""
        key = question.strip()
        if not key:
            return None

        # Direct index alias (e.g., "question1", "q2")
        alias_question = self._resolve_index_alias(key)
        if alias_question:
            record = self.records.get(alias_question)
            if record:
                return json.loads(json.dumps(record))

        norm = _normalize_text(key)
        if not norm:
            return None

        # Exact normalized hit
        original = self._norm_index.get(norm)
        if original:
            record = self.records.get(original)
            if record:
                return json.loads(json.dumps(record))

        # Fuzzy best-match (always returns best candidate)
        match = self._best_fuzzy_match(norm)
        if match:
            matched_question, score = match
            cprint(f"[TrialMemory] Fuzzy matched to: {matched_question} (score={score:.2f})")
            record = self.records.get(matched_question)
            if record:
                return json.loads(json.dumps(record))

        return None

    def save_record(self, record: Dict[str, Any]):
        """Persist a new/updated record to disk."""
        normalized = self._normalize_record(record)
        if not normalized:
            return

        self.records[normalized["question"]] = normalized
        self._reindex()
        self._write()

    def _write(self):
        """Write the current records to disk."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = list(self.records.values())
            with self.path.open("w", encoding="utf-8") as fp:
                json.dump(payload, fp, indent=2, ensure_ascii=False)
        except Exception as err:
            cprint(f"[TrialMemory] Failed to write {self.path.name}: {err}")
