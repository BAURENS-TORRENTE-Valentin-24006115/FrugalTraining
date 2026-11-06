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
        loadStyle();
    });
}

function renderPersonas() {
    const list = document.getElementById('personas-container');
    list.innerHTML = '';
    settingsData.personas.forEach(p => {
        list.innerHTML += `
            <div class="item-card">
                <div>
                    <img src="${p.icon}" alt="${p.name}" width="32" height="32">
                    <span><strong>${p.name}</strong> (${p.id})</span>
                </div>
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
                <div>
                    <img src="${m.image}" alt="${m.name}" width="32" height="32">
                    <span><strong>${m.name}</strong> (${m.id}) - Score: ${m.score}</span>
                </div>
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
    const id = document.getElementById('p-id').value.trim().toLowerCase();
    const name = document.getElementById('p-name').value.trim();
    const icon = document.getElementById('p-icon').value.trim();
    const persona = document.getElementById('p-persona').value.trim();

    // Verify non-empty fields
    if (!id || !name || !icon || !persona) {
        alert("Tous les champs sont obligatoires.");
        return;
    }

    // Verify lower-case only format for ID
    if (!/^[a-z0-9_-]+$/.test(id)) {
        alert("L'ID doit être écrit uniquement en minuscules (sans espaces ni accents).");
        return;
    }

    const item = { id, name, icon, persona };

    window.pywebview.api.save_persona(item).then(() => {
        loadData();
        document.getElementById('form-persona').reset();
    });
}

function deletePersona(id) {
    if (confirm(`Voulez-vous vraiment supprimer le persona '${id}' ?`)) {
        window.pywebview.api.delete_persona(id).then(() => loadData());
    }
}

function editModel(id) {
    const m = settingsData.models.find(x => x.id === id);
    if (!m) return;
    document.getElementById('m-id').value = m.id;
    document.getElementById('m-name').value = m.name;
    document.getElementById('m-key').value = m.api_key || '';
    document.getElementById('m-image').value = m.image || '';
    document.getElementById('m-score').value = m.score !== undefined ? m.score : 50;
}

function saveModel() {
    const id = document.getElementById('m-id').value.trim().toLowerCase();
    const name = document.getElementById('m-name').value.trim();
    const apiKey = document.getElementById('m-key').value.trim();
    const image = document.getElementById('m-image').value.trim();
    const scoreVal = document.getElementById('m-score').value.trim();

    // Verify non-empty fields
    if (!id || !name || !apiKey || !image || scoreVal === '') {
        alert("Tous les champs (y compris la clé API et le score) sont obligatoires.");
        return;
    }

    // Verify lower-case only format for ID
    if (!/^[a-z0-9_-]+$/.test(id)) {
        alert("L'ID doit être écrit uniquement en minuscules (sans espaces ni accents).");
        return;
    }

    const score = parseInt(scoreVal, 10);
    if (isNaN(score) || score < 0 || score > 100) {
        alert("Le score doit être un nombre valide entre 0 et 100.");
        return;
    }

    const item = { id, name, api_key: apiKey, image, score };

    window.pywebview.api.save_model(item).then(() => {
        loadData();
        document.getElementById('form-model').reset();
    });
}

function deleteModel(id) {
    if (confirm(`Voulez-vous vraiment supprimer l'IA '${id}' ?`)) {
        window.pywebview.api.delete_model(id).then(() => loadData());
    }
}

function loadStyle() {
    window.pywebview.api.get_style().then(style => {
        document.getElementById('s-font-scale').value = style.font_scale;
        document.getElementById('font-scale-value').textContent = style.font_scale;
    });
}

function saveStyle() {
    const fontScale = parseInt(document.getElementById('s-font-scale').value, 10);
    window.pywebview.api.save_style({ font_scale: fontScale });
}

window.addEventListener('pywebviewready', loadData);