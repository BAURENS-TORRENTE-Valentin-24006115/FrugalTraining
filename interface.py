import json
import os
import webview
import tts
import admin_auth
import settings_manager


class FrugalInterface:
    def __init__(self, models_file='assets/json/models.json', roles_file='assets/json/personas.json'):
        self.models_file = models_file
        self.roles_file = roles_file

        self.models = self._load_json(self.models_file, default=[])
        self.roles = self._load_json(self.roles_file, default=[])

        self.selected_role = self.roles[0] if self.roles else None
        self.selected_model = self.models[0] if self.models else None
        self.reponse_ia_frugal = "En attente de la réponse de l'IA..."
        self.reponse_ia_repondante = "En attente de la réponse de l'IA..."
        self._frugal_window = None
        self._answering_window = None
        self._admin = admin_auth.SessionAdmin()        

    def _load_json(self, path, default):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default

    # --- Methods exposed to JavaScript ---

    def recharger_donnees(self):
        """Re-loads JSON from disk to catch updates made by the Admin Settings."""
        self.models = self._load_json(self.models_file, default=[])
        self.roles = self._load_json(self.roles_file, default=[])

    def obtenir_donnees(self):
        """Returns public data to render the UI dynamically."""

        self.recharger_donnees()

        # Calculate current average score
        scores = [m.get('score', 0) for m in self.models if 'score' in m]
        avg_score = round(sum(scores) / len(scores)) if scores else 0

        safe_models = [
            {
                "id": m["id"],
                "name": m["name"],
                "image": m.get("image", "img/models/gemini.png"),
                "score": m.get("score", 0),
                "keybind": m.get("keybind", "")
            }
            for m in self.models
        ]

        return {
            "roles": self.roles,
            "models": safe_models,
            "selected_role_id": self.selected_role["id"] if self.selected_role else None,
            "selected_model_id": self.selected_model["id"] if self.selected_model else None,
            "current_role_name": self.selected_role["name"] if self.selected_role else "",
            "average_score": f"{avg_score}/100",
            "reponse_ia_frugal": self.reponse_ia_frugal,
            "reponse_ia_repondante": self.reponse_ia_repondante
        }

    def select_role(self, role_id):
        """Called from JS when a persona button is clicked."""
        for role in self.roles:
            if role["id"] == role_id:
                self.selected_role = role
                print(f"[Persona Selected] {role['name']} (Prompt: {role['persona']})")
                if self._frugal_window:
                    image_url = role.get("icon", "")
                    self._frugal_window.evaluate_js(f"window.updateSelectedPersona('{image_url}', '{role['name']}')")
                break

    def select_model(self, model_id):
        """Called from JS when a model button is clicked."""
        for model in self.models:
            if model["id"] == model_id:
                self.selected_model = model
                print(f"[Model Selected] {model['name']}")
                if self._answering_window:
                    image_url = model.get("image", "")
                    self._answering_window.evaluate_js(f"window.updateLogo('{image_url}')")
                break

    def verifier_mot_de_passe_admin(self, mot_de_passe):
        """Appelée par admin.js quand on clique sur Valider. Renvoie "ok", "faux" ou "bloque"."""
        return self._admin.connexion(mot_de_passe)

    def est_admin(self):
        return self._admin.est_connecte()

    def deconnecter_admin(self):
        self._admin.deconnexion()   

    def ouvrir_panel_admin(self):
        """Ouvre la fenêtre des paramètres, uniquement si l'admin est connecté."""
        if not self._admin.est_connecte():
            return False
        panel = settings_manager.SettingsManager()
        webview.create_window(
            title="Configuration - IA Frugal",
            url="assets/settings.html",
            js_api=panel,
            width=900,
            height=600
        )
        return True     

    # --- Methods for Python side ---

    def get_current_prompt(self):
        """Returns the prompt/persona of the currently selected role."""
        return self.selected_role["persona"] if self.selected_role else ""

    def get_current_api_key(self):
        """Returns the private API key for the currently selected model."""
        return self.selected_model.get("api_key", "") if self.selected_model else ""

    def push_frugal_ai_response(self, text, progressive=True):
        """Pushes a response from Python directly to the UI."""
        self.reponse_ia_frugal = text
        if self._frugal_window:
            escaped_text = json.dumps(text)
            # Appel à la fonction TTS
            # tts.llm_stream_to_speech(text, "fr-CA-AntoineNeural")
            self._frugal_window.evaluate_js(f"window.displayResponse({escaped_text}, {str(progressive).lower()})")

    def push_answering_ai_response(self, text, progressive=True):
        """Pushes a response from Python directly to the UI."""
        self.reponse_ia_repondante = text
        if self._answering_window:
            escaped_text = json.dumps(text)
            self._answering_window.evaluate_js(f"window.displayResponse({escaped_text}, {str(progressive).lower()})")


def launch_windows(http_server=False, debug=False):
    interface = FrugalInterface()
    interface._frugal_window = webview.create_window(
        title="IA Frugal",
        url="assets/frugal_ai.html",
        js_api=interface,
        fullscreen=True
    )
    interface._answering_window = webview.create_window(
        title="IA Repondante",
        url="assets/answering_ai.html",
        js_api=interface,
        fullscreen=True
    )

    webview.start(http_server=http_server, debug=debug)


if __name__ == '__main__':
    launch_windows()