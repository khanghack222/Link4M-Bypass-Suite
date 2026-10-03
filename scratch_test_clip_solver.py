import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import numpy as np

print("Testing CLIP ViT-B/32 Zero-Shot reCAPTCHA Classifier...", flush=True)
device = "cuda" if torch.cuda.is_available() else "cpu"
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

def solve_grid_with_clip(img: Image.Image, instruction: str, total_tiles: int = 9) -> list[int]:
    grid_n = 4 if total_tiles == 16 else 3
    w, h = img.size
    tw, th = w // grid_n, h // grid_n
    
    # Extract clean target noun
    inst_lower = instruction.lower()
    target = "object"
    for cand in ["bicycles", "bicycle", "motorcycles", "motorcycle", "buses", "bus", "cars", "car", 
                 "traffic lights", "traffic light", "fire hydrants", "fire hydrant", 
                 "crosswalks", "crosswalk", "pedestrian crossing", "bridges", "bridge", 
                 "stairs", "chimneys", "chimney", "tractors", "tractor", "palm trees", "boats", "boat"]:
        if cand in inst_lower:
            target = cand
            break
            
    print(f"  [CLIP] Target parsed: '{target}' on {grid_n}x{grid_n} grid", flush=True)
    
    tiles = []
    for r in range(grid_n):
        for c in range(grid_n):
            tile = img.crop((c * tw, r * th, (c + 1) * tw, (r + 1) * th))
            tiles.append(tile)
            
    labels = [
        f"a photo containing a {target}",
        f"a photo of an empty street, background or sky without {target}"
    ]
    
    inputs = processor(text=labels, images=tiles, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        outputs = model(**inputs)
        logits_per_image = outputs.logits_per_image # shape: (num_tiles, 2)
        probs = logits_per_image.softmax(dim=1).cpu().numpy()
        
    matched = []
    for idx, p in enumerate(probs):
        tile_num = idx + 1
        conf = float(p[0])
        print(f"    Tile {tile_num}: {target} conf = {conf:.3f}", flush=True)
        # Threshold: if target prob > 0.50
        if conf >= 0.55:
            matched.append(tile_num)
            
    return matched

# Test on a dummy image
dummy = Image.new("RGB", (400, 400), color=(128, 128, 128))
res = solve_grid_with_clip(dummy, "Select all images with bicycles", 9)
print("Dummy test result (should be empty):", res, flush=True)
