import os
import shutil
from huggingface_hub import snapshot_download

def prepare_dataset(dest_dir: str = "dataset"):
    print("[*] Downloading lightweight reCAPTCHA classification dataset (~15MB)...", flush=True)
    repo_path = snapshot_download(
        repo_id="verytuffcat/recaptcha-dataset",
        repo_type="dataset",
        allow_patterns=["data/train/*", "data/test/*"]
    )
    
    print(f"[+] Downloaded to HF cache: {repo_path}", flush=True)
    os.makedirs(dest_dir, exist_ok=True)
    
    # Organize into clean class folders in dest_dir
    src_train = os.path.join(repo_path, "data", "train")
    if os.path.exists(src_train):
        for class_name in os.listdir(src_train):
            src_class_dir = os.path.join(src_train, class_name)
            if not os.path.isdir(src_class_dir):
                continue
            
            # Normalize class names (e.g., 'stair' -> 'stairs', 'traffic light' -> 'traffic_light')
            target_name = class_name.lower().replace(" ", "_")
            if target_name == "stair": target_name = "stairs"
            
            target_class_dir = os.path.join(dest_dir, target_name)
            os.makedirs(target_class_dir, exist_ok=True)
            
            count = 0
            for fname in os.listdir(src_class_dir):
                if fname.lower().endswith(('.png', '.jpg', '.jpeg')):
                    src_f = os.path.join(src_class_dir, fname)
                    dst_f = os.path.join(target_class_dir, fname)
                    if not os.path.exists(dst_f):
                        shutil.copy2(src_f, dst_f)
                        count += 1
            print(f"  [+] Loaded {count} images for class '{target_name}'", flush=True)

    total_images = sum([len(files) for r, d, files in os.walk(dest_dir)])
    print(f"[+] Dataset ready in '{dest_dir}': {total_images} total images across {len(os.listdir(dest_dir))} classes.", flush=True)

if __name__ == "__main__":
    prepare_dataset()
