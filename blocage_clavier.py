import sys

# Numéros physiques des touches (identiques quelle que soit la langue de Windows)
CTRL = [29]
MAJ = [42, 54]

# Touches autorisées (sans compter les lettres, chiffres et symboles) : entrée, retour arrière, espace
TOUCHES_AUTORISEES = [28, 14, 57]


def activer_blocage(est_admin):
    """Bloque tout le clavier sauf les touches utiles (Windows uniquement).

    est_admin : fonction qui renvoie True si l'administrateur est connecté.
    """
    if sys.platform != "win32":
        print("[INFO] Blocage du clavier ignoré : il ne fonctionne que sous Windows")
        return

    # Importé ici car la bibliothèque keyboard n'est installée que sous Windows
    import keyboard

    # On retient si Ctrl et Maj sont enfoncées
    enfoncees = {"ctrl": False, "maj": False}

    def filtrer(event):
        """Appelée à chaque touche : True laisse passer la touche, False la bloque."""
        appuyee = event.event_type == "down"

        # Ctrl et Maj sont autorisées pour les majuscules et pour Ctrl + Maj + A
        if event.scan_code in CTRL:
            enfoncees["ctrl"] = appuyee
            return True
        if event.scan_code in MAJ:
            enfoncees["maj"] = appuyee
            return True

        # L'administrateur connecté a accès à tout le clavier (pour remplir le panel)
        if est_admin():
            return True

        if event.scan_code in TOUCHES_AUTORISEES:
            return True

        nom = (event.name or "").lower()

        # Les noms de plus d'un caractère sont des touches spéciales :
        # Windows, Alt, Tab, Échap, F1 à F12, flèches... -> bloquées
        if len(nom) != 1:
            return False

        # Avec Ctrl enfoncée, seul Ctrl + Maj + A passe (Ctrl + R, Ctrl + P... sont bloqués)
        if enfoncees["ctrl"]:
            return nom == "a" and enfoncees["maj"]

        return True

    # suppress=True : une touche pour laquelle filtrer renvoie False n'arrive jamais à Windows
    keyboard.hook(filtrer, suppress=True)
    print("[INFO] Blocage du clavier activé")