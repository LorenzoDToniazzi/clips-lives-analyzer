from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


INITIAL_PROMPT = (
    "Live brasileira de League of Legends. Vocabulário provável: build, item, runa, "
    "matchup, ciência, off-meta, X1, Arena, Draft Lab, Laboratório, kill, dive, "
    "gank, mid, top, jungle, ADC, suporte, flash, ignite, ultimate, stack, proc."
)


def emit(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def run_worker(
    audio_path: Path,
    *,
    model_name: str,
    device: str,
    compute_type: str,
    language: str,
) -> int:
    try:
        emit("model_loading", device=device, model=model_name)
        from faster_whisper import WhisperModel

        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        emit("model_loaded", device=device, model=model_name)

        generator, info = model.transcribe(
            str(audio_path),
            language=None if language == "auto" else language,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 900},
            condition_on_previous_text=True,
            initial_prompt=INITIAL_PROMPT,
        )
        emit("transcription_started")
        for segment in generator:
            emit(
                "segment",
                start=float(segment.start),
                end=float(segment.end),
                text=str(segment.text).strip(),
                words=[
                    {
                        "start": float(word.start),
                        "end": float(word.end),
                        "text": str(word.word),
                        "probability": (
                            float(word.probability)
                            if word.probability is not None
                            else None
                        ),
                    }
                    for word in (segment.words or [])
                ],
            )
        emit(
            "done",
            language=str(info.language),
            language_probability=float(info.language_probability),
        )
        return 0
    except Exception as exc:
        emit(
            "error",
            error_type=type(exc).__name__,
            message=str(exc),
            traceback=traceback.format_exc()[-6000:],
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", choices=("cuda", "cpu"), required=True)
    parser.add_argument("--compute-type", required=True)
    parser.add_argument("--language", default="pt")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(
        run_worker(
            Path(args.audio),
            model_name=args.model,
            device=args.device,
            compute_type=args.compute_type,
            language=args.language,
        )
    )


if __name__ == "__main__":
    main()
