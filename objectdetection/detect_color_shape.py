import torch
import torchvision
from torchvision import transforms
import cv2
import matplotlib.pyplot as plt
import webcolors
import numpy as np
from sklearn.cluster import KMeans

# ✅ Load pretrained Mask R-CNN
model = torchvision.models.detection.maskrcnn_resnet50_fpn(weights="COCO_V1")
model.eval()

# ✅ COCO categories
COCO_INSTANCE_CATEGORY_NAMES = [
    '__background__', 'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus',
    'train', 'truck', 'boat', 'traffic light', 'fire hydrant', 'N/A', 'stop sign',
    'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
    'elephant', 'bear', 'zebra', 'giraffe', 'N/A', 'backpack', 'umbrella', 'N/A',
    'N/A', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard',
    'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard',
    'surfboard', 'tennis racket', 'bottle', 'N/A', 'wine glass', 'cup', 'fork',
    'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
    'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
    'potted plant', 'bed', 'N/A', 'dining table', 'N/A', 'N/A', 'toilet',
    'N/A', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone',
    'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'N/A', 'book',
    'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]


# ✅ Convert RGB → simple color name
def rgb_to_name(rgb):
    r, g, b = rgb
    if r > 200 and g > 200 and b > 200:
        return "white"
    if r < 50 and g < 50 and b < 50:
        return "black"
    if r > 150 and g < 80 and b < 80:
        return "red"
    if g > 150 and r < 100 and b < 100:
        return "green"
    if b > 150 and r < 100 and g < 100:
        return "blue"
    if r > 200 and g > 200 and b < 100:
        return "yellow"
    if r > 180 and g > 100 and b < 50:
        return "orange"
    if r > 100 and g < 80 and b > 100:
        return "purple"
    if r > 100 and g > 100 and b > 100:
        return "gray"
    return "color"

# ✅ Fine color using KMeans


# 🎨 Extended color mapping using webcolors
def closest_color(requested_rgb):
    min_colors = {}
    for key, name in webcolors.CSS3_HEX_TO_NAMES.items():
        r, g, b = webcolors.hex_to_rgb(key)
        rd = (r - requested_rgb[0]) ** 2
        gd = (g - requested_rgb[1]) ** 2
        bd = (b - requested_rgb[2]) ** 2
        min_colors[(rd + gd + bd)] = name
    return min_colors[min(min_colors.keys())]

def get_advanced_color_name(rgb):
    try:
        # Try to match directly
        return webcolors.rgb_to_name(rgb, spec='css3')
    except ValueError:
        # Fallback to closest match
        return closest_color(rgb)

# Replace old rgb_to_name in your pipeline:
def get_dominant_color(pixels, k=3):
    if len(pixels) == 0:
        return (128, 128, 128), "unknown"
    kmeans = KMeans(n_clusters=k, n_init=10)
    kmeans.fit(pixels)
    dominant = kmeans.cluster_centers_[np.argmax(np.bincount(kmeans.labels_))]
    rgb = tuple(map(int, dominant))
    color_name = get_advanced_color_name(rgb)
    return rgb, color_name


# ✅ Shape detection
def get_shape(mask):
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return "unknown"
    cnt = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(cnt)
    perimeter = cv2.arcLength(cnt, True)
    if perimeter == 0:
        return "unknown"
    circularity = 4 * np.pi * area / (perimeter * perimeter)
    x, y, w, h = cv2.boundingRect(cnt)
    aspect_ratio = w / h

    if circularity > 0.7:
        return "circular"
    elif 0.8 < aspect_ratio < 1.2:
        return "square"
    elif aspect_ratio > 1.2 or aspect_ratio < 0.8:
        return "rectangular"
    else:
        return "irregular"

# ✅ Image path
IMAGE_PATH = "final.png"  # Replace with your image path

# Load image
image = cv2.imread(IMAGE_PATH)
image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
transform = transforms.Compose([transforms.ToTensor()])
input_tensor = transform(image_rgb).unsqueeze(0)

# Run inference
with torch.no_grad():
    outputs = model(input_tensor)

scores = outputs[0]['scores'].numpy()
labels = outputs[0]['labels'].numpy()
boxes = outputs[0]['boxes'].numpy()
masks = outputs[0]['masks'].squeeze().numpy()

threshold = 0.7
for i in range(len(scores)):
    if scores[i] > threshold:
        print("Labels:", labels[i], " Max allowed:", len(COCO_INSTANCE_CATEGORY_NAMES)-1)
        label = COCO_INSTANCE_CATEGORY_NAMES[labels[i]]
        box = boxes[i].astype(int)
        mask = masks[i] > 0.5

        # Extract pixels
        object_pixels = image_rgb[mask].reshape(-1, 3)

        # Dominant color
        avg_rgb, color_name = get_dominant_color(object_pixels)

        # Shape detection
        shape = get_shape(mask)

        # Draw box
        cv2.rectangle(image_rgb, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
        cv2.putText(image_rgb, f"{color_name} {shape} {label}", (box[0], box[1]-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

# Show
plt.figure(figsize=(12, 8))
plt.imshow(image_rgb)
plt.axis("off")
plt.show()
