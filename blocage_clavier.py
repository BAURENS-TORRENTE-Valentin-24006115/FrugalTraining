import sys

# Touches autorisées (sans compter les lettres, chiffres et symboles)
TOUCHES_AUTORISEES = [
    "enter",       
    "backspace",   
    "space",
    "spacebar",    
]


def activer_blocage(est_admin):
    """Bloque tout le clavier sauf les touches utiles (Windows uniquement).

    est_admin : fonction qui renvoie True si l'administrateur est connecté.
    """
    if sys.platform != "win32":
        print("[INFO] Blocage du clavier ignoré : il ne fonctionne que sous Windows")
        return

    # Importé ici car la bibliothèque keyboard n'est installée que sous Windows
    import keyboard

    def filtrer(event):
        """Appelée à chaque touche : True laisse passer la touche, False la bloque."""
        # L'administrateur connecté a accès à tout le clavier (pour remplir le panel)
        if est_admin():
            return True

        nom = (event.name or "").lower()
        print("TOUCHE:", event.event_type, repr(nom), "ctrl:", keyboard.is_pressed("ctrl"), "shift:", keyboard.is_pressed("shift"))  # TEST, à enlever        

        # Shift et Ctrl sont autorisés pour les majuscules et pour Ctrl + Shift + A
        if "shift" in nom or "ctrl" in nom:
            return True

        if nom in TOUCHES_AUTORISEES:
            return True

        # Les noms de plus d'un caractère sont des touches spéciales :
        # Windows, Alt, Tab, Échap, F1 à F12, flèches... -> bloquées
        if len(nom) != 1:
            return False

        # Avec Ctrl enfoncé, seul Ctrl + Shift + A passe (Ctrl + R, Ctrl + P... sont bloqués)
        if keyboard.is_pressed("ctrl"):
            return nom == "a" and keyboard.is_pressed("shift")

        return True

    # suppress=True : une touche pour laquelle filtrer renvoie False n'arrive jamais à Windows
    keyboard.hook(filtrer, suppress=True)
    print("[INFO] Blocage du clavier activé")