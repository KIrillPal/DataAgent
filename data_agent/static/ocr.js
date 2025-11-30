function update_containers() {
    const containers = document.querySelectorAll('.ocr-container');
    containers.forEach(container => {
        const boxes = JSON.parse(container.dataset.boxes || '[]');
        const overlay = container.querySelector('.ocr-overlay');
        const img = container.querySelector('.ocr-image');
        const downloadBtn = container.querySelector('.ocr-download-btn');
        const textArea = container.querySelector('.ocr-text-area');
        
        if (overlay && img) {
            img.onload = function() {
                boxes.forEach(box => {
                    const boxDiv = document.createElement("div");
                    boxDiv.className = "ocr-text-box";
                    boxDiv.style.left = box.x + "%";
                    boxDiv.style.top = box.y + "%";
                    boxDiv.style.width = box.width + "%";
                    boxDiv.style.height = box.height + "%";
                    boxDiv.setAttribute("data-text", box.text);
                    boxDiv.title = box.text + " (" + (box.confidence * 100).toFixed(1) + "%)";
                    
                    boxDiv.addEventListener('click', function(e) {
                        e.stopPropagation();
                        const text = this.getAttribute('data-text');
                        if (navigator.clipboard && text) {
                            navigator.clipboard.writeText(text);
                            this.style.background = 'rgba(143,107,214,0.3)';
                            setTimeout(() => this.style.background = '', 150);
                        }
                    });
                    
                    overlay.appendChild(boxDiv);
                });
            };
            if (img.complete) img.onload();
        }
        
        // Handle download button
        if (downloadBtn && textArea) {
            downloadBtn.addEventListener('click', (e) => {
                e.preventDefault();
                const text = textArea.value;
                if (text) {
                    const blob = new Blob([text], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'ocr-text.txt';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                }
            });
        }
    });
}