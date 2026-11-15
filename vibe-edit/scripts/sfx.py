"""Synthesized sound effects for reels: whoosh (on zoom cuts), pop (on key words), riser + hit (on the hook).

Everything is generated from noise and sine waves with numpy, so there are no sample files to license, ship
or download, and the same build always gives the same sound (fixed seeds). Levels are set relative to the
speaker's average voice level, measured on the voice + music mix before the effects go in.

  events = [{"kind": "whoosh", "at": 4.17, "db": -8, "variant": 1}, ...]   # "at" = the moment it lands
  track = render(events, total_s, voice_db)        # float32 stereo, 48 kHz
  write_wav(path, track)
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000
WIN = int(0.03 * SR)  # 30 ms: the window for "how loud is this sound at its loudest"


def _svf(x: np.ndarray, fc: np.ndarray | float, q: float, mode: str = "band") -> np.ndarray:
    """Chamberlin state-variable filter with a per-sample cutoff (band- or low-pass)."""
    fc = np.broadcast_to(np.clip(fc, 20, SR / 7), x.shape)
    f = 2 * np.sin(np.pi * fc / SR)
    damp = 1.0 / q
    low = band = 0.0
    out = np.empty_like(x)
    for i in range(len(x)):
        low += f[i] * band
        high = x[i] - low - damp * band
        band += f[i] * high
        out[i] = band if mode == "band" else low
    return out


def _pan(sig: np.ndarray, theta: np.ndarray | float) -> np.ndarray:
    theta = np.broadcast_to(theta, sig.shape)
    return np.stack([sig * np.cos(theta), sig * np.sin(theta)], axis=1)


def whoosh(variant: int = 0, dur: float = 0.55, peak: float = 0.6) -> tuple[np.ndarray, float]:
    """Air rushing past: band-passed noise sweeping up then a little down, panned across.
    Returns (stereo, seconds from the start of the sound to its loudest point)."""
    rng = np.random.default_rng(101 + variant)
    n = int(dur * SR)
    u = np.arange(n) / n
    f_hi = (1500, 1800, 2200)[variant % 3]
    shape = np.where(u < peak, u / peak, 1 - 0.45 * (u - peak) / (1 - peak))
    fc = 180 * (f_hi / 180) ** shape
    sig = _svf(rng.standard_normal(n), fc, 1.2) + 1.2 * _svf(rng.standard_normal(n), fc * 0.3, 0.8, "low")
    sig = _svf(sig, 5000.0, 0.707, "low")  # take the hiss off the top
    env = np.where(u < peak, (u / peak) ** 2.2, ((1 - u) / (1 - peak)) ** 1.6)
    side = 1 if variant % 2 == 0 else -1  # alternate left->right and right->left
    return _pan(sig * env, np.pi / 4 + side * 0.32 * np.tanh(3 * (u - peak))), peak * dur


def riser(dur: float = 0.45) -> tuple[np.ndarray, float]:
    """A rising whoosh that peaks at its very end (lands into a hit)."""
    rng = np.random.default_rng(7)
    n = int(dur * SR)
    u = np.arange(n) / n
    fc = 250 * (2800 / 250) ** u
    sig = _svf(rng.standard_normal(n), fc, 1.5) + 1.0 * _svf(rng.standard_normal(n), fc * 0.3, 0.8, "low")
    sig = _svf(sig, 6000.0, 0.707, "low")
    env = u ** 3 * np.clip((1 - u) / 0.04, 0, 1)
    return _pan(sig * env, np.pi / 4), dur * 0.96


def pop(dur: float = 0.12) -> tuple[np.ndarray, float]:
    """A soft bubble pop: a quick upward blip with a tiny click on the front."""
    rng = np.random.default_rng(3)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 320 + 700 * (1 - np.exp(-t / 0.012))
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = (np.sin(ph) + 0.3 * np.sin(2 * ph)) * (1 - np.exp(-t / 0.0015)) * np.exp(-t / 0.04)
    click = rng.standard_normal(n) * np.exp(-t / 0.0012)
    click = click - np.concatenate([[0.0], click[:-1]])  # crude high-pass: keep it a tick, not a thump
    return _pan(tone + 0.12 * click, np.pi / 4), 0.004


def hit(dur: float = 0.8) -> tuple[np.ndarray, float]:
    """An impact: a pitched-down boom plus a mid 'knock' and a bright snap. Phone speakers play little below
    ~150 Hz, so the boom is saturated (harmonics) and the knock carries the hit on a phone."""
    rng = np.random.default_rng(11)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 60 + 160 * np.exp(-t / 0.04)
    attack = 1 - np.exp(-t / 0.002)
    boom = np.tanh(4 * np.sin(2 * np.pi * np.cumsum(f) / SR) * attack * np.exp(-t / 0.22)) * 0.6
    knock = np.sin(2 * np.pi * np.cumsum(190 + 140 * np.exp(-t / 0.02)) / SR) * attack * np.exp(-t / 0.06)
    snap = _svf(rng.standard_normal(n), 2500.0, 0.9) * np.exp(-t / 0.02)
    body = _svf(rng.standard_normal(n), 900.0, 0.7, "low") * np.exp(-t / 0.08)
    return _pan(boom + 0.9 * knock + 0.9 * snap + 0.8 * body, np.pi / 4), 0.003


def peak_db(x: np.ndarray) -> float:
    """Level of the loudest 30 ms of a (mono or stereo) signal, in dBFS."""
    m = x.mean(axis=1) if x.ndim == 2 else x
    if len(m) < WIN:
        return 20 * np.log10(np.sqrt(np.mean(m ** 2)) + 1e-12)
    c = np.cumsum(np.concatenate([[0.0], m.astype(np.float64) ** 2]))
    return 10 * np.log10((c[WIN:] - c[:-WIN]).max() / WIN + 1e-12)


def make(kind: str, variant: int = 0) -> tuple[np.ndarray, float]:
    return {"whoosh": lambda: whoosh(variant), "riser": riser, "pop": pop, "hit": hit}[kind]()


def render(events: list[dict], total: float, voice_db: float) -> np.ndarray:
    """Place every event so its loudest point lands on ev['at'], at ev['db'] relative to the voice level."""
    out = np.zeros((int(total * SR) + 1, 2), dtype=np.float64)
    cache = {}
    for ev in events:
        key = (ev["kind"], ev.get("variant", 0))
        if key not in cache:
            cache[key] = make(*key)
        sig, lead = cache[key]
        g = 10 ** ((voice_db + ev["db"] - peak_db(sig)) / 20)
        s0 = int(round((ev["at"] - lead) * SR))
        a, b = max(s0, 0), min(s0 + len(sig), len(out))
        if b > a:
            out[a:b] += g * sig[a - s0:b - s0]
        ev["start"] = round(max(ev["at"] - lead, 0), 3)
        ev["end"] = round(min(ev["at"] - lead + len(sig) / SR, total), 3)
    return out.astype(np.float32)


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    assert sw == 2, f"{path}: expected 16-bit PCM"
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    return x.reshape(-1, ch), sr


def write_wav(path: Path, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def voice_level_db(path: Path, spans: list[tuple[float, float]]) -> float:
    """Average (RMS) level of the speech in a wav, over the given word spans, in dBFS."""
    x, sr = read_wav(path)
    m = x.mean(axis=1)
    parts = [m[int(s * sr):int(e * sr)] for s, e in spans if e > s]
    sp = np.concatenate(parts) if parts else m
    return float(20 * np.log10(np.sqrt(np.mean(sp.astype(np.float64) ** 2)) + 1e-12))
