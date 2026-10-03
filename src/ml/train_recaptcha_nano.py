"""
Lightweight Training & ONNX Export Pipeline for Pure ONNX Nano reCAPTCHA Classifier
- Architecture: MobileNetV3-Small (Pretrained backbone, replaces head with 14 classes)
- Resource Footprint: Low CPU threads (2 max), batch size 16/32, RAM < 400MB
- Output: models/recaptcha_nano.onnx (< 4MB) & quantized INT8 (< 2MB)
"""

import os
import sys
import argparse
import time

def set_low_resource_env(max_threads: int = 2):
    """Restricts torch and openmp threads so CPU stays cool for other tasks."""
    os.environ["OMP_NUM_THREADS"] = str(max_threads)
    os.environ["MKL_NUM_THREADS"] = str(max_threads)
    try:
        import torch
        torch.set_num_threads(max_threads)
        torch.set_num_interop_threads(max_threads)
    except Exception:
        pass

def train_and_export(data_dir: str, epochs: int = 5, batch_size: int = 16, lr: float = 0.001, output_onnx: str = "models/recaptcha_nano.onnx"):
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
    from torchvision import datasets, transforms, models

    set_low_resource_env(max_threads=2)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[*] Training on device: {device} (Max CPU Threads: 2, Batch Size: {batch_size})")

    os.makedirs(os.path.dirname(output_onnx) or ".", exist_ok=True)

    # 1. Data Transforms (Optimized for 128x128 tiles)
    train_transform = transforms.Compose([
        transforms.Resize((128, 128)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(degrees=10),
        transforms.ColorJitter(brightness=0.2, contrast=0.2),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    if not os.path.exists(data_dir) or len(os.listdir(data_dir)) == 0:
        print(f"[!] Data directory '{data_dir}' is empty or does not exist.")
        print("[*] Generating synthetic placeholder dataset for architecture compilation test...")
        os.makedirs(os.path.join(data_dir, "bicycle"), exist_ok=True)
        os.makedirs(os.path.join(data_dir, "car"), exist_ok=True)
        from PIL import Image
        for i in range(10):
            Image.new("RGB", (128, 128), color=(i*20, 100, 50)).save(os.path.join(data_dir, "bicycle", f"demo_{i}.jpg"))
            Image.new("RGB", (128, 128), color=(50, 100, i*20)).save(os.path.join(data_dir, "car", f"demo_{i}.jpg"))

    dataset = datasets.ImageFolder(root=data_dir, transform=train_transform)
    num_classes = len(dataset.classes)
    print(f"[+] Loaded dataset: {len(dataset)} images across {num_classes} classes: {dataset.classes}")

    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)

    # 2. Build MobileNetV3-Small
    print("[*] Initializing MobileNetV3-Small backbone...")
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    
    # Replace classifier head
    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, max(num_classes, 14))
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    # 3. Training Loop with Low CPU Priority
    model.train()
    for ep in range(epochs):
        t0 = time.time()
        running_loss = 0.0
        correct = 0
        total = 0
        for imgs, targets in loader:
            imgs, targets = imgs.to(device), targets.to(device)
            optimizer.zero_grad()
            outputs = model(imgs)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * imgs.size(0)
            _, preds = torch.max(outputs, 1)
            correct += (preds == targets).sum().item()
            total += targets.size(0)
            
            # Cooperative yield for host CPU
            time.sleep(0.01)

        ep_loss = running_loss / max(total, 1)
        ep_acc = (correct / max(total, 1)) * 100
        print(f"[Epoch {ep+1}/{epochs}] Loss: {ep_loss:.4f} | Acc: {ep_acc:.1f}% | Time: {time.time()-t0:.1f}s", flush=True)

    # 4. Export directly to ONNX (< 4MB)
    print(f"[*] Exporting trained model to ONNX: {output_onnx}...")
    model.eval()
    dummy_input = torch.randn(1, 3, 128, 128, device=device)
    try:
        torch.onnx.export(
            model,
            dummy_input,
            output_onnx,
            export_params=True,
            opset_version=14,
            do_constant_folding=True,
            input_names=['images'],
            output_names=['output0'],
            dynamic_axes={'images': {0: 'batch'}, 'output0': {0: 'batch'}},
            dynamo=False
        )
    except TypeError:
        torch.onnx.export(
            model,
            dummy_input,
            output_onnx,
            export_params=True,
            opset_version=14,
            do_constant_folding=True,
            input_names=['images'],
            output_names=['output0'],
            dynamic_axes={'images': {0: 'batch'}, 'output0': {0: 'batch'}}
        )
    
    file_size_mb = os.path.getsize(output_onnx) / (1024 * 1024)
    print(f"[+] Pure ONNX Nano model exported successfully: {output_onnx} ({file_size_mb:.2f} MB)")

    # 5. Optional INT8 Quantization (< 2MB)
    try:
        import onnxruntime
        from onnxruntime.quantization import quantize_dynamic, QuantType
        int8_onnx = output_onnx.replace(".onnx", "_int8.onnx")
        print(f"[*] Compressing model to INT8: {int8_onnx}...")
        quantize_dynamic(output_onnx, int8_onnx, weight_type=QuantType.QUInt8)
        int8_size_mb = os.path.getsize(int8_onnx) / (1024 * 1024)
        print(f"[+] INT8 Quantized Model ready: {int8_onnx} ({int8_size_mb:.2f} MB)")
    except Exception as e:
        print(f"[*] INT8 Quantization skipped ({e}). FP32 ONNX model is already lightweight.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="dataset", help="Path to dataset folder")
    parser.add_argument("--epochs", type=int, default=5, help="Number of epochs")
    parser.add_argument("--batch_size", type=int, default=16, help="Batch size (16 for low RAM)")
    parser.add_argument("--output", type=str, default="models/recaptcha_nano.onnx", help="Output ONNX path")
    args = parser.parse_args()

    train_and_export(
        data_dir=args.data_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        output_onnx=args.output
    )
