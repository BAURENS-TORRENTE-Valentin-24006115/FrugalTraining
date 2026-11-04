import hashlib
import hmac
import json
import secrets
import time
from getpass import getpass

FICHIER_MDP = "admin_password.json"

ITERATIONS = 600000      # nombre de fois que le calcul est répété (valeur conseillée par l'OWASP)
ESSAIS_MAX = 5           # nombre d'erreurs avant blocage
DUREE_BLOCAGE = 5 * 60   
DUREE_SESSION = 10 * 60  # l'admin est déconnecté après 10 minutes


def hasher(mot_de_passe, sel):
    """Calcule le hash du mot de passe avec PBKDF2-SHA256."""
    # Répéter le calcul rend chaque essai lent qui freine les attaques par force brute
    resultat = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel.encode(), ITERATIONS)
    # Conversion en texte hexadécimal pour l'enregistrer dans le JSON    
    return resultat.hex()  


def enregistrer_mot_de_passe(mot_de_passe):
    """Enregistre le hash et le sel du mot de passe dans le fichier."""
    # Sel aléatoire : deux même mots de passe donnent deux hash différents
    sel = secrets.token_hex(16)
    with open(FICHIER_MDP, "w") as f:
        json.dump({"sel": sel, "hash": hasher(mot_de_passe, sel)}, f)


def verifier_mot_de_passe(mot_de_passe):
    """Renvoie True si le mot de passe correspond au hash enregistré."""
    try:
        with open(FICHIER_MDP) as f:
            donnees = json.load(f)
    except FileNotFoundError:
        # aucun mot de passe encore creer
        return False

    hash_tape = hasher(mot_de_passe, donnees["sel"])
    # compare_digest fait la même chose que == mais a toujours le même temps
    # on ne peut pas deviner le hash en mesurant le temps de réponse
    return hmac.compare_digest(hash_tape, donnees["hash"])


class SessionAdmin:
    """Gère la connexion admin : session, compteur d'erreurs et blocage."""

    def __init__(self):
        # Heures stockées en secondes (format de time.time())
        self.connecte_jusqua = 0
        self.bloque_jusqua = 0
        self.nb_erreurs = 0

    def connexion(self, mot_de_passe):
        """Renvoie "ok", "faux" ou "bloque"."""
        maintenant = time.time()

        if maintenant < self.bloque_jusqua:
            return "bloque"

        if verifier_mot_de_passe(mot_de_passe):
            self.nb_erreurs = 0
            self.connecte_jusqua = maintenant + DUREE_SESSION
            return "ok"

        self.nb_erreurs += 1
        if self.nb_erreurs >= ESSAIS_MAX:
            self.nb_erreurs = 0
            self.bloque_jusqua = maintenant + DUREE_BLOCAGE
            return "bloque"
        return "faux"

    def est_connecte(self):
        return time.time() < self.connecte_jusqua

    def deconnexion(self):
        self.connecte_jusqua = 0


# Exécuté uniquement avec la commande : python admin_auth.py
if __name__ == "__main__":
    # getpass fonctionne comme input, mais n'affiche pas ce qu'on tape
    mdp = getpass("Nouveau mot de passe admin : ")
    confirmation = getpass("Confirmer : ")

    if mdp != confirmation:
        print("Les deux mots de passe sont différents")
    elif len(mdp) < 8:
        print("Il faut au moins 8 caractères")
    else:
        enregistrer_mot_de_passe(mdp)
        print("Mot de passe enregistré")