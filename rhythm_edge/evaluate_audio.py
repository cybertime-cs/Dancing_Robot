"""Evaluate the saved recognizer on the current short source recordings.

The direct test uses the WAV files as they are. Other cases are deterministic
signal changes made from those same files; they are not microphone recordings.
No source or database file is modified.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from recognizer import RhythmRecognizer, SAMPLE_RATE, read_wav


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "rhythm_edge" / "rhythm_database.npz"
SOURCE = ROOT / "rhythm_train"
OUTPUT = ROOT / "rhythm_edge" / "evaluation_results.json"


def speed_change(audio: np.ndarray, factor: float) -> np.ndarray:
    positions = np.arange(round(audio.size / factor), dtype=np.float64) * factor
    return np.interp(positions, np.arange(audio.size), audio).astype(np.float32)


def add_noise(audio: np.ndarray, snr_db: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise_std = max(float(np.std(audio)), 1e-6) * 10 ** (-snr_db / 20)
    return (audio + rng.normal(0, noise_std, audio.size)).astype(np.float32)


def altered_cases(audio: np.ndarray, seed: int):
    audio = audio[:round(15 * SAMPLE_RATE)]
    yield "起始延迟加15dB噪声", add_noise(
        np.concatenate((np.zeros(round(0.5 * SAMPLE_RATE), np.float32),
                        audio[:-round(0.5 * SAMPLE_RATE)] * 0.6)), 15, seed)
    yield "速度加快2%", speed_change(audio, 1.02)
    yield "速度减慢2%", speed_change(audio, 0.98)
    spectrum = np.fft.rfft(audio)
    freq = np.fft.rfftfreq(audio.size, 1 / SAMPLE_RATE)
    spectrum[(freq < 250) | (freq > 3200)] = 0
    filtered = np.fft.irfft(spectrum, n=audio.size).astype(np.float32)
    echo = filtered.copy()
    delay = round(0.07 * SAMPLE_RATE)
    echo[delay:] += 0.35 * filtered[:-delay]
    yield "限带加70ms回声", add_noise(echo, 25, seed + 1)


def main():
    recognizer = RhythmRecognizer(DATABASE)
    rows = []
    for number, name in enumerate(recognizer.names):
        path = SOURCE / name
        audio, _ = read_wav(path)
        cases = [("原始WAV", None), *altered_cases(audio, 100 + number)]
        for condition, altered in cases:
            begin = time.perf_counter()
            result = (recognizer.recognize_wav(path) if altered is None
                      else recognizer.recognize_audio(altered))
            elapsed = time.perf_counter() - begin
            row = {
                "source": name,
                "condition": condition,
                "predicted": result.name,
                "correct": result.name == name,
                "score": round(result.score, 4),
                "margin": round(result.margin, 4),
                "seconds_on_this_computer": round(elapsed, 4),
                "scores": result.scores,
            }
            rows.append(row)
            print(f"{name:10s} {condition:21s} -> {str(result.name):10s} "
                  f"score={result.score:.3f} margin={result.margin:.3f}")
    summary = {
        "database_names": recognizer.names,
        "tested": len(rows),
        "correct": sum(row["correct"] for row in rows),
        "per_condition": {
            condition: {
                "correct": sum(row["correct"] for row in rows if row["condition"] == condition),
                "total": sum(row["condition"] == condition for row in rows),
            }
            for condition in dict.fromkeys(row["condition"] for row in rows)
        },
        "rows": rows,
        "note": "Only source WAVs and deterministic alterations were used; no microphone playback was tested.",
    }
    if OUTPUT.exists():
        raise FileExistsError(f"Will not overwrite existing result: {OUTPUT}")
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SUMMARY {summary['correct']}/{summary['tested']} correct")


if __name__ == "__main__":
    main()
