#!/usr/bin/env python3
"""scripts/compile_promo_video.py
Compiles the high-fidelity promotional frames, synthesizes speech, downloads music,
and mixes them into a fully-voiced, fully-scored MP4 video using ffmpeg and macOS say.
"""

from __future__ import annotations
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = ROOT / "images"
OUTPUT_PATH = IMAGES_DIR / "ao-operator-promo.mp4"

NARRATION_TEXT = (
    "Midnight. The backlog is growing, and the release is tomorrow. You close your laptop. "
    "While you sleep, A O Operator turns your local developer machines into a secure, "
    "role-disciplined software factory. No loose prompts. No context bloat. Every task brief "
    "is bound to a strict, verified obligation ledger, executed inside isolated local sandboxes. "
    "Wake up to complete, peer-reviewed, and cryptographically verified pull requests. "
    "Safe. Accountable. Done. A O Operator. The local multi-agent software factory. "
    "Run it tonight."
)

MUSIC_URL = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"

def compile_video():
    print("[+] Starting fully-voiced promotional video compilation...")

    # Input image paths
    launch_img = IMAGES_DIR / "ao-operator-midnight-launch.png"
    seal_img = IMAGES_DIR / "ao-operator-crypto-seal.png"
    pr_img = IMAGES_DIR / "ao-operator-green-pr.png"

    # Verify input images exist
    for img in (launch_img, seal_img, pr_img):
        if not img.is_file():
            raise FileNotFoundError(f"Required frame missing: {img.name}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        clip1 = tmp / "clip1.mp4"
        clip2 = tmp / "clip2.mp4"
        clip3 = tmp / "clip3.mp4"
        slideshow_silent = tmp / "slideshow_silent.mp4"
        concat_list = tmp / "concat.txt"
        narration_audio = tmp / "narration.aiff"
        music_audio = tmp / "music.mp3"

        # 1. Synthesize Narration using macOS 'say' command
        print("[+] Synthesizing narration track using native macOS speech engine...")
        subprocess.run(["say", "-o", str(narration_audio), NARRATION_TEXT], check=True)

        # 2. Download Royalty-Free Background Music
        print("[+] Downloading royalty-free background track...")
        try:
            urllib.request.urlretrieve(MUSIC_URL, str(music_audio))
        except Exception as exc:
            print(f"[!] Direct download failed: {exc}. Trying curl backup...")
            subprocess.run(["curl", "-sSL", MUSIC_URL, "-o", str(music_audio)], check=True)

        # 3. Render Visual Scenes
        print("[+] Rendering Scene 1: The Midnight Launch (10 seconds)...")
        cmd1 = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(launch_img),
            "-t", "10",
            "-vf", "scale=1024:1024,fade=t=in:st=0:d=1.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            str(clip1)
        ]
        subprocess.run(cmd1, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print("[+] Rendering Scene 2: The Cryptographic Seal (15 seconds)...")
        cmd2 = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(seal_img),
            "-t", "15",
            "-vf", "scale=1024:1024",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            str(clip2)
        ]
        subprocess.run(cmd2, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print("[+] Rendering Scene 3: The Pull Request Victory (15 seconds)...")
        cmd3 = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(pr_img),
            "-t", "15",
            "-vf", "scale=1024:1024,fade=t=out:st=13:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            str(clip3)
        ]
        subprocess.run(cmd3, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 4. Concatenate Video Slides
        print("[+] Assembling visual slideshow...")
        concat_content = f"file '{clip1.as_posix()}'\nfile '{clip2.as_posix()}'\nfile '{clip3.as_posix()}'\n"
        concat_list.write_text(concat_content, encoding="utf-8")

        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            str(slideshow_silent)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 5. Audio Mixing and Final Trim at 40s
        print("[+] Mixing voice narration and background track into video...")
        # - We boost narration volume by 3.5x to keep it crisp.
        # - We duck the background music to 0.10x so it stays in the background.
        # - -t 40 forces the video output to cut cleanly at exactly 40 seconds.
        cmd_mix = [
            "ffmpeg", "-y",
            "-i", str(slideshow_silent),
            "-i", str(narration_audio),
            "-i", str(music_audio),
            "-filter_complex", "[1:a]volume=3.5[a1];[2:a]volume=0.10[a2];[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", "40",
            str(OUTPUT_PATH)
        ]
        subprocess.run(cmd_mix, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"[SUCCESS] Fully-voiced & scored promo compiled successfully: {OUTPUT_PATH.relative_to(ROOT)}")
    print(f"File Size: {OUTPUT_PATH.stat().st_size} bytes")

if __name__ == "__main__":
    compile_video()
