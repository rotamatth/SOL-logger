"""Prepare the review animations and their stills from the supplied MP4s.

The supplied clips show each picture small and off-centre on a black 4K frame, and browsers
cannot key out black reliably on tablets. This writes clips cropped to the picture on the white
of the page, plus a still of the last frame, so a clip looks the same on every device. The sound
track is dropped because the supplied ones are silent.

Needs numpy, scipy, Pillow and imageio-ffmpeg, which are not part of the application:
    python tools/prepare_review_media.py SOURCE_DIR static/videos/review static/images/review
"""
import argparse
from pathlib import Path
import subprocess

import imageio_ffmpeg
import numpy as np
from PIL import Image
from scipy import ndimage

SIZE = (3840, 2160)
SCALE = 2  # 4K is far more than a tablet shows; decode at half size.
DARK = 14  # Below this in every channel a pixel may be background.
SMALL_HOLE = 0.002  # Dark areas enclosed by the picture and smaller than this share stay, as outlines and pupils.
MARGIN = 12
SPECK = 500  # Bright areas smaller than this many pixels at decoding size are noise.
SOFT = {"Orecchio_02": (170, 0.40)}  # By source clip: the sound waves, in the left of the frame, fade out over the black.
MAX_HEIGHT = 840
# Output name, source clip, still. Orecchio 02 and 03 are swapped in the supplied files:
# the Figma and the recap picture go child, inside of the ear, animals.
CLIPS = (("Orecchio_01", "Orecchio_01", "ear-1"), ("Orecchio_02", "Orecchio_03", "ear-2"), ("Orecchio_03", "Orecchio_02", "ear-3"),
         ("Spazio_01", "Spazio_01", "space-1"), ("Spazio_02", "Spazio_02", "space-2"), ("Spazio_03", "Spazio_03", "space-3"))


def frames(path):
    width, height = SIZE[0] // SCALE, SIZE[1] // SCALE
    process = subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(path), "-vf", f"scale={width}:{height}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = width * height * 3
    while chunk := process.stdout.read(size):
        yield np.frombuffer(chunk, np.uint8).reshape(height, width, 3)
    process.wait()


def picture_mask(frame):
    """The picture without the specks of compression noise scattered over the black."""
    labels, _ = ndimage.label(frame.max(axis=2) >= 28)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= SPECK
    keep[0] = False
    return keep[labels]


def on_white(frame, soft):
    """Black that belongs to the background becomes white, with soft edges. Dark parts of the picture stay."""
    picture = ndimage.binary_dilation(picture_mask(frame), iterations=4)
    dark = (frame.max(axis=2) < DARK) | ~picture
    labels, _ = ndimage.label(dark)
    sizes = np.bincount(labels.ravel())
    edge = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    background = np.zeros(sizes.size, bool)
    background[edge] = True
    background[sizes > SMALL_HOLE * frame.shape[0] * frame.shape[1]] = True
    background[0] = False
    mask = background[labels]
    # The art was drawn over black, so near the background its colour is scaled by its coverage.
    near = ndimage.binary_dilation(mask, iterations=2)
    alpha = np.clip(frame.sum(axis=2) * 3 / 255 - 0.08, 0, 1)[..., None]
    alpha = np.where(near[..., None], alpha, 1.0)
    if soft:
        # Shapes that fade out over the black: everything this dim and joined to the background.
        level, share = soft
        dim = frame.max(axis=2) < level
        dim[:, int(frame.shape[1] * share):] = False
        labels, _ = ndimage.label(dim | mask)
        joined = np.isin(labels, np.unique(labels[mask])) & dim & (labels > 0)
        alpha = np.where(joined[..., None], np.clip(frame.max(axis=2) / level, 0, 1)[..., None], alpha)
    alpha = np.where(mask[..., None], 0.0, alpha)
    return np.clip(frame + (1 - alpha) * 255, 0, 255).astype(np.uint8)


def art_box(path):
    box = None
    for frame in frames(path):
        picture = picture_mask(frame)
        rows = np.flatnonzero(picture.any(axis=1))
        columns = np.flatnonzero(picture.any(axis=0))
        if rows.size:
            found = (columns[0], rows[0], columns[-1], rows[-1])
            box = found if box is None else (min(box[0], found[0]), min(box[1], found[1]), max(box[2], found[2]), max(box[3], found[3]))
    height, width = SIZE[1] // SCALE, SIZE[0] // SCALE
    return (max(box[0] - MARGIN, 0), max(box[1] - MARGIN, 0), min(box[2] + MARGIN, width), min(box[3] + MARGIN, height))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("videos", type=Path)
    parser.add_argument("stills", type=Path)
    args = parser.parse_args()
    for name, source, still in CLIPS:
        left, top, right, bottom = art_box(args.source / f"{source}.mp4")
        width, height = right - left, bottom - top
        out_h = min(height, MAX_HEIGHT // SCALE * SCALE) // 2 * 2
        out_w = int(width * out_h / height) // 2 * 2
        writer = subprocess.Popen(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{width // 2 * 2}x{height // 2 * 2}", "-r", "30", "-i", "-", "-vf", f"scale={out_w}:{out_h},format=yuv420p,lutyuv=y='if(gt(val,226),235,val)':u='if(between(val,124,132),128,val)':v='if(between(val,124,132),128,val)'",
             "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow",
             "-color_range", "tv", "-colorspace", "bt709", "-movflags", "+faststart", "-an", str(args.videos / f"{name}.mp4")],
            stdin=subprocess.PIPE)
        last = None
        for frame in frames(args.source / f"{source}.mp4"):
            last = on_white(frame[top:top + height // 2 * 2, left:left + width // 2 * 2], SOFT.get(source))
            writer.stdin.write(last.tobytes())
        writer.stdin.close()
        writer.wait()
        Image.fromarray(last).resize((out_w, out_h), Image.LANCZOS).save(args.stills / f"{still}.webp", quality=88, method=6)
        print(name, "from", source, f"{out_w}x{out_h}", "ratio", round(out_w / out_h, 3))


if __name__ == "__main__":
    main()
