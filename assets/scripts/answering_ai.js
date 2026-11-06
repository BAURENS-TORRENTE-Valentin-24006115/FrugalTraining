const BASE_MIN_FONT_SIZE = 1.2; // Minimum readable font size (rem)
const BASE_MAX_FONT_SIZE = 5.0; // Maximum font size for short text (rem)
let fontScale = 100; // Réglage depuis les paramètres (%)
let lastText = '';
let typingInterval = null;
const responseBox = document.getElementById('ai-answer');

function updateLogo(imageUrl) {
    document.getElementById('logo').src = imageUrl || 'img/models/mistral.png';
}

function fitTextToScreen(textBox = responseBox) {
    if (!textBox.textContent.trim()) return;

    const MIN_FONT_SIZE = BASE_MIN_FONT_SIZE * fontScale / 100;
    const MAX_FONT_SIZE = BASE_MAX_FONT_SIZE * fontScale / 100;

    let low = MIN_FONT_SIZE;
    let high = MAX_FONT_SIZE;
    let bestSize = MIN_FONT_SIZE;

    // Binary search to find the optimal font size that fits the container
    while (low <= high) {
        const mid = parseFloat(((low + high) / 2).toFixed(2));
        textBox.style.fontSize = mid + 'rem';

        if (textBox.scrollHeight <= textBox.clientHeight && 
            textBox.scrollWidth <= textBox.clientWidth) {
            bestSize = mid;
            low = mid + 0.1; // Try bigger
        } else {
            high = mid - 0.1; // Try smaller
        }
    }

    textBox.style.fontSize = bestSize + 'rem';

    // Fallback: If text overflows even at minimum font size, trim oldest words from the top
    while (textBox.scrollHeight > textBox.clientHeight && textBox.innerText.length > 0) {
        const words = textBox.innerText.split(' ');
        words.shift(); 
        textBox.innerText = '...' + words.join(' ');
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
// Fetch initial data on load
window.addEventListener('pywebviewready', function() {
    window.pywebview.api.obtenir_donnees().then(function(data) {
        fontScale = data.font_scale || 100;
        const activeModel = data.models.find(m => m.id === data.selected_model_id);
        if (activeModel) updateLogo(activeModel.image);
        displayResponse(data.reponse_ia_repondante, true);
    });
});

// Font size adjustable via settings
window.setFontScale = function (scale) {
    fontScale = scale;
    clearInterval(typingInterval);
    if (lastText) {
        responseBox.textContent = lastText;
        fitTextToScreen();
    }
};

window.addEventListener('pywebviewready', async () => {
    renderData(await window.pywebview.api.obtenir_donnees());
});
