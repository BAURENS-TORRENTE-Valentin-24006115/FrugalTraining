const responseBox = document.getElementById('ai-answer');

function displayResponse(text) {
    responseBox.textContent = text || '';
}

function renderData(data) {
    document.getElementById('role-header').textContent = `Rôle : ${data.current_role_name}`;
    const personaImage = document.getElementById('persona-image');
    if (personaImage) personaImage.src = data.current_role_icon || 'img/personnas/persona.svg';
    displayResponse(data.reponse_ia_frugal);

    // const chartGrid = document.getElementById('chart-grid');
    // const chartLabels = document.getElementById('chart-labels');
    // chartGrid.replaceChildren();
    // chartLabels.replaceChildren();
    // data.models.forEach(model => {
    //     const bar = document.createElement('i');
    //     bar.style.height = `${Math.max(0, Math.min(100, model.score || 0))}%`;
    //     bar.title = `${model.name} : ${model.score || 0}/100`;
    //     chartGrid.appendChild(bar);
    //     const label = document.createElement('span');
    //     label.textContent = model.name;
    //     chartLabels.appendChild(label);
    // });

    const roles = document.getElementById('roles-list');
    roles.replaceChildren();
    data.roles.forEach(role => {
        const p = document.createElement('p');
        p.type = 'paragraph';
        p.className = 'persona-paragraph';
        p.disabled = data.running;
        p.classList.toggle('is-selected', role.id === data.selected_role_id);
        // const image = document.createElement('img');
        // image.src = role.icon || 'img/personnas/persona.svg';
        // image.alt = '';
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
        // const image = document.createElement('img');
        // image.src = model.image || 'img/models/mistral.png';
        // image.alt = '';
        const label = document.createElement('span');
        label.textContent = model.keybind ? `| ${model.name} [${model.keybind.toUpperCase()}]` : model.name;
        p.append(label);
        p.addEventListener('click', () => window.pywebview.api.select_model(model.id));
        models.appendChild(p);
    });
}

window.displayResponse = displayResponse;
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
