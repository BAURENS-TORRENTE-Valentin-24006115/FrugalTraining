const responseBox = document.getElementById('ai-answer');
let targetText = '';
let displayedLength = 0;
let typingTimer = null;
let wordsPerSecond = 3;
let pendingDisplayId = null;
let targetCharacters = [];
let activeWord = null;
let activeWordIndex = 0;
let characterDelay = 0;

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
        return;
    }
    if (!text.startsWith(targetText) && !targetText.startsWith(text)) {
        clearTimeout(typingTimer);
        typingTimer = null;
        displayedLength = 0;
        pendingDisplayId = null;
        activeWord = null;
        responseBox.textContent = '';
    } else if (text.length < targetText.length) {
        clearTimeout(typingTimer);
        typingTimer = null;
        activeWord = null;
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
        displayedLength += 1;
        activeWordIndex += 1;
        responseBox.textContent = targetCharacters.slice(0, displayedLength).join('');
        if (activeWordIndex >= activeWord.length) activeWord = null;
        advanceDisplay();
    }, characterDelay);
}

function acknowledgeFinishedDisplay() {
    if (pendingDisplayId === null || displayedLength < targetCharacters.length || !window.pywebview?.api) return;
    const displayId = pendingDisplayId;
    pendingDisplayId = null;
    window.pywebview.api.acknowledge_display(displayId);
}

function setDisplaySettings(_scale, speed) {
    wordsPerSecond = Math.max(0.5, Math.min(10, Number(speed) || 3));
}

function renderData(data) {
    setDisplaySettings(data.font_scale, data.words_per_second);
    document.getElementById('role-header').textContent = `Rôle : ${data.current_role_name}`;
    const personaImage = document.getElementById('persona-image');
    if (personaImage) personaImage.src = data.current_role_icon || 'img/personas/persona.svg';
    displayResponse(data.reponse_ia_frugal);

    const roles = document.getElementById('roles-list');
    roles.replaceChildren();
    data.roles.forEach(role => {
        const p = document.createElement('p');
        p.type = 'paragraph';
        p.className = 'persona-paragraph';
        p.disabled = data.running;
        p.classList.toggle('is-selected', role.id === data.selected_role_id);
        const label = document.createElement('span');
        label.textContent = role.keybind ? `${role.name} [${role.keybind.toUpperCase()}]|` : role.name;
        p.append(label);
        p.addEventListener('click', () => window.pywebview.api.select_role(role.id));
        roles.appendChild(p);
    });

    const models = document.getElementById('models-list');
    models.replaceChildren();
    data.models.forEach(model => {
        const p = document.createElement('p');
        p.type = 'paragraph';
        p.className = 'model-paragraph';
        p.disabled = data.running;
        p.classList.toggle('is-selected', model.id === data.selected_model_id);
        const label = document.createElement('span');
        label.textContent = model.keybind ? `| ${model.name} [${model.keybind.toUpperCase()}]` : model.name;
        p.append(label);
        p.addEventListener('click', () => window.pywebview.api.select_model(model.id));
        models.appendChild(p);
    });
}

window.displayResponse = displayResponse;
window.finishResponse = finishResponse;
window.setDisplaySettings = setDisplaySettings;
window.renderData = renderData;
window.addEventListener('pywebviewready', async () => {
    renderData(await window.pywebview.api.obtenir_donnees());
});

document.addEventListener('keydown', async (event) => {
    const activeElement = document.activeElement;
    if (event.repeat || event.key.length !== 1 || activeElement?.isContentEditable ||
        ['INPUT', 'TEXTAREA', 'SELECT'].includes(activeElement?.tagName)) {
        return;
    }

    try {
        const data = await window.pywebview.api.obtenir_donnees();
        const pressedKey = event.key.toLowerCase();
        const model = data.models.find(item => item.keybind?.toLowerCase() === pressedKey);
        if (model) {
            event.preventDefault();
            await window.pywebview.api.select_model(model.id);
            return;
        }

        const role = data.roles.find(item => item.keybind?.toLowerCase() === pressedKey);
        if (role) {
            event.preventDefault();
            await window.pywebview.api.select_role(role.id);
        }
    } catch (error) {
        console.error('Erreur de sélection par raccourci :', error);
    }
});
