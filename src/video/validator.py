import json
import subprocess

import structlog

logger = structlog.get_logger()


def validate_video(video_path: str) -> dict:
    """Validate a video file using ffprobe. Returns metadata dict."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        logger.error("ffprobe_failed", path=video_path, stderr=result.stderr[:500])
        raise RuntimeError(f"ffprobe validation failed: {result.stderr[:500]}")

    metadata = json.loads(result.stdout)
    fmt = metadata.get("format", {})
    streams = metadata.get("streams", [])

    video_stream = next((s for s in streams if s["codec_type"] == "video"), None)
    audio_stream = next((s for s in streams if s["codec_type"] == "audio"), None)

    info = {
        "duration_seconds": float(fmt.get("duration", 0)),
        "size_bytes": int(fmt.get("size", 0)),
        "format_name": fmt.get("format_name"),
        "video_codec": video_stream["codec_name"] if video_stream else None,
        "width": int(video_stream["width"]) if video_stream else None,
        "height": int(video_stream["height"]) if video_stream else None,
        "fps": _parse_fps(video_stream.get("r_frame_rate", "0/1")) if video_stream else None,
        "audio_codec": audio_stream["codec_name"] if audio_stream else None,
    }

    logger.info("video_validated", path=video_path, **info)
    return info


def check_compatibility(intro_path: str, main_path: str) -> tuple[bool, str]:
    """Check whether two videos are compatible for stream-copy concat.

    Returns (compatible, reason).
    """
    intro = validate_video(intro_path)
    main = validate_video(main_path)

    if intro["video_codec"] != main["video_codec"]:
        return False, f"Video codec mismatch: {intro['video_codec']} vs {main['video_codec']}"
    if intro["width"] != main["width"] or intro["height"] != main["height"]:
        return False, (
            f"Resolution mismatch: {intro['width']}x{intro['height']} "
            f"vs {main['width']}x{main['height']}"
        )
    if intro["audio_codec"] != main["audio_codec"]:
        return False, f"Audio codec mismatch: {intro['audio_codec']} vs {main['audio_codec']}"

    return True, "compatible"


def _parse_fps(r_frame_rate: str) -> float | None:
    try:
        num, den = r_frame_rate.split("/")
        return round(int(num) / int(den), 2) if int(den) else None
    except (ValueError, ZeroDivisionError):
        return None
