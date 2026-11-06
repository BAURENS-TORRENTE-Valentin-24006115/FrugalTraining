const responseBox = document.getElementById('ai-answer');

function updateLogo(imageUrl) {
    document.getElementById('logo').src = imageUrl || 'img/models/mistral.png';
}

function fitTextToScreen() {
    let size = 5;
    responseBox.style.fontSize = `${size}rem`;
    while (size > 1.2 && (responseBox.scrollHeight > responseBox.clientHeight || responseBox.scrollWidth > responseBox.clientWidth)) {
        size -= 0.2;
        responseBox.style.fontSize = `${size}rem`;
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
