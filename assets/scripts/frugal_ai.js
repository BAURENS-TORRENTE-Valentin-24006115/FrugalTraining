let typingInterval = null;

function displayResponse(text, progressive = true) {
    const responseBox = document.getElementById('ai-answer');
    clearInterval(typingInterval);

    if (!progressive) {
        responseBox.innerText = text;
        return;
    }

    responseBox.innerText = '';
    let index = 0;
    typingInterval = setInterval(() => {
        responseBox.innerText += text.charAt(index);
        index++;
        if (index >= text.length) {
            clearInterval(typingInterval);
        }
    }, 25);
}

function updateSelectedPersona(imageUrl, currentRoleName) {
    const personaImage = document.getElementById('persona-image');
    const roleHeader = document.getElementById('role-header');
    if (personaImage) {
        personaImage.src = imageUrl;
    }
    if (roleHeader) {
        roleHeader.innerText = `Role: ${currentRoleName}`;
    }
}

// Make accessible to Python evaluate_js
window.displayResponse = displayResponse;
window.updateSelectedPersona = updateSelectedPersona;

window.addEventListener('pywebviewready', function() {
    window.pywebview.api.obtenir_donnees().then(function(data) {

        // Initial Texts & Scores
        document.getElementById('persona-image').src = data.current_role_icon || 'img/personnas/persona.svg';
        document.getElementById('role-header').innerText = `Role: ${data.current_role_name}`;
        document.getElementById('average-score-text').innerText = data.average_score;
        displayResponse(data.reponse_ia_frugal, false);

        // Build Chart
        const chartGrid = document.getElementById('chart-grid');
        const chartLabels = document.getElementById('chart-labels');
        chartGrid.innerHTML = '';
        chartLabels.innerHTML = '';

        data.models.forEach(model => {
            const bar = document.createElement('i');
            bar.style.height = `${model.score}%`;
            bar.title = `${model.name}: ${model.score}%`;
            chartGrid.appendChild(bar);

            const label = document.createElement('span');
            label.innerText = model.name;
            chartLabels.appendChild(label);
        });

        // Render Roles (Bottom Left)
        const rolesContainer = document.getElementById('roles-list');
        rolesContainer.innerHTML = '';

        data.roles.forEach(role => {
            const button = document.createElement('button');
            button.className = 'persona-button';
            button.type = 'button';
            button.innerHTML = `
                <img src='${role.icon || 'img/personnas/persona.svg'}' alt=''>
                <span>${role.name}</span>
            `;

            if (role.id === data.selected_role_id) {
                button.classList.add('is-selected');
            }

            button.addEventListener('click', () => {
                document.querySelectorAll('.persona-button').forEach(b => b.classList.remove('is-selected'));
                button.classList.add('is-selected');
                document.getElementById('role-header').innerText = `Role: ${role.name}`;
                window.pywebview.api.select_role(role.id);
            });

            rolesContainer.appendChild(button);
        });

        // Render Models (Bottom Right)
        const modelsContainer = document.getElementById('models-list');
        modelsContainer.innerHTML = '';

        data.models.forEach(model => {
            const button = document.createElement('button');
            button.className = 'model-button';
            button.type = 'button';
            button.innerHTML = `
                <img src='${model.image}' alt=''>
                <span>${model.name}</span>
            `;

            if (model.id === data.selected_model_id) {
                button.classList.add('is-selected');
            }

            button.addEventListener('click', () => {
                document.querySelectorAll('.model-button').forEach(b => b.classList.remove('is-selected'));
                button.classList.add('is-selected');
                window.pywebview.api.select_model(model.id);
            });

            modelsContainer.appendChild(button);
        });
    });
});

document.addEventListener('keydown', async (event) => {
    // Ignore keypresses if the user is typing in a text box (like the admin password field)
    const activeElement = document.activeElement.tagName;
    if (activeElement === 'INPUT' || activeElement === 'TEXTAREA' || document.activeElement.isContentEditable) {
        return; 
    }

    const pressedKey = event.key.toLowerCase();

    try {
        // Fetch the absolute latest data from Python
        const data = await window.pywebview.api.obtenir_donnees();
        
        // Check for a matching Model keybind
        const matchedModel = data.models.find(m => m.keybind && m.keybind.toLowerCase() === pressedKey);
        if (matchedModel) {
            console.log(`Keybind selected model: ${matchedModel.name}`);
            window.pywebview.api.select_model(matchedModel.id);
            return; 
        }

        // 4. Check for a matching Persona keybind
        const matchedPersona = data.roles.find(p => p.keybind && p.keybind.toLowerCase() === pressedKey);
        if (matchedPersona) {
            console.log(`Keybind selected persona: ${matchedPersona.name}`);
            window.pywebview.api.select_role(matchedPersona.id);
        }
    } catch (error) {
        console.error("Error matching keybinds:", error);
    }
});