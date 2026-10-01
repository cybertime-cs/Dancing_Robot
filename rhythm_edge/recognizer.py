"""Lightweight, offline rhythm matching for a directory of short WAV files.

Dependencies: Python standard library and NumPy. No librosa, DTW, network, or
pickle loading. The database stores band-wise onset envelopes, not audio.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


SAMPLE_RATE = 8000
FRAME_SIZE = 512
HOP_SIZE = 256
BANDS_HZ = ((40, 180), (180, 700), (700, 2000), (2000, 3800))
DEFAULT_WINDOW_SECONDS = 8.0
DEFAULT_STEP_SECONDS = 2.0
TEMPLATE_SECONDS = 15.0
MIN_SOURCE_SECONDS = 14.9
MAX_SOURCE_SECONDS = 17.0
DEFAULT_MIN_SCORE = 0.45
DEFAULT_MIN_MARGIN = 0.10


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read uncompressed PCM WAV as mono float32 in [-1, 1]."""
    with wave.open(str(path), "rb") as wav:
        if wav.getcomptype() != "NONE":
            raise ValueError(f"Only uncompressed PCM WAV is supported: {path}")
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    if width == 1:
        audio = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported PCM sample width ({width} bytes): {path}")
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate < SAMPLE_RATE:
        raise ValueError(f"Sample rate must be at least {SAMPLE_RATE} Hz: {path}")
    if audio.size == 0:
        raise ValueError(f"Empty WAV: {path}")
    if rate != SAMPLE_RATE:
        # A short moving average suppresses high-frequency aliases before the
        # inexpensive linear resampling. Rhythm features are below 3.8 kHz.
        width = max(1, rate // SAMPLE_RATE)
        if width > 1:
            kernel = np.full(width, 1.0 / width, dtype=np.float32)
            audio = np.convolve(audio, kernel, mode="same").astype(np.float32)
        count = max(1, round(audio.size * SAMPLE_RATE / rate))
        positions = np.arange(count, dtype=np.float64) * (rate / SAMPLE_RATE)
        audio = np.interp(positions, np.arange(audio.size), audio).astype(np.float32)
    return audio, SAMPLE_RATE


def onset_features(audio: np.ndarray) -> np.ndarray:
    """Return four 32 ms-hop onset envelopes, shape (4, frames)."""
    if audio.size < FRAME_SIZE + HOP_SIZE:
        raise ValueError("Audio is too short; at least 0.1 second is required")
    frames = np.lib.stride_tricks.sliding_window_view(audio, FRAME_SIZE)[::HOP_SIZE]
    window = np.hanning(FRAME_SIZE).astype(np.float32)
    freq = np.fft.rfftfreq(FRAME_SIZE, 1.0 / SAMPLE_RATE)
    features = []
    # Chunking bounds working memory for the 106-second choice.wav on a Pi.
    for low, high in BANDS_HZ:
        features.append(np.empty(frames.shape[0], dtype=np.float32))
    for start in range(0, len(frames), 512):
        stop = min(start + 512, len(frames))
        spectrum = np.abs(np.fft.rfft(frames[start:stop] * window, axis=1)).astype(np.float32)
        for band, (low, high) in enumerate(BANDS_HZ):
            selection = (freq >= low) & (freq < high)
            energy = np.mean(spectrum[:, selection], axis=1)
            features[band][start:stop] = np.log1p(energy * 20.0)
    out = np.stack(features)
    # Half-wave spectral-energy change retains beat timing and accent strength.
    out = np.maximum(np.diff(out, axis=1, prepend=out[:, :1]), 0.0)
    out = (np.pad(out, ((0, 0), (1, 1)), mode="edge")[:, :-2]
           + np.pad(out, ((0, 0), (1, 1)), mode="edge")[:, 1:-1]
           + np.pad(out, ((0, 0), (1, 1)), mode="edge")[:, 2:]) / 3.0
    return out.astype(np.float32)


def build_database(
    audio_dir: str | Path, database: str | Path, overwrite: bool = False
) -> tuple[list[str], list[str]]:
    source = Path(audio_dir)
    files = sorted(p for p in source.iterdir() if p.suffix.lower() == ".wav")
    if not files:
        raise ValueError(f"No WAV files in {source}")
    names = []
    skipped = []
    arrays = {}
    for path in files:
        with wave.open(str(path), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        if not MIN_SOURCE_SECONDS <= duration <= MAX_SOURCE_SECONDS:
            skipped.append(f"{path.name}: {duration:.2f}s outside {MIN_SOURCE_SECONDS}-{MAX_SOURCE_SECONDS}s")
            continue
        audio, _ = read_wav(path)
        audio = audio[:round(TEMPLATE_SECONDS * SAMPLE_RATE)]
        index = len(names)
        arrays[f"feature_{index}"] = onset_features(audio)
        names.append(path.name)
    if not names:
        raise ValueError("No approximately 15-second WAV files found")
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists() and not overwrite:
        raise FileExistsError(f"Database exists; pass --overwrite to rebuild: {database}")
    temporary = database.with_name(database.name + ".tmp.npz")
    np.savez_compressed(
        temporary,
        names=np.array(names),
        sample_rate=np.array(SAMPLE_RATE),
        frame_size=np.array(FRAME_SIZE),
        hop_size=np.array(HOP_SIZE),
        **arrays,
    )
    temporary.replace(database)
    return names, skipped


def _pearson_sliding(template: np.ndarray, query: np.ndarray) -> np.ndarray:
    """Correlation of query against every equally sized template window."""
    length = query.size
    if template.size < length:
        return np.empty(0, dtype=np.float32)
    q = query.astype(np.float64) - float(query.mean())
    q_norm = np.sqrt(np.dot(q, q))
    if q_norm < 1e-8:
        return np.zeros(template.size - length + 1, dtype=np.float32)
    t = template.astype(np.float64)
    numerator = np.correlate(t, q, mode="valid")
    sums = np.concatenate(([0.0], np.cumsum(t)))
    squares = np.concatenate(([0.0], np.cumsum(t * t)))
    sum_win = sums[length:] - sums[:-length]
    sq_win = squares[length:] - squares[:-length]
    variance = np.maximum(sq_win - sum_win * sum_win / length, 1e-12)
    return (numerator / (q_norm * np.sqrt(variance))).astype(np.float32)


def _match_window(template: np.ndarray, query: np.ndarray) -> tuple[float, int]:
    curves = [_pearson_sliding(template[b], query[b]) for b in range(query.shape[0])]
    if not curves or curves[0].size == 0:
        return -1.0, 0
    # Give all frequency bands a vote. Each curve is gain/offset invariant.
    combined = np.mean(np.stack(curves), axis=0)
    index = int(np.argmax(combined))
    return float(combined[index]), index


@dataclass(frozen=True)
class Match:
    name: str | None
    score: float
    margin: float
    offset_seconds: float
    scores: dict[str, float]


class RhythmRecognizer:
    def __init__(self, database: str | Path):
        with np.load(database, allow_pickle=False) as saved:
            if (int(saved["sample_rate"]) != SAMPLE_RATE or
                int(saved["frame_size"]) != FRAME_SIZE or
                int(saved["hop_size"]) != HOP_SIZE):
                raise ValueError("Database feature settings do not match this code")
            self.names = [str(name) for name in saved["names"]]
            self.templates = [saved[f"feature_{i}"].copy() for i in range(len(self.names))]

    def recognize_audio(
        self,
        audio: np.ndarray,
        min_score: float = DEFAULT_MIN_SCORE,
        min_margin: float = DEFAULT_MIN_MARGIN,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
    ) -> Match:
        features = onset_features(audio)
        window = min(features.shape[1], max(20, round(window_seconds * SAMPLE_RATE / HOP_SIZE)))
        step = max(1, round(DEFAULT_STEP_SECONDS * SAMPLE_RATE / HOP_SIZE))
        starts = list(range(0, features.shape[1] - window + 1, step))
        if starts[-1] != features.shape[1] - window:
            starts.append(features.shape[1] - window)
        best = {name: (-1.0, 0) for name in self.names}
        for start in starts:
            piece = features[:, start:start + window]
            for name, template in zip(self.names, self.templates):
                score, offset = _match_window(template, piece)
                if score > best[name][0]:
                    best[name] = (score, offset)
        ranked = sorted(best.items(), key=lambda item: item[1][0], reverse=True)
        name, (top, offset) = ranked[0]
        second = ranked[1][1][0] if len(ranked) > 1 else -1.0
        margin = top - second
        accepted = top >= min_score and margin >= min_margin
        return Match(
            name=name if accepted else None,
            score=top,
            margin=margin,
            offset_seconds=offset * HOP_SIZE / SAMPLE_RATE,
            scores={n: round(float(result[0]), 4) for n, result in ranked},
        )

    def recognize_wav(self, path: str | Path, **kwargs) -> Match:
        audio, _ = read_wav(path)
        return self.recognize_audio(audio, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline rhythm recognition using NumPy only")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Build compact features from training WAV files")
    build.add_argument("--audio-dir", default="rhythm_train")
    build.add_argument("--database", default="rhythm_edge/rhythm_database.npz")
    build.add_argument("--overwrite", action="store_true", help="Rebuild only the output database")
    recognize = sub.add_parser("recognize", help="Recognize a PCM WAV recording")
    recognize.add_argument("wav")
    recognize.add_argument("--database", default="rhythm_edge/rhythm_database.npz")
    recognize.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    recognize.add_argument("--min-margin", type=float, default=DEFAULT_MIN_MARGIN)
    listen = sub.add_parser("listen", help="Record 15 seconds with ALSA arecord, then recognize")
    listen.add_argument("--database", default="rhythm_edge/rhythm_database.npz")
    listen.add_argument("--device", default="default")
    listen.add_argument("--seconds", type=int, default=15)
    listen.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    listen.add_argument("--min-margin", type=float, default=DEFAULT_MIN_MARGIN)
    args = parser.parse_args()
    if args.command == "build":
        names, skipped = build_database(args.audio_dir, args.database, overwrite=args.overwrite)
        print(json.dumps({"database": args.database, "files": names, "skipped": skipped}, ensure_ascii=False))
    elif args.command == "recognize":
        result = RhythmRecognizer(args.database).recognize_wav(
            args.wav, min_score=args.min_score, min_margin=args.min_margin
        )
        print(json.dumps(result.__dict__, ensure_ascii=False))
    else:
        if args.seconds < 8:
            raise ValueError("Recording must be at least 8 seconds")
        with tempfile.TemporaryDirectory(prefix="rhythm_edge_") as directory:
            recording = Path(directory) / "recording.wav"
            subprocess.run(
                ["arecord", "-q", "-D", args.device, "-f", "S16_LE",
                 "-r", "16000", "-c", "1", "-d", str(args.seconds), str(recording)],
                check=True,
            )
            result = RhythmRecognizer(args.database).recognize_wav(
                recording, min_score=args.min_score, min_margin=args.min_margin
            )
            print(json.dumps(result.__dict__, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
