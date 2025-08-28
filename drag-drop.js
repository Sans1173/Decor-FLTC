const canvas = document.getElementById("room-canvas");
const ctx = canvas.getContext("2d");

const background = new Image();
background.src = "room.jpg"; // background
background.onload = () => redrawCanvas();

let draggedImg = null;
let decorItems = [];
let selectedItem = null;
let isPreviewMode = false;

// History stacks
let undoStack = [];
let redoStack = [];

function saveState() {
  undoStack.push(JSON.stringify(decorItems));
  redoStack = [];
}

document.querySelectorAll(".decor").forEach((item) => {
  item.addEventListener("dragstart", (e) => {
    draggedImg = e.target;
  });
});

canvas.addEventListener("dragover", (e) => e.preventDefault());

canvas.addEventListener("drop", (e) => {
  e.preventDefault();
  if (draggedImg) {
    saveState();
    const rect = canvas.getBoundingClientRect();
    const x = snapToGrid(e.clientX - rect.left - 40);
    const y = snapToGrid(e.clientY - rect.top - 40);

    const img = new Image();
    img.onload = () => {
      decorItems.push({ img, x, y, w: 80, h: 80, rotation: 0 });
      redrawCanvas();
    };
    img.src = draggedImg.src;
  }
});

// Snap to grid
function snapToGrid(val) {
  const gridSize = 20;
  return Math.round(val / gridSize) * gridSize;
}

// Mouse controls
let isDragging = false;
let dragOffsetX = 0;
let dragOffsetY = 0;

canvas.addEventListener("mousedown", (e) => {
  if (isPreviewMode) return;
  const rect = canvas.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  selectedItem = null;
  for (let i = decorItems.length - 1; i >= 0; i--) {
    let item = decorItems[i];
    if (
      mouseX >= item.x &&
      mouseX <= item.x + item.w &&
      mouseY >= item.y &&
      mouseY <= item.y + item.h
    ) {
      selectedItem = item;
      dragOffsetX = mouseX - item.x;
      dragOffsetY = mouseY - item.y;
      isDragging = true;
      saveState();
      break;
    }
  }
});

canvas.addEventListener("mousemove", (e) => {
  if (isDragging && selectedItem) {
    const rect = canvas.getBoundingClientRect();
    selectedItem.x = snapToGrid(e.clientX - rect.left - dragOffsetX);
    selectedItem.y = snapToGrid(e.clientY - rect.top - dragOffsetY);
    redrawCanvas();
  }
});

canvas.addEventListener("mouseup", () => {
  isDragging = false;
});

// Touch support
canvas.addEventListener("touchstart", (e) => {
  const touch = e.touches[0];
  const rect = canvas.getBoundingClientRect();
  const x = touch.clientX - rect.left;
  const y = touch.clientY - rect.top;
  selectedItem = decorItems.find(
    (item) => x >= item.x && x <= item.x + item.w && y >= item.y && y <= item.h
  );
  saveState();
});

canvas.addEventListener("touchmove", (e) => {
  if (selectedItem) {
    const touch = e.touches[0];
    const rect = canvas.getBoundingClientRect();
    selectedItem.x = snapToGrid(touch.clientX - rect.left - selectedItem.w / 2);
    selectedItem.y = snapToGrid(touch.clientY - rect.top - selectedItem.h / 2);
    redrawCanvas();
  }
});

// Redraw
function redrawCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(background, 0, 0, canvas.width, canvas.height);

  decorItems.forEach((item) => {
    ctx.save();
    ctx.translate(item.x + item.w / 2, item.y + item.h / 2);
    ctx.rotate((item.rotation * Math.PI) / 180);
    ctx.drawImage(item.img, -item.w / 2, -item.h / 2, item.w, item.h);
    ctx.restore();
  });

  if (!isPreviewMode) drawGrid();
}

// Draw alignment grid
function drawGrid() {
  const gridSize = 20;
  ctx.strokeStyle = "#eee";
  for (let x = 0; x < canvas.width; x += gridSize) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height);
    ctx.stroke();
  }
  for (let y = 0; y < canvas.height; y += gridSize) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(canvas.width, y);
    ctx.stroke();
  }
}

// Undo / Redo
function undo() {
  if (undoStack.length > 0) {
    redoStack.push(JSON.stringify(decorItems));
    decorItems = JSON.parse(undoStack.pop());
    redrawCanvas();
  }
}
function redo() {
  if (redoStack.length > 0) {
    undoStack.push(JSON.stringify(decorItems));
    decorItems = JSON.parse(redoStack.pop());
    redrawCanvas();
  }
}

// Preview mode
function togglePreview() {
  isPreviewMode = !isPreviewMode;
  redrawCanvas();
}

// Save & Load JSON
function saveLayoutJSON() {
  const data = JSON.stringify(decorItems);
  const blob = new Blob([data], { type: "application/json" });
  const link = document.createElement("a");
  link.download = "layout.json";
  link.href = URL.createObjectURL(blob);
  link.click();
}
function loadLayoutJSON() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "application/json";
  input.onchange = (e) => {
    const file = e.target.files[0];
    const reader = new FileReader();
    reader.onload = () => {
      decorItems = JSON.parse(reader.result);
      redrawCanvas();
    };
    reader.readAsText(file);
  };
  input.click();
}

// Reset
function resetDecor() {
  saveState();
  decorItems = [];
  redrawCanvas();
}
