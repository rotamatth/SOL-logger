"""
Puzzle Image System
-------------------
Splits a source image into N equal horizontal strips (one per task/question).
Each strip is saved as piece_1.png, piece_2.png, etc.

Usage:
    python puzzle.py <source_image> <num_pieces> [output_dir]

Example:
    python puzzle.py static/puzzle_source.png 3 static/puzzle_pieces

Can also be imported and called programmatically:
    from puzzle import split_puzzle_image
    split_puzzle_image("source.png", 3, "static/puzzle_pieces")
"""

import os
import sys
from PIL import Image


def split_puzzle_image(source_path, num_pieces, output_dir="static/puzzle_pieces"):
    """
    Split an image into `num_pieces` equal horizontal strips.

    Args:
        source_path: Path to the source image file.
        num_pieces:  Number of pieces to split into (should match number of tasks).
        output_dir:  Directory where piece images will be saved.

    Returns:
        List of output file paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    img = Image.open(source_path)
    width, height = img.size
    piece_height = height // num_pieces

    paths = []
    for i in range(num_pieces):
        top = i * piece_height
        # Last piece gets any remaining pixels (handles rounding)
        bottom = height if i == num_pieces - 1 else (i + 1) * piece_height

        piece = img.crop((0, top, width, bottom))
        piece_path = os.path.join(output_dir, f"piece_{i + 1}.png")
        piece.save(piece_path)
        paths.append(piece_path)
        print(f"  Saved {piece_path} ({width}x{bottom - top})")

    print(f"\nDone! Split '{source_path}' into {num_pieces} pieces in '{output_dir}/'")
    return paths


def generate_placeholder(num_pieces, output_dir="static/puzzle_pieces", width=600, total_height=400):
    """
    Generate a placeholder puzzle image and split it into pieces.
    Each piece gets a distinct color so the puzzle mechanic is visually testable.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Distinct colors for each piece
    colors = [
        (66, 133, 244),   # Google Blue
        (234, 67, 53),    # Google Red
        (251, 188, 5),    # Google Yellow
        (52, 168, 83),    # Google Green
        (138, 43, 226),   # Purple
        (255, 140, 0),    # Orange
    ]

    piece_height = total_height // num_pieces

    paths = []
    for i in range(num_pieces):
        h = total_height - (num_pieces - 1) * piece_height if i == num_pieces - 1 else piece_height
        color = colors[i % len(colors)]
        piece = Image.new("RGB", (width, h), color)

        piece_path = os.path.join(output_dir, f"piece_{i + 1}.png")
        piece.save(piece_path)
        paths.append(piece_path)
        print(f"  Saved placeholder {piece_path} ({width}x{h}, color={color})")

    print(f"\nGenerated {num_pieces} placeholder pieces in '{output_dir}/'")
    return paths


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python puzzle.py <source_image|--placeholder> <num_pieces> [output_dir]")
        sys.exit(1)

    source = sys.argv[1]
    num = int(sys.argv[2])
    out = sys.argv[3] if len(sys.argv) > 3 else "static/puzzle_pieces"

    if source == "--placeholder":
        generate_placeholder(num, out)
    else:
        split_puzzle_image(source, num, out)
