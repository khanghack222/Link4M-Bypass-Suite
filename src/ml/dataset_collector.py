import os
import re
import io
import time
from typing import Optional
from PIL import Image

CLASSES = [
    'bicycle', 'bridge', 'bus', 'car', 'chimney',
    'crosswalk', 'hydrant', 'motorcycle', 'mountain', 'other',
    'palm', 'stairs', 'tractor', 'traffic_light'
]

CLASS_TO_IDX = {cls_name: idx for idx, cls_name in enumerate(CLASSES)}

INSTRUCTION_CLASS_MAP = {
    'bicycle': 'bicycle', 'bicycles': 'bicycle', 'bike': 'bicycle',
    'bridge': 'bridge', 'bridges': 'bridge',
    'bus': 'bus', 'buses': 'bus',
    'car': 'car', 'cars': 'car', 'automobile': 'car', 'taxi': 'car',
    'chimney': 'chimney', 'chimneys': 'chimney',
    'crosswalk': 'crosswalk', 'crosswalks': 'crosswalk', 'pedestrian': 'crosswalk',
    'hydrant': 'hydrant', 'hydrants': 'hydrant', 'fire hydrant': 'hydrant',
    'motorcycle': 'motorcycle', 'motorcycles': 'motorcycle', 'motorbike': 'motorcycle',
    'mountain': 'mountain', 'mountains': 'mountain', 'hill': 'mountain',
    'palm': 'palm', 'palm tree': 'palm', 'palm trees': 'palm',
    'stair': 'stairs', 'stairs': 'stairs',
    'tractor': 'tractor', 'tractors': 'tractor',
    'traffic light': 'traffic_light', 'traffic lights': 'traffic_light'
}

def extract_class_from_instruction(instruction: str) -> Optional[str]:
    inst_lower = instruction.lower()
    for kw, cls in sorted(INSTRUCTION_CLASS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if kw in inst_lower:
            return cls
    return None

class DatasetCollector:
    """
    Saves cropped tiles from live reCAPTCHA challenges directly into class folders
    for ongoing training/fine-tuning.
    """
    def __init__(self, data_dir: str = "dataset"):
        self.data_dir = data_dir
        for c in CLASSES:
            os.makedirs(os.path.join(self.data_dir, c), exist_ok=True)

    def save_challenge_tiles(self, img_bytes: bytes, instruction: str, matched_tiles: list, total_tiles: int = 9):
        target_cls = extract_class_from_instruction(instruction)
        if not target_cls:
            return

        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            w, h = img.size
            grid_n = 4 if total_tiles == 16 else 3
            tw, th = w // grid_n, h // grid_n
            ts = int(time.time() * 1000)

            tile_num = 1
            for r in range(grid_n):
                for c in range(grid_n):
                    tile = img.crop((c * tw, r * th, (c + 1) * tw, (r + 1) * th))
                    # If this tile was matched by solver, save under target_cls; otherwise save under 'other'
                    is_positive = tile_num in matched_tiles
                    folder = target_cls if is_positive else 'other'
                    out_path = os.path.join(self.data_dir, folder, f"{target_cls}_{ts}_{tile_num}.jpg")
                    tile.save(out_path, quality=85)
                    tile_num += 1
        except Exception:
            pass
