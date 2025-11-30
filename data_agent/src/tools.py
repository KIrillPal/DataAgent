from typing import Dict, List
import asyncio
import json
import os
import uuid
from pathlib import Path
import tempfile
import shutil
from PIL import Image


def init_filesystem_tools(tool_config: Dict):
    from langchain_community.agent_toolkits import FileManagementToolkit

    toolkit = FileManagementToolkit(
        root_dir=os.getcwd(),
        selected_tools=tool_config.get('permissions', [])
    )
    return toolkit.get_tools()


def init_mcp_tools(tool_config: Dict):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    with open(tool_config['path'], 'r') as f:
        mcp_config = json.load(f)
    
    mcp_client = MultiServerMCPClient(mcp_config)
    return asyncio.run(mcp_client.get_tools())


def init_ocr_tool(tool_config: Dict):
    """Initialize PaddleOCR tool for character recognition in images."""
    from langchain_core.tools import tool
    from paddleocr import PaddleOCR
    
    # Initialize PaddleOCR once
    ocr_instance = PaddleOCR(use_angle_cls=True, lang='en')
    
    def recognize_text_in_image(image_path: str) -> str:
        try:
            
            # Validate image exists and can be opened
            if not Path(image_path).exists():
                return f"<div class='ocr-error'>Error: Image file not found at {image_path}</div>"
            
            img = Image.open(image_path)
            img_width, img_height = img.size
            
            # Run OCR
            print("Running PaddleOCR on image:", image_path)
            result = ocr_instance.ocr(image_path)
            print("done", result)
            
            if not result or not result[0]:
                return "<div class='ocr-card'><p class='ocr-no-text'>No text detected in image</p></div>"
            
            # Extract text boxes and text
            text_boxes = []
            all_text = []
            
            for line in result:
                texts = line['rec_texts']
                boxes = line['rec_boxes']
                scores = line['rec_scores']
                for text, box, score in zip(texts, boxes, scores):
                    all_text.append(text)
                    x1, y1, x2, y2 = list(map(int, box))
                    
                    text_boxes.append({
                        'x': x1,
                        'y': y1,
                        'width': x2 - x1,
                        'height': y2 - y1,
                        'text': text,
                        'confidence': score
                    })
            
            # Copy image to OCR temp directory instead of encoding to base64
            ocr_dir = Path(tempfile.gettempdir()) / "dataagent_ocr"
            ocr_dir.mkdir(exist_ok=True)
            
            # Generate unique filename
            image_filename = f"{uuid.uuid4().hex}.jpg"
            ocr_image_path = ocr_dir / image_filename
            
            # Copy or convert image to JPEG
            if Path(image_path).suffix.lower() == '.jpg':
                shutil.copy(image_path, ocr_image_path)
            else:
                # Convert to JPEG
                img_rgb = img.convert('RGB')
                img_rgb.save(ocr_image_path, 'JPEG')
            
            # Generate unique ID for this card
            card_id = f"ocr-card-{uuid.uuid4().hex[:8]}"
            
            # Use URL instead of base64
            image_url = f"/api/ocr-image/{image_filename}"
            download_url = image_url
            
            # Create HTML structure with image URL
            html = f'''
<div class="ocr-container">
<div class="ocr-card" id="{card_id}">
<div class="ocr-image-wrapper">
    <img src="{image_url}" alt="OCR Image" class="ocr-image" id="{card_id}-img" />
    <svg class="ocr-overlay" id="{card_id}-svg" viewBox="0 0 {img_width} {img_height}">
    <!-- Text boxes will be inserted here -->
    </svg>
    <a href="{download_url}" download="ocr-result.jpg" class="ocr-download-btn" title="Download image">⬇</a>
</div>
<div class="ocr-text-section">
    <h3 class="ocr-text-title">Extracted Text</h3>
    <textarea class="ocr-text-area" readonly>{' '.join(all_text)}</textarea>
</div>
</div>
</div>

<script>
(function() {{
const cardId = "{card_id}";
const textBoxes = {json.dumps(text_boxes)};
const svg = document.getElementById(cardId + "-svg");

if (svg) {{
// Create rect elements for each text box
textBoxes.forEach((box, idx) => {{
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", box.x);
    rect.setAttribute("y", box.y);
    rect.setAttribute("width", box.width);
    rect.setAttribute("height", box.height);
    rect.setAttribute("class", "ocr-text-box");
    rect.setAttribute("data-text", box.text);
    rect.setAttribute("data-confidence", box.confidence);
    
    // Create title for tooltip
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = box.text + " (confidence: " + (box.confidence * 100).toFixed(1) + "%)";
    rect.appendChild(title);
    
    svg.appendChild(rect);
}});
}}
}})();
</script>
'''
            with open("debug_ocr_output.html", "w") as debug_file:
                debug_file.write(html)
            print(html)
            return html
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"<div class='ocr-error'>Error processing image: {str(e)}</div>"
    
    @tool
    def ocr(image_path: str) -> str:
        """
        Recognize text in an image using PaddleOCR and return an interactive HTML card.
        
        Args:
            image_path: Path to the image file to process
            
        Returns:
            str: HTML element with interactive OCR card and extracted text.
            Paste this result directly into the chat to display the OCR output.
        """
        return recognize_text_in_image(image_path)

    return [ocr]


def init(config: Dict):
    tools = []

    for name, tool_config in config.items():
        if not tool_config.get('enabled', False):
            continue
        if name == 'filesystem':
            tools.extend(init_filesystem_tools(tool_config))

        if name == 'mcp':
            tools.extend(init_mcp_tools(tool_config))
        
        if name == 'ocr':
            tools.extend(init_ocr_tool(tool_config))
    
    return tools