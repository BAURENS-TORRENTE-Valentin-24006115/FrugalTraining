let firstAdminSetup = false;

async function ouvrirPanelAdmin() {
    await window.pywebview.api.ouvrir_panel_admin();
}

async function afficherMotDePasse() {
    try {
        if (await window.pywebview.api.est_admin()) {
            await ouvrirPanelAdmin();
            return;
        }
        firstAdminSetup = !(await window.pywebview.api.admin_configure());
        document.getElementById('admin-login').style.display = 'flex';
        document.getElementById('admin-confirmation').style.display = firstAdminSetup ? 'block' : 'none';
        document.querySelector('#admin-login h2').textContent = firstAdminSetup ? 'Créer le mot de passe admin' : 'Accès admin';
        document.getElementById('admin-message').textContent = firstAdminSetup ? 'Au moins 8 caractères.' : '';
        document.getElementById('admin-password').focus();
    } catch (error) {
        document.getElementById('admin-message').textContent = String(error);
    }
}

function cacherMotDePasse() {
    document.getElementById('admin-login').style.display = 'none';
    document.getElementById('admin-password').value = '';
    document.getElementById('admin-confirmation').value = '';
    document.getElementById('admin-message').textContent = '';
}

async function validerMotDePasse() {
    const password = document.getElementById('admin-password').value;
    const message = document.getElementById('admin-message');
    try {
        if (firstAdminSetup) {
            const confirmation = document.getElementById('admin-confirmation').value;
            if (!(await window.pywebview.api.initialiser_admin(password, confirmation))) {
                message.textContent = 'Vérifiez la confirmation et utilisez au moins 8 caractères.';
                return;
            }
        } else {
            const result = await window.pywebview.api.verifier_mot_de_passe_admin(password);
            if (result !== 'ok') {
                message.textContent = result === 'bloque' ? 'Trop d’erreurs, réessayez dans 5 minutes.' : 'Mot de passe incorrect.';
                return;
            }
        }
        cacherMotDePasse();
        await ouvrirPanelAdmin();
    } catch (error) {
        message.textContent = String(error);
    } finally {
        document.getElementById('admin-password').value = '';
    }
}

document.addEventListener('keydown', event => {
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'a') {
        event.preventDefault();
        afficherMotDePasse();
    } else if (event.key === 'Enter' && document.getElementById('admin-login').style.display === 'flex') {
        validerMotDePasse();
    }
});
