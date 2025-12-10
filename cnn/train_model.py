#!/usr/bin/env python3
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from pathlib import Path
from PIL import Image
import re
import random
import glob
import os
import argparse

# Configuration
BATCH_SIZE = 16
EPOCHS = 100 
LEARNING_RATE = 0.001
IMAGE_WIDTH = 120  # Upscaled width (original 40 * 3)
IMAGE_HEIGHT = 33  # Upscaled height (original 11 * 3)
# We upscale slightly to help CNN features, though 40x11 is tiny.
# Let's stick to a reasonable size. 
# Original images are tiny: ~40x12. 
# EasyOCR upscaled by 8x. 
# Let's try 3x upscale for training to keep it small but visible. 
# Width ~120, Height ~33.

class CaptchaDataset(Dataset):
    def __init__(self, image_paths, transform=None):
        self.image_paths = image_paths
        self.transform = transform

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        path = self.image_paths[idx]
        image = Image.open(path).convert('L') # Grayscale
        from PIL import ImageOps
        image = ImageOps.invert(image) # Invert: Black text becomes White (high value)
        
        # Extract label
        # Matches last 4 digits in filename (e.g. vc0001_4035.bmp -> 4035)
        matches = re.findall(r'(\d{4})', Path(path).stem)
        if matches:
            label_str = matches[-1]
        else:
            # Should not happen if filtered correctly
            print(f"Warning: No label found for {path}, skipping (returning 0000)")
            label_str = "0000"

        # Convert label to tensor (4 integers)
        label_tensor = torch.tensor([int(c) for c in label_str], dtype=torch.long)

        if self.transform:
            image = self.transform(image)

        return image, label_tensor

class SimpleCNN(nn.Module):
    def __init__(self):
        super(SimpleCNN, self).__init__()
        
        # Input: 1 x H x W
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(32)
        self.pool1 = nn.MaxPool2d(2, 2)
        
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(64)
        self.pool2 = nn.MaxPool2d(2, 2)
        
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(128)
        self.pool3 = nn.MaxPool2d(2, 2)
        
        # Calculate flatten size dynamically or pre-calculate
        # 120x33 -> 60x16 -> 30x8 -> 15x4
        self.fc1 = nn.Linear(128 * 15 * 4, 256) 
        self.dropout = nn.Dropout(0.5)
        
        # 4 output heads, one for each digit (0-9)
        self.fc_digit1 = nn.Linear(256, 10)
        self.fc_digit2 = nn.Linear(256, 10)
        self.fc_digit3 = nn.Linear(256, 10)
        self.fc_digit4 = nn.Linear(256, 10)
        
        self.relu = nn.ReLU()

    def forward(self, x):
        x = self.pool1(self.relu(self.bn1(self.conv1(x))))
        x = self.pool2(self.relu(self.bn2(self.conv2(x))))
        x = self.pool3(self.relu(self.bn3(self.conv3(x))))
        
        x = x.view(x.size(0), -1)
        x = self.relu(self.fc1(x))
        # x = self.dropout(x)
        
        d1 = self.fc_digit1(x)
        d2 = self.fc_digit2(x)
        d3 = self.fc_digit3(x)
        d4 = self.fc_digit4(x)
        
        return d1, d2, d3, d4

import time

