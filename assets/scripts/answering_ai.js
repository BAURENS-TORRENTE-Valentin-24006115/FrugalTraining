const BASE_MIN_FONT_SIZE = 1.2; // Minimum readable font size (rem)
const BASE_MAX_FONT_SIZE = 5.0; // Maximum font size for short text (rem)
let fontScale = 100; // Réglage depuis les paramètres (%)
let lastText = '';
let typingInterval = null;
const responseBox = document.getElementById('ai-answer');

function updateLogo(imageUrl) {
    document.getElementById('logo').src = imageUrl;
}

function fitTextToScreen() {
    if (!responseBox.textContent.trim()) return;

    const MIN_FONT_SIZE = BASE_MIN_FONT_SIZE * fontScale / 100;
    const MAX_FONT_SIZE = BASE_MAX_FONT_SIZE * fontScale / 100;

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

function displayResponse(text, progressive = true) {
    lastText = text;
    clearInterval(typingInterval);

    if (!progressive) {
        responseBox.textContent = text;
        fitTextToScreen();
        return;
    }

    responseBox.textContent = '';
    let index = 0;

    typingInterval = setInterval(() => {
        // Use textContent instead of innerText to preserve trailing spaces
        const char = text.charAt(index);
        responseBox.textContent += char;
        index++;

        // Only adjust font scale on spaces/newlines or final character to prevent flickering
        if (char === ' ' || char === '\n' || index >= text.length) {
            fitTextToScreen();
        }

        if (index >= text.length) {
            clearInterval(typingInterval);
        }
    }, 25);
}

// Expose functions to Python
window.updateLogo = updateLogo;
window.displayResponse = displayResponse;
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

// --- Taille de police réglable depuis les paramètres ---
window.setFontScale = function (scale) {
    fontScale = scale;
    clearInterval(typingInterval);
    if (lastText) {
        responseBox.textContent = lastText;
        fitTextToScreen();
    }
};