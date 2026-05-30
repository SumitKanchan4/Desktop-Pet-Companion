import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw

# Add workspace root to sys.path so we can import sprite_gen
sys.path.append(str(Path(__file__).resolve().parent))

import sprite_gen

def main():
    # 1. Generate the base frame (standing/idle with happy open mouth)
    # _mk parameters: bx, by, phase, wag, droop, blink, mouth, sx, bob
    img = sprite_gen._mk(phase=0, wag=2, droop=False, blink=False, mouth=True)
    
    # 2. Draw the tail using the exact code from sprite_gen
    d = ImageDraw.Draw(img)
    # Draw a happy, wagging tail (droop=False)
    sprite_gen._tail(d, sprite_gen.BX0, sprite_gen.BY0, wag=2, droop=False)
    
    # 3. Crop the image to Buddy's active area (remove extra empty margins)
    # The canvas is 56x48. Buddy sits roughly from x=4 to x=52, and y=8 to y=46.
    # Let's crop it tightly to 52x42 and center it slightly.
    bbox = img.getbbox()
    if bbox:
        # Expand bbox slightly to not cut off outlines/tail tips
        x0, y0, x1, y1 = bbox
        x0 = max(0, x0 - 2)
        y0 = max(0, y0 - 2)
        x1 = min(sprite_gen.FW, x1 + 2)
        y1 = min(sprite_gen.FH, y1 + 2)
        img_cropped = img.crop((x0, y0, x1, y1))
    else:
        img_cropped = img
        
    # 4. Scale up the cropped image using Nearest Neighbor to keep the pixel art crisp
    # A scale factor of 6 produces a beautiful high-resolution image (~300px wide)
    w, h = img_cropped.size
    scale_factor = 6
    img_scaled = img_cropped.resize((w * scale_factor, h * scale_factor), Image.Resampling.NEAREST)
    
    # 5. Create assets/ directory if it doesn't exist and save
    assets_dir = Path(__file__).resolve().parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    preview_path = assets_dir / "preview.png"
    
    # Save as PNG
    img_scaled.save(preview_path)
    print(f"Generated preview image at {preview_path}")

if __name__ == "__main__":
    main()
