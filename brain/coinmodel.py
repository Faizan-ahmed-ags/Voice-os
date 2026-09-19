"""Slot for YOUR own coin model.

Drop your model file(s) into  data/custom_models/  (or upload via the Brain
page). Supported formats:

  * joblib / pickle  — object exposing .predict(X) or .predict_proba(X)
  * ONNX             — .onnx file (needs `pip install onnxruntime`)

The loader is defensive by design: a broken/hostile file must never crash
trading. Custom signals are ADVISORY — they are surfaced on the Brain page
and in /api/models, but do not gate or trigger orders until you explicitly
set  "custom_model_trusted": true  in config.json.

Feature contract: if your model was trained on our 16 engineered features,
name the columns explicitly (pickle a sklearn Pipeline trained on a DataFrame
with our feature names, or include a feature_order list in model_meta.json).
Otherwise the loader passes the raw 16-feature vector and reports a
`feature_match: unknown` warning.
"""
import json
import pickle
import re
import time
from pathlib import Path

from . import util

MODELS_DIR = util.DATA_DIR / "custom_models"
CUSTOM_FEATURES = [
    "ret_1d", "ret_5d", "ret_20d", "rsi_14", "macd", "macd_signal", "macd_hist",
    "donchian_pos", "vol_20", "vol_ratio", "volume_z", "gh_z", "above_sma50",
    "above_sma200", "dist_sma50", "hl_spread",
]


def _ensure_dir():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def _load_object(path):
    """Load a joblib/pickle model file. Never raises."""
    try:
        try:
            import joblib
            return joblib.load(path)
        except ImportError:
            with open(path, "rb") as f:
                return pickle.load(f)
    except Exception as e:
        return {"__error__": f"load failed: {e}"}


class CoinModel:
    """Wrapper around a user-supplied model with predict dispatch."""

    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.stem
        self.fmt = self.path.suffix.lower().lstrip(".")
        self.obj = None
        self.error = None
        self.feature_match = "unknown"
        self.loaded_at = util.iso()
        self._load()

    def _load(self):
        if self.fmt == "onnx":
            self._load_onnx()
        else:
            obj = _load_object(self.path)
            if isinstance(obj, dict) and "__error__" in obj:
                self.error = obj["__error__"]
            else:
                self.obj = obj

    def _load_onnx(self):
        try:
            import onnxruntime as ort
            self.obj = ort.InferenceSession(str(self.path), providers=["CPUExecutionProvider"])
        except ImportError:
            self.error = "onnx file but onnxruntime not installed (pip install onnxruntime)"
        except Exception as e:
            self.error = f"onnx load failed: {e}"

    # ------------------------------------------------------------- inference
    def _proba_from_obj(self, x):
        obj = self.obj
        if hasattr(obj, "predict_proba"):
            p = obj.predict_proba(x)[0]
            return float(p[-1])  # P(class=1) — upside class
        if hasattr(obj, "predict"):
            v = obj.predict(x)
            try:
                return float(v[0])
            except (TypeError, IndexError):
                return float(v)
        return None

    def _proba_from_onnx(self, x):
        import numpy as np
        inp = self.obj.get_inputs()[0].name
        out = self.obj.run(None, {inp: np.asarray(x, dtype=np.float32)})[0]
        a = np.asarray(out).reshape(-1)
        if a.size >= 2:  # softmax-style two-class output
            e = np.exp(a - a.max())
            return float((e / e.sum())[-1])
        return float(a[0])

    def predict_up_probability(self, features_row):
        """features_row: list of 16 floats in CUSTOM_FEATURES order.
        Returns (probability or None, note)."""
        if self.error:
            return None, self.error
        try:
            x = [list(map(float, features_row))]
            if self.fmt == "onnx":
                return self._proba_from_onnx(x), "onnx"
            p = self._proba_from_obj(x)
            if p is None:
                return None, "model exposes neither predict_proba nor predict"
            p = min(max(p, 0.0), 1.0) if 0.0 <= p <= 1.0 else p
            return p, "ok"
        except Exception as e:
            return None, f"predict failed: {e}"

    def describe(self):
        return {
            "name": self.name,
            "file": self.path.name,
            "format": self.fmt,
            "error": self.error,
            "feature_match": self.feature_match,
            "loaded_at": self.loaded_at,
        }


_CACHE = {"entries": {}, "checked": 0.0}


def discover(refresh=False):
    """Scan data/custom_models/ — cached for 5s. Returns {name: CoinModel}."""
    _ensure_dir()
    now = time.time()
    if not refresh and now - _CACHE["checked"] < 5:
        return _CACHE["entries"]
    entries = {}
    for p in sorted(MODELS_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() in (".joblib", ".pkl", ".pickle", ".onnx"):
            entries[p.stem] = CoinModel(p)
    _CACHE["entries"] = entries
    _CACHE["checked"] = now
    return entries


def save_upload(filename, content_bytes):
    """Persist an uploaded model file. Returns stored filename."""
    _ensure_dir()
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name) or "coin_model.bin"
    if not safe.lower().endswith((".joblib", ".pkl", ".pickle", ".onnx")):
        safe += ".joblib"
    target = MODELS_DIR / safe
    target.write_bytes(content_bytes)
    util.log_event("COINMODEL", f"stored upload {safe} ({len(content_bytes)} bytes)")
    discover(refresh=True)
    return safe


def remove(name):
    _ensure_dir()
    p = MODELS_DIR / f"{name}"
    if p.exists():
        p.unlink()
    discover(refresh=True)


def status():
    """Summary for the Brain page / /api/models."""
    from .config import load
    cfg = load()
    trusted = bool(cfg.get("custom_model_trusted", False))
    entries = {n: m.describe() for n, m in discover().items()}
    return {
        "dir": str(MODELS_DIR),
        "trusted": trusted,
        "advisory_note": (
            "custom signals are advisory only — they do not place orders"
            if not trusted else
            "custom signals trusted: they may pre-rank candidates (still halal-gated)"
        ),
        "models": entries,
    }


def predict_signal(symbol_features):
    """Advisory signal across all loaded custom models for one feature row.
    Returns {model_name: {"p_up": float|None, "note": str}}."""
    out = {}
    for name, m in discover().items():
        if m.error:
            out[name] = {"p_up": None, "note": m.error}
            continue
        p, note = m.predict_up_probability(symbol_features)
        out[name] = {"p_up": p, "note": note}
    return out
