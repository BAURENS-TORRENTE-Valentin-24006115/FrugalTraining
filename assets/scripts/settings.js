let settingsData = { personas: [], models: [] };

function switchTab(name, button) {
    document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(item => item.classList.remove('active'));
    document.getElementById(`tab-${name}`).classList.add('active');
    button.classList.add('active');
}

async function loadData() {
    try {
        settingsData = await window.pywebview.api.get_all_settings();
        renderList('personas', settingsData.personas);
        renderList('models', settingsData.models);
    } catch (error) {
        alert(`Session administrateur expirée : ${error}`);
        window.close();
    }
}

function renderList(kind, items) {
    const list = document.getElementById(`${kind}-container`);
    list.replaceChildren();
    items.forEach(item => {
        const card = document.createElement('div');
        card.className = 'item-card';
        const info = document.createElement('div');
        const image = document.createElement('img');
        image.src = kind === 'models' ? item.image : item.icon;
        image.alt = '';
        image.width = image.height = 32;
        const title = document.createElement('span');
        title.textContent = `${item.name} (${item.id})${kind === 'models' ? ` — ${item.score}/100` : ''}`;
        info.append(image, title);
        const actions = document.createElement('div');
        const edit = document.createElement('button');
        edit.type = 'button';
        edit.className = 'btn-edit';
        edit.textContent = 'Éditer';
        edit.addEventListener('click', () => kind === 'models' ? editModel(item.id) : editPersona(item.id));
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn-delete';
        remove.textContent = 'Supprimer';
        remove.addEventListener('click', () => kind === 'models' ? deleteModel(item.id) : deletePersona(item.id));
        actions.append(edit, remove);
        card.append(info, actions);
        list.appendChild(card);
    });
}

function editPersona(id) {
    const item = settingsData.personas.find(p => p.id === id);
    if (!item) return;
    for (const field of ['id', 'name', 'icon', 'persona']) {
        document.getElementById(`p-${field}`).value = item[field];
    }
}

function editModel(id) {
    const item = settingsData.models.find(m => m.id === id);
    if (!item) return;
    for (const field of ['id', 'name', 'provider', 'model', 'base_url', 'image', 'score']) {
        document.getElementById(`m-${field}`).value = item[field] ?? '';
    }
    document.getElementById('m-key').value = item.api_key || '';
}

async function savePersona() {
    const item = Object.fromEntries(['id', 'name', 'icon', 'persona'].map(field =>
        [field, document.getElementById(`p-${field}`).value.trim()]));
    try {
        await window.pywebview.api.save_persona(item);
        document.getElementById('form-persona').reset();
        await loadData();
    } catch (error) { alert(String(error)); }
}

async function deletePersona(id) {
    if (!confirm(`Supprimer le persona « ${id} » ?`)) return;
    try { await window.pywebview.api.delete_persona(id); await loadData(); }
    catch (error) { alert(String(error)); }
}

async function saveModel() {
    const item = Object.fromEntries(['id', 'name', 'provider', 'model', 'base_url', 'image'].map(field =>
        [field, document.getElementById(`m-${field}`).value.trim()]));
    item.api_key = document.getElementById('m-key').value.trim();
    item.score = Number(document.getElementById('m-score').value);
    try {
        await window.pywebview.api.save_model(item);
        document.getElementById('form-model').reset();
        await loadData();
    } catch (error) { alert(String(error)); }
}

async function deleteModel(id) {
    if (!confirm(`Supprimer le modèle « ${id} » ?`)) return;
    try { await window.pywebview.api.delete_model(id); await loadData(); }
    catch (error) { alert(String(error)); }
}

window.addEventListener('pywebviewready', loadData);