def train():
    parser = argparse.ArgumentParser(description="Train Captcha CNN")
    parser.add_argument('folders', nargs='+', help='List of folders to look for training data (e.g. captchas test_verification)')
    parser.add_argument('--device', type=str, default='auto', choices=['auto', 'cpu', 'cuda', 'mps'], help='Device to train on (auto, cpu, cuda, mps)')
    parser.add_argument('--epochs', type=int, default=300, help='Number of epochs to train (default: 300)')
    args = parser.parse_args()

    # 1. Collect Data
    # Collect all .bmp files from known directories
    files = []
    for folder in args.folders:
        path = Path(folder)
        if not path.exists():
            print(f"Warning: Folder {folder} does not exist.")
            continue
        # Support recursive or just top level? glob is simple.
        # Original was glob('folder/*.bmp').
        found = list(path.glob('*.bmp'))
        print(f"Found {len(found)} images in {folder}")
        files.extend(found)
    
    # Filter valid files (must have 4 digits in filename)
    valid_files = []
    for f in files:
        # Resolve to string for regex checks if needed, or keep as Path
        if re.search(r'\d{4}', f.stem):
            valid_files.append(str(f)) # Dataset expects string or Path? Dataset init takes 'image_paths'.
            
    files = valid_files # Dataset handles both strings and paths usually, but let's stick to consistent type.

    if not files:
        print("Error: No training data found.")
        return

    print(f"Found {len(files)} valid images for training.")

    # 2. Transforms & Augmentation
    # 2. Transforms & Augmentation
    train_transform = transforms.Compose([
        transforms.Resize((IMAGE_HEIGHT, IMAGE_WIDTH)),
        transforms.RandomRotation(5, fill=0), # Fill with black (bg color after inversion)
        transforms.ColorJitter(brightness=0.2, contrast=0.2), 
        transforms.ToTensor(),
    ])
    
    # 3. DataLoader
    dataset = CaptchaDataset(files, transform=train_transform)
    # Explicitly set pin_memory=False to avoid MPS warning on macOS
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, pin_memory=False)
    
    # Debug: Print first few labels
    print("Debug: First 5 labels in dataset:")
    for i in range(min(5, len(dataset))):
        _, lbl = dataset[i]
        print(f"  {files[i]} -> {lbl.tolist()}")
    
    # 4. Model Setup
    if args.device == 'auto':
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    
    print(f"Training on device: {device}")
    
    model = SimpleCNN().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    
    # 5. Training Loop
    print("\nStarting Training...")
    # Increase Epochs for small dataset convergence
    TOTAL_EPOCHS = args.epochs
    
    start_time = time.time()
    
    for epoch in range(TOTAL_EPOCHS):
        epoch_start = time.time()
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        
        for images, labels in dataloader:
            images = images.to(device)
            labels = labels.to(device)
            
            optimizer.zero_grad()
            
            d1, d2, d3, d4 = model(images)
            
            loss1 = criterion(d1, labels[:, 0])
            loss2 = criterion(d2, labels[:, 1])
            loss3 = criterion(d3, labels[:, 2])
            loss4 = criterion(d4, labels[:, 3])
            loss = loss1 + loss2 + loss3 + loss4
            
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            
            # Accuracy
            p1 = d1.argmax(1)
            p2 = d2.argmax(1)
            p3 = d3.argmax(1)
            p4 = d4.argmax(1)
            
            # Check if all 4 digits match
            is_correct = (p1 == labels[:, 0]) & (p2 == labels[:, 1]) & \
                         (p3 == labels[:, 2]) & (p4 == labels[:, 3])
            correct += is_correct.sum().item()
            total += labels.size(0)
            
        epoch_acc = 100 * correct / total
        epoch_duration = time.time() - epoch_start
        
        if (epoch + 1) % 20 == 0 or (epoch + 1) == TOTAL_EPOCHS:
            print(f"Epoch [{epoch+1}/{TOTAL_EPOCHS}], Loss: {running_loss/len(dataloader):.4f}, Acc: {epoch_acc:.2f}%, Time: {epoch_duration:.2f}s")
            
    total_time = time.time() - start_time
    print(f"\nTraining completed in {total_time:.2f} seconds.")
    print(f"Average time per epoch: {total_time/TOTAL_EPOCHS:.4f} seconds.")

    # 6. Save Model
    torch.save(model.state_dict(), "captcha_cnn.pth")
    print("\nModel saved to captcha_cnn.pth")
    
    # Save a small metadata file for inference script to know dimensions
    with open("model_config.py", "w") as f:
        f.write(f"IMAGE_WIDTH = {IMAGE_WIDTH}\n")
        f.write(f"IMAGE_HEIGHT = {IMAGE_HEIGHT}\n")

if __name__ == "__main__":
    train()
