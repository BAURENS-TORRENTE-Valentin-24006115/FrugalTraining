import json
import os
import webview
import tts


class FrugalInterface:
    def __init__(self, models_file='assets/models.json', roles_file='assets/personas.json'):
        self.models_file = models_file
        self.roles_file = roles_file

        self.models = self._load_json(self.models_file, default=[])
        self.roles = self._load_json(self.roles_file, default=[])

        self.selected_role = self.roles[0] if self.roles else None
        self.selected_model = self.models[0] if self.models else None
        self.reponse_ia = "En attente de la réponse de l'IA..."
        self._window = None

    def _load_json(self, path, default):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default

    # --- Methods exposed to JavaScript ---

    def obtenir_donnees(self):
        """Returns public data to render the UI dynamically."""
        # Calculate current average score
        scores = [m.get('score', 0) for m in self.models if 'score' in m]
        avg_score = round(sum(scores) / len(scores)) if scores else 0

        # Note: We omit api_key when sending data to the browser for security
        safe_models = [
            {
                "id": m["id"],
                "name": m["name"],
                "image": m.get("image", "img/gemini.png"),
                "score": m.get("score", 0)
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
            "reponse_ia": self.reponse_ia
        }

    def select_role(self, role_id):
        """Called from JS when a persona button is clicked."""
        for role in self.roles:
            if role["id"] == role_id:
                self.selected_role = role
                print(f"[Persona Selected] {role['name']} (Prompt: {role['persona']})")
                break

    def select_model(self, model_id):
        """Called from JS when a model button is clicked."""
        for model in self.models:
            if model["id"] == model_id:
                self.selected_model = model
                print(f"[Model Selected] {model['name']}")
                break

    # --- Methods for Python side ---

    def get_current_prompt(self):
        """Returns the prompt/persona of the currently selected role."""
        return self.selected_role["persona"] if self.selected_role else ""

    def get_current_api_key(self):
        """Returns the private API key for the currently selected model."""
        return self.selected_model.get("api_key", "") if self.selected_model else ""

    def push_ai_response(self, text, progressive=True):
        """Pushes a response from Python directly to the UI."""
        self.reponse_ia = text
        if self._window:
            escaped_text = json.dumps(text)
            # Appel à la fonction TTS
            # tts.llm_stream_to_speech(text, "fr-CA-AntoineNeural")
            self._window.evaluate_js(f"window.displayResponse({escaped_text}, {str(progressive).lower()})")


def launch_window(http_server=False, debug=False):
    monitors = webview.screens

    screen_for_ai_1 = monitors[0]

    interface = FrugalInterface()
    window = webview.create_window(
        title="IA Frugal",
        url="assets/frugal_ai.html",
        js_api=interface,
        screen=screen_for_ai_1,
        fullscreen=True
    )
    interface._window = window

    webview.start(http_server=http_server, debug=debug)


if __name__ == '__main__':
    launch_window()