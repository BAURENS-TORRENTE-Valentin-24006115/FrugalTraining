function ouvrirPanelAdmin() {
    console.log("Accès admin OK");
}

// Affiche la fenêtre de mot de passe, sauf si la session admin est encore valide
function afficherMotDePasse() {
    // .then attend la réponse de Python (true ou false)
    window.pywebview.api.est_admin().then(function (connecte) {
        if (connecte) {
            ouvrirPanelAdmin();
        } else {
            document.getElementById("admin-login").style.display = "flex";
        }
    });
}

// Ferme la fenêtre de mot de passe et la remet à zéro 
    function cacherMotDePasse() {
    document.getElementById("admin-login").style.display = "none";
    document.getElementById("admin-password").value = "";
    document.getElementById("admin-message").innerText = "";
}

// Envoie le mot de passe à Python, qui renvoie "ok", "faux" ou "bloque"
function validerMotDePasse() {
    const mdp = document.getElementById("admin-password").value;
    const message = document.getElementById("admin-message");

    // La vérification est faite côté Python, jamais en JavaScript
    window.pywebview.api.verifier_mot_de_passe_admin(mdp).then(function (resultat) {
        if (resultat === "ok") {
            cacherMotDePasse();
            ouvrirPanelAdmin();
        } else if (resultat === "bloque") {
            message.innerText = "Trop d'erreurs, réessayez dans 5 minutes";
        } else {
            message.innerText = "Mot de passe incorrect";
        }
        document.getElementById("admin-password").value = "";
    });
}

// Raccourci Ctrl + Shift + A pour ouvrir la fenêtre de mot de passe
document.addEventListener("keydown", function (event) {
    if (event.ctrlKey && event.shiftKey && event.key === "A") {
        afficherMotDePasse();
    }
});