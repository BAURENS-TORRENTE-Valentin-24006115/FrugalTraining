const responseBox = document.getElementById('ai-answer');
const MIN_FONT_SIZE = 1.2; // Minimum readable font size (rem)
const MAX_FONT_SIZE = 5.0; // Maximum font size for short text (rem)

function updateLogo(imageUrl) {
    document.getElementById('logo').src = imageUrl || 'img/models/mistral.png';
}

function fitTextToScreen() {
    if (!responseBox.textContent.trim()) return;

    let low = MIN_FONT_SIZE;
    let high = MAX_FONT_SIZE;
    let bestSize = MIN_FONT_SIZE;

    // Binary search to find the optimal font size that fits the container
    while (low <= high) {
        const mid = parseFloat(((low + high) / 2).toFixed(2));
        responseBox.style.fontSize = mid + 'rem';

        if (responseBox.scrollHeight <= responseBox.clientHeight && 
            responseBox.scrollWidth <= responseBox.clientWidth) {
            bestSize = mid;
            low = mid + 0.1; // Try bigger
        } else {
            high = mid - 0.1; // Try smaller
        }
    }

    responseBox.style.fontSize = bestSize + 'rem';

    // Fallback: If text overflows even at minimum font size, trim oldest words from the top
    while (responseBox.scrollHeight > responseBox.clientHeight && responseBox.innerText.length > 0) {
        const words = responseBox.innerText.split(' ');
        words.shift(); 
        responseBox.innerText = '...' + words.join(' ');
    }
}

function displayResponse(text) {
    responseBox.textContent = text || '';
    fitTextToScreen();
}

function renderData(data) {
    const selected = data.models.find(model => model.id === data.selected_model_id);
    updateLogo(selected && selected.image);
    displayResponse(data.reponse_ia_repondante);
}

window.updateLogo = updateLogo;
window.displayResponse = displayResponse;
window.renderData = renderData;
window.addEventListener('resize', fitTextToScreen);
window.addEventListener('pywebviewready', async () => {
    renderData(await window.pywebview.api.obtenir_donnees());
});
