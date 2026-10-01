"""Repeatable offline check using only WAVs from a supplied directory.

This is an in-sample engineering check. It is not a microphone-field accuracy
estimate because snippets come from the same files used for the database.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from recognizer import RhythmRecognizer, read_wav, SAMPLE_RATE


def cases(audio: np.ndarray, name: str):
    duration = audio.size / SAMPLE_RATE
    clip = min(15.0, duration)
    for start in [0.0]:
        start_frame = round(start * SAMPLE_RATE)
        part = audio[start_frame:start_frame + round(clip * SAMPLE_RATE)].copy()
        yield f"{name}@{start:.1f}s clean", part
        # Simulated level change, moderate background noise, and a delayed
        # start. All source music still comes from the supplied WAV files.
        rng = np.random.default_rng(20260927 + start_frame)
        noise = rng.normal(0.0, max(float(np.std(part)) * 0.04, 1e-5), part.size)
        altered = np.concatenate((np.zeros(round(0.35 * SAMPLE_RATE), dtype=np.float32),
                                  (part * 0.65 + noise).astype(np.float32)))
        yield f"{name}@{start:.1f}s altered", altered
        # Slight playback-rate change is a stronger check than gain/noise.
        speed = 1.02
        positions = np.arange(round(part.size / speed)) * speed
        changed = np.interp(positions, np.arange(part.size), part).astype(np.float32)
        yield f"{name}@{start:.1f}s speed+2%", changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-dir", default="rhythm_train")
    parser.add_argument("--database", default="rhythm_edge/rhythm_database.npz")
    args = parser.parse_args()
    recognizer = RhythmRecognizer(args.database)
    total = correct = rejected = 0
    times = []
    for name in recognizer.names:
        path = Path(args.audio_dir) / name
        audio, _ = read_wav(path)
        audio = audio[:round(15.0 * SAMPLE_RATE)]
        for label, sample in cases(audio, path.name):
            before = time.perf_counter()
            result = recognizer.recognize_audio(sample)
            times.append(time.perf_counter() - before)
            total += 1
            correct += result.name == path.name
            rejected += result.name is None
            print(f"{label:35s} -> {str(result.name):10s} score={result.score:.3f} "
                  f"margin={result.margin:.3f} time={times[-1]:.3f}s")
    print(f"SUMMARY correct={correct}/{total} rejected={rejected} "
          f"mean_time={np.mean(times):.3f}s max_time={max(times):.3f}s")
    print("HELD-OUT CLASS CHECK (each source removed from the database in memory)")
    for name in recognizer.names:
        path = Path(args.audio_dir) / name
        audio, _ = read_wav(path)
        subset = object.__new__(RhythmRecognizer)
        subset.names = [n for n in recognizer.names if n != name]
        subset.templates = [t for n, t in zip(recognizer.names, recognizer.templates) if n != name]
        result = subset.recognize_audio(audio[:round(15.0 * SAMPLE_RATE)])
        print(f"{name:10s} -> {str(result.name):10s} score={result.score:.3f} "
              f"margin={result.margin:.3f}")


if __name__ == "__main__":
    main()
