let fontScale = 100;
let wordsPerSecond = 3;
let targetText = '';
let targetCharacters = [];
let displayedLength = 0;
let typingTimer = null;
let pendingDisplayId = null;
let activeWord = null;
let activeWordIndex = 0;
let characterDelay = 0;
const responseBox = document.getElementById('ai-answer');
const BASE_MIN_FONT_SIZE = 1.2;
const BASE_MAX_FONT_SIZE = 5.0;

function updateLogo(imageUrl) {
    document.getElementById('logo').src = imageUrl || 'img/models/mistral.png';
}

function fitTextToScreen(textBox = responseBox) {
    if (!textBox.textContent.trim()) return;

    const minFontSize = BASE_MIN_FONT_SIZE * fontScale / 100;
    const maxFontSize = BASE_MAX_FONT_SIZE * fontScale / 100;
    let low = minFontSize;
    let high = maxFontSize;
    let bestSize = minFontSize;
    while (low <= high) {
        const mid = Number(((low + high) / 2).toFixed(2));
        textBox.style.fontSize = `${mid}rem`;
        if (textBox.scrollHeight <= textBox.clientHeight &&
            textBox.scrollWidth <= textBox.clientWidth) {
            bestSize = mid;
            low = mid + 0.1;
        } else {
            high = mid - 0.1;
        }
    }
    textBox.style.fontSize = `${bestSize}rem`;

    while (textBox.scrollHeight > textBox.clientHeight && textBox.innerText.length > 0) {
        const words = textBox.innerText.split(' ');
        words.shift();
        textBox.innerText = `...${words.join(' ')}`;
    }
}

function displayResponse(text, progressive = false) {
    text = text || '';
    if (text === targetText) return;
    if (!progressive) {
        clearTimeout(typingTimer);
        typingTimer = null;
        targetText = text;
        targetCharacters = Array.from(text);
        displayedLength = targetCharacters.length;
        pendingDisplayId = null;
        activeWord = null;
        responseBox.textContent = text;
        fitTextToScreen();
        return;
    }
    if (!text.startsWith(targetText) && !targetText.startsWith(text)) {
        clearTimeout(typingTimer);
        typingTimer = null;
        displayedLength = 0;
        pendingDisplayId = null;
        activeWord = null;
        responseBox.textContent = '';
    } else {
        if (text.length < targetText.length) {
            clearTimeout(typingTimer);
            typingTimer = null;
            activeWord = null;
        }
    }
    targetText = text;
    targetCharacters = Array.from(text);
    displayedLength = Math.min(displayedLength, targetCharacters.length);
    advanceDisplay();
}

function finishResponse(text, displayId) {
    displayResponse(text, true);
    pendingDisplayId = displayId;
    advanceDisplay();
}

function advanceDisplay() {
    if (typingTimer !== null) return;
    if (displayedLength >= targetCharacters.length) {
        if (pendingDisplayId !== null) fitTextToScreen();
        acknowledgeFinishedDisplay();
        return;
    }
    if (!activeWord) {
        const remaining = targetCharacters.slice(displayedLength).join('');
        let match = remaining.match(/^\s*\S+\s+/);
        if (!match && pendingDisplayId !== null) match = remaining.match(/^\s*\S+\s*$/);
        if (!match) return;
        activeWord = Array.from(match[0]);
        activeWordIndex = 0;
        characterDelay = 1000 / (wordsPerSecond * activeWord.length);
    }
    typingTimer = setTimeout(() => {
        typingTimer = null;
        responseBox.append(targetCharacters[displayedLength]);
        displayedLength += 1;
        activeWordIndex += 1;
        if (activeWordIndex >= activeWord.length) {
            activeWord = null;
            fitTextToScreen();
        }
        advanceDisplay();
    }, characterDelay);
}

function acknowledgeFinishedDisplay() {
    if (pendingDisplayId === null || displayedLength < targetCharacters.length || !window.pywebview?.api) return;
    const displayId = pendingDisplayId;
    pendingDisplayId = null;
    window.pywebview.api.acknowledge_display(displayId);
}

function setDisplaySettings(scale, speed) {
    fontScale = Number(scale) || 100;
    wordsPerSecond = Math.max(0.5, Math.min(10, Number(speed) || 3));
    fitTextToScreen();
}

function renderData(data) {
    setDisplaySettings(data.font_scale, data.words_per_second);
    const selected = data.models.find(model => model.id === data.selected_model_id);
    updateLogo(selected && selected.image);
    displayResponse(data.reponse_ia_repondante);
}

window.updateLogo = updateLogo;
window.displayResponse = displayResponse;
window.finishResponse = finishResponse;
window.setDisplaySettings = setDisplaySettings;
window.setFontScale = scale => setDisplaySettings(scale, wordsPerSecond);
window.renderData = renderData;
window.addEventListener('resize', fitTextToScreen);
window.addEventListener('pywebviewready', async () => {
    renderData(await window.pywebview.api.obtenir_donnees());
});
