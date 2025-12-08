import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image
from pathlib import Path

# Must match training config
IMAGE_WIDTH = 120
IMAGE_HEIGHT = 33

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
        
        # 120x33 -> 60x16 -> 30x8 -> 15x4
        self.fc1 = nn.Linear(128 * 15 * 4, 256) 
        self.dropout = nn.Dropout(0.5)
        
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
        # No dropout during inference (model.eval() handles it)
        
        d1 = self.fc_digit1(x)
        d2 = self.fc_digit2(x)
        d3 = self.fc_digit3(x)
        d4 = self.fc_digit4(x)
        
        return d1, d2, d3, d4

class CNNInference:
    def __init__(self, model_path="captcha_cnn.pth"):
        self.device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        self.model = SimpleCNN().to(self.device)
        
        if not Path(model_path).exists():
             raise FileNotFoundError(f"Model file {model_path} not found")
             
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.eval()
        
        self.transform = transforms.Compose([
            transforms.Resize((IMAGE_HEIGHT, IMAGE_WIDTH)),
            transforms.ToTensor(),
        ])
        
    def predict(self, image_path: Path) -> (str, float):
        try:
            im = Image.open(image_path).convert('L')
            from PIL import ImageOps
            im = ImageOps.invert(im) # Invert to match training data
            
            input_tensor = self.transform(im).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                d1, d2, d3, d4 = self.model(input_tensor)
                
                # Get predictions
                p1 = d1.argmax(1).item()
                p2 = d2.argmax(1).item()
                p3 = d3.argmax(1).item()
                p4 = d4.argmax(1).item()
                
                # Calculate simple confidence (max softmax prob averaged)
                # Softmax for probabilities
                probs1 = torch.softmax(d1, dim=1).max().item()
                probs2 = torch.softmax(d2, dim=1).max().item()
                probs3 = torch.softmax(d3, dim=1).max().item()
                probs4 = torch.softmax(d4, dim=1).max().item()
                avg_conf = (probs1 + probs2 + probs3 + probs4) / 4.0
                
                return f"{p1}{p2}{p3}{p4}", avg_conf
        except Exception as e:
            print(f"Inference error: {e}")
            return "", 0.0
