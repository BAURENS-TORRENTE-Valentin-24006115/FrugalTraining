let typingInterval = null;

function displayResponse(text, progressive = true) {
    const responseBox = document.getElementById('ai-reponse');
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

// Make accessible to Python evaluate_js
window.displayResponse = displayResponse;

window.addEventListener('pywebviewready', function() {
    window.pywebview.api.obtenir_donnees().then(function(data) {

        // 1. Initial Texts & Scores
        document.getElementById('role-header').innerText = `Role: ${data.current_role_name}`;
        document.getElementById('average-score-text').innerText = data.average_score;
        displayResponse(data.reponse_ia, false);

        // 2. Build Chart
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

        // 3. Render Roles (Bottom Left)
        const rolesContainer = document.getElementById('roles-list');
        rolesContainer.innerHTML = '';

        data.roles.forEach(role => {
            const button = document.createElement('button');
            button.className = 'persona-button';
            button.type = 'button';
            button.innerHTML = `
                <img src='${role.icon || 'img/persona.svg'}' alt=''>
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

        // 4. Render Models (Bottom Right)
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