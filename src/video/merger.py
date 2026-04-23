import os
import subprocess
import tempfile

import structlog

logger = structlog.get_logger()


def merge_videos(intro_path: str, main_path: str, output_path: str) -> dict:
    """Merge intro and main videos using FFmpeg concat demuxer (lossless).

    Both inputs must share the same codec, resolution, and frame rate for
    stream-copy to work correctly.  Returns metadata about the merged file.
    """
    fd, filelist_path = tempfile.mkstemp(suffix=".txt", prefix="ffmpeg_concat_")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(f"file '{intro_path}'\n")
            f.write(f"file '{main_path}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", filelist_path,
            "-c", "copy",
            output_path,
        ]

        logger.info("ffmpeg_merge_start", intro=intro_path, main=main_path, output=output_path)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            logger.error("ffmpeg_merge_failed", stderr=result.stderr[:2000])
            raise RuntimeError(f"FFmpeg merge failed: {result.stderr[:500]}")

        size_bytes = os.path.getsize(output_path)
        logger.info("ffmpeg_merge_complete", output=output_path, size_bytes=size_bytes)

        return {"output_path": output_path, "size_bytes": size_bytes}
    finally:
        if os.path.exists(filelist_path):
            os.remove(filelist_path)


def merge_videos_reencode(intro_path: str, main_path: str, output_path: str) -> dict:
    """Merge with re-encoding -- use when inputs have different codecs/resolutions."""
    cmd = [
        "ffmpeg", "-y",
        "-i", intro_path,
        "-i", main_path,
        "-filter_complex",
        "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[outv][outa]",
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]

    logger.info("ffmpeg_reencode_start", intro=intro_path, main=main_path, output=output_path)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    if result.returncode != 0:
        logger.error("ffmpeg_reencode_failed", stderr=result.stderr[:2000])
        raise RuntimeError(f"FFmpeg re-encode failed: {result.stderr[:500]}")

    size_bytes = os.path.getsize(output_path)
    logger.info("ffmpeg_reencode_complete", output=output_path, size_bytes=size_bytes)

    return {"output_path": output_path, "size_bytes": size_bytes}
