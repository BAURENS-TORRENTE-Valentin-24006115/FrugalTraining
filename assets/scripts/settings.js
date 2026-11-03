let settingsData = { personas: [], models: [] };

function switchTab(tabName) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    
    document.getElementById(`tab-${tabName}`).classList.add('active');
    event.target.classList.add('active');
}

function loadData() {
    window.pywebview.api.get_all_settings().then(data => {
        settingsData = data;
        renderPersonas();
        renderModels();
    });
}

function renderPersonas() {
    const list = document.getElementById('personas-container');
    list.innerHTML = '';
    settingsData.personas.forEach(p => {
        list.innerHTML += `
            <div class="item-card">
                <span><strong>${p.name}</strong> (${p.id})</span>
                <div>
                    <button class="btn-edit" onclick="editPersona('${p.id}')">Éditer</button>
                    <button class="btn-delete" onclick="deletePersona('${p.id}')">Supprimer</button>
                </div>
            </div>`;
    });
}

function renderModels() {
    const list = document.getElementById('models-container');
    list.innerHTML = '';
    settingsData.models.forEach(m => {
        list.innerHTML += `
            <div class="item-card">
                <span><strong>${m.name}</strong> (${m.id}) - Score: ${m.score}</span>
                <div>
                    <button class="btn-edit" onclick="editModel('${m.id}')">Éditer</button>
                    <button class="btn-delete" onclick="deleteModel('${m.id}')">Supprimer</button>
                </div>
            </div>`;
    });
}

function editPersona(id) {
    const p = settingsData.personas.find(x => x.id === id);
    if (!p) return;
    document.getElementById('p-id').value = p.id;
    document.getElementById('p-name').value = p.name;
    document.getElementById('p-icon').value = p.icon || '';
    document.getElementById('p-persona').value = p.persona;
}

function savePersona() {
    const item = {
        id: document.getElementById('p-id').value,
        name: document.getElementById('p-name').value,
        icon: document.getElementById('p-icon').value,
        persona: document.getElementById('p-persona').value
    };
    window.pywebview.api.save_persona(item).then(() => loadData());
}

function deletePersona(id) {
    window.pywebview.api.delete_persona(id).then(() => loadData());
}

function editModel(id) {
    const m = settingsData.models.find(x => x.id === id);
    if (!m) return;
    document.getElementById('m-id').value = m.id;
    document.getElementById('m-name').value = m.name;
    document.getElementById('m-key').value = m.api_key || '';
    document.getElementById('m-image').value = m.image || '';
    document.getElementById('m-score').value = m.score || 0;
}

function saveModel() {
    const item = {
        id: document.getElementById('m-id').value,
        name: document.getElementById('m-name').value,
        api_key: document.getElementById('m-key').value,
        image: document.getElementById('m-image').value,
        score: parseInt(document.getElementById('m-score').value) || 0
    };
    window.pywebview.api.save_model(item).then(() => loadData());
}

function deleteModel(id) {
    window.pywebview.api.delete_model(id).then(() => loadData());
}

window.addEventListener('pywebviewready', loadData);