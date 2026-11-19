"""Video processing with ffmpeg (optional dependency, installed in the Docker image)."""
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import HTTPException


async def _run(*args: str, timeout: int = 180) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(413, "That video took too long to process. Try a shorter one.")
    return proc.returncode, out, err


async def process_video(raw: bytes, ext: str, max_seconds: int) -> tuple[bytes, str, bytes | None, int | None]:
    """Returns (video bytes, extension, poster image bytes or None, duration in seconds or None)."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return raw, ext, None, None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in.{ext}"
        src.write_bytes(raw)
        code, out, _ = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "json", str(src), timeout=30)
        if code != 0:
            raise HTTPException(415, "That file isn't a readable video.")
        try:
            duration = float(json.loads(out)["format"]["duration"])
        except (KeyError, ValueError, TypeError):
            raise HTTPException(415, "That file isn't a readable video.")
        if duration > max_seconds + 0.5:
            raise HTTPException(400, f"Videos can be up to {max_seconds} seconds.")
        dst = Path(tmp) / "out.mp4"
        code, _, _ = await _run(
            "ffmpeg", "-y", "-v", "error", "-i", str(src), "-map_metadata", "-1",
            "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dst))
        if code != 0 or not dst.is_file():
            raise HTTPException(415, "That video couldn't be processed.")
        poster = Path(tmp) / "poster.jpg"
        await _run("ffmpeg", "-y", "-v", "error", "-ss", str(min(1.0, duration / 2)), "-i", str(dst),
                   "-frames:v", "1", "-q:v", "4", str(poster), timeout=30)
        return dst.read_bytes(), "mp4", poster.read_bytes() if poster.is_file() else None, int(round(duration))
