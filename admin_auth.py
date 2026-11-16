import hashlib
import hmac
import json
import secrets
import time
from getpass import getpass
from pathlib import Path

FICHIER_MDP = Path(__file__).resolve().parent / "admin_password.json"


def password_exists():
    return FICHIER_MDP.is_file()

ITERATIONS = 600000      # nombre de fois que le calcul est répété (valeur conseillée par l'OWASP)
ESSAIS_MAX = 5           # nombre d'erreurs avant blocage
DUREE_BLOCAGE = 5 * 60   
DUREE_SESSION = 10 * 60  # l'admin est déconnecté après 10 minutes


def hasher(mot_de_passe, sel):
    """Hash a password with PBKDF2-SHA256."""
    # The repeated work slows down password guessing.
    resultat = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel.encode(), ITERATIONS)
    return resultat.hex()  


def enregistrer_mot_de_passe(mot_de_passe):
    """Save the password hash and salt to disk."""
    # A random salt gives identical passwords different hashes.
    sel = secrets.token_hex(16)
    with open(FICHIER_MDP, "w") as f:
        json.dump({"sel": sel, "hash": hasher(mot_de_passe, sel)}, f)


def initialiser_mot_de_passe(mot_de_passe):
    """Create the first password once, without overwriting an existing file."""
    if len(mot_de_passe) < 8:
        return False
    sel = secrets.token_hex(16)
    try:
        with open(FICHIER_MDP, "x", encoding="utf-8") as f:
            json.dump({"sel": sel, "hash": hasher(mot_de_passe, sel)}, f)
    except FileExistsError:
        return False
    return True


def verifier_mot_de_passe(mot_de_passe):
    """Return whether a password matches the stored hash."""
    try:
        with open(FICHIER_MDP) as f:
            donnees = json.load(f)
    except FileNotFoundError:
        return False

    hash_tape = hasher(mot_de_passe, donnees["sel"])
    # Constant-time comparison avoids timing differences between guesses.
    return hmac.compare_digest(hash_tape, donnees["hash"])


class SessionAdmin:
    """Manage admin sessions, failed attempts, and temporary lockouts."""

    def __init__(self):
        # Store session deadlines as Unix timestamps.
        self.connecte_jusqua = 0
        self.bloque_jusqua = 0
        self.nb_erreurs = 0

    def connexion(self, mot_de_passe):
        """Return 'ok', 'faux', or 'bloque'."""
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


# Run this module directly to initialize the administrator password.
if __name__ == "__main__":
    # getpass hides the password while it is entered.
    mdp = getpass("Nouveau mot de passe admin : ")
    confirmation = getpass("Confirmer : ")

    if mdp != confirmation:
        print("Les deux mots de passe sont différents")
    elif len(mdp) < 8:
        print("Il faut au moins 8 caractères")
    else:
        enregistrer_mot_de_passe(mdp)
        print("Mot de passe enregistré")
