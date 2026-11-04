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
        self.reponse_ia_repondante = """Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aliquam consequat non ante et accumsan. Interdum et malesuada fames ac ante ipsum primis in faucibus. Quisque placerat diam in orci consectetur, ac aliquet dolor placerat. Donec luctus gravida arcu, sed vestibulum urna placerat ut. Nullam vestibulum, eros tincidunt accumsan condimentum, dolor neque sodales diam, nec cursus mi massa ac elit. Integer et venenatis risus. Integer erat est, consectetur a interdum vulputate, interdum a lorem. Phasellus commodo, velit ac maximus elementum, massa nisl ultricies tellus, eget gravida nulla est ac tellus. Morbi a varius magna, laoreet bibendum nulla. Class aptent taciti sociosqu ad litora torquent per conubia nostra, per inceptos himenaeos. Nunc eget eleifend turpis, sit amet blandit sem. Etiam neque nisl, lacinia in tristique tempor, semper at ex. Sed non ipsum mollis elit gravida tempus eu at risus. Integer condimentum mattis bibendum. Sed tristique ex sed tristique cursus. Proin vestibulum tempor mattis. Pellentesque habitant morbi tristique senectus et netus et malesuada fames ac turpis egestas. Ut at congue tortor, eu laoreet tortor. Quisque vel ex et turpis tempus dignissim at hendrerit sem. Nam iaculis sed purus nec semper. Nam mattis accumsan massa ut luctus. Pellentesque pharetra pellentesque turpis, bibendum lacinia ligula dignissim quis. Suspendisse non tortor ut elit euismod dictum id quis orci. Duis aliquet dolor lectus, nec luctus erat volutpat at. Quisque lorem ante, consectetur ut felis eget, finibus condimentum mi. Pellentesque ac ipsum a diam condimentum congue eu et eros. Suspendisse luctus velit eu nulla bibendum viverra. Phasellus pharetra vulputate tellus, ut accumsan neque vulputate in. Donec elementum placerat aliquet. Etiam egestas justo quam, ut vulputate ligula mollis a. Maecenas fermentum nibh arcu, ac tincidunt mi pretium in. Nam faucibus felis sit amet scelerisque luctus. Sed fringilla viverra lobortis. Vestibulum lobortis vestibulum lacus, id suscipit turpis tempus nec. Pellentesque lacinia arcu sed dolor ultrices, eget ornare magna laoreet. Donec vitae porta arcu. In dignissim justo sodales arcu posuere semper. Mauris pharetra neque ac posuere consectetur. Maecenas tincidunt dolor at ligula tincidunt, sed lacinia risus facilisis. Vestibulum ultricies velit et purus varius, sed dictum urna ultrices. Maecenas commodo ultrices pretium. Cras a lacus diam. Suspendisse odio erat, dapibus sit amet auctor quis, laoreet ut elit. Praesent sapien neque, consectetur vitae nulla at, malesuada dictum nisl. Donec lobortis vitae purus eu aliquet. Quisque mauris ante, sodales eu vulputate id, ornare in mi. Class aptent taciti sociosqu ad litora torquent per conubia nostra, per inceptos himenaeos. Duis eget orci id urna malesuada vestibulum consectetur ac nisl. Sed vitae orci eget justo malesuada bibendum ac ultrices odio. Cras vitae eleifend odio. Suspendisse facilisis dictum rutrum. Sed molestie nulla justo, eu blandit sem rhoncus vitae. Nulla mollis, nibh at maximus lobortis, erat nisl viverra magna, nec sagittis libero lacus sit amet velit. Proin tortor libero, malesuada ac est id, vehicula pulvinar dolor. Nulla nunc elit, congue vel libero vitae, faucibus dignissim ex. Fusce ut elit vulputate, venenatis leo et, faucibus orci. Sed et pulvinar ante. Phasellus diam neque, convallis aliquam porta ut, tincidunt eget nisi. Pellentesque pulvinar purus ornare lacus interdum condimentum. Nunc vitae libero ipsum. Ut dui velit, feugiat ut felis ut, convallis venenatis magna. Integer sit amet enim cursus nibh pulvinar blandit. Suspendisse vitae sollicitudin lorem. Mauris et purus lectus. Praesent sed erat venenatis, consectetur nisl sed, consectetur diam. Nullam tortor est, rhoncus id posuere at, porta ut mauris. Proin sagittis fringilla viverra. Quisque eleifend diam eu purus feugiat, suscipit pellentesque libero dignissim. Sed dapibus ex a aliquet feugiat. Duis sagittis orci at erat molestie auctor. Quisque augue urna, mattis tincidunt luctus ac, tempus ac arcu. Sed sagittis dictum felis in mattis. Donec a ante tristique, viverra mi vel, rhoncus tortor. Pellentesque ullamcorper ornare augue, ut pharetra lorem placerat sed. Curabitur sed odio congue, sollicitudin lorem id, consequat lorem. Vivamus non pretium urna. Cras diam risus, vestibulum in diam mattis, placerat convallis dui. Sed feugiat imperdiet justo maximus sodales. Suspendisse volutpat velit purus, dictum molestie elit maximus at. Donec luctus justo ac magna cursus finibus nec et enim. Ut eleifend mi eu sem iaculis vestibulum. Nam fermentum auctor tristique. Maecenas id nisi quis urna consequat egestas at a mi. Etiam tempus lorem metus, non dignissim tellus tempus vel. Mauris condimentum nibh non dui lacinia vulputate. Praesent id arcu eu nisl consectetur pharetra ut non lectus. Fusce dictum efficitur massa ut faucibus. Quisque bibendum egestas sodales. Vivamus cursus molestie quam sed tempus. Interdum et malesuada fames ac ante ipsum primis in faucibus. Nulla facilisi. Sed ut dapibus nunc, ut dictum ligula."""
        self._frugal_window = None
        self._answering_window = None
        self._admin = admin_auth.SessionAdmin()        

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

        safe_models = [
            {
                "id": m["id"],
                "name": m["name"],
                "image": m.get("image", "img/models/gemini.png"),
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
            "reponse_ia_frugal": self.reponse_ia_frugal,
            "reponse_ia_repondante": self.reponse_ia_repondante
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
    monitors = webview.screens
    print(f"[INFO] Detected {len(monitors)} monitor(s): {monitors}")
    if len(monitors) < 2:
        print("[WARNING] Less than 2 monitors detected. Both windows will open on the primary monitor.")
        monitors = [monitors[0], monitors[0]]
    screen_for_ai_1 = monitors[0]
    screen_for_ai_2 = monitors[1]

    interface = FrugalInterface()
    interface._frugal_window = webview.create_window(
        title="IA Frugal",
        url="assets/frugal_ai.html",
        js_api=interface,
        screen=screen_for_ai_1,
        fullscreen=True
    )
    interface._answering_window = webview.create_window(
        title="IA Repondante",
        url="assets/answering_ai.html",
        js_api=interface,
        screen=screen_for_ai_2,
        fullscreen=True
    )

    webview.start(http_server=http_server, debug=debug)


if __name__ == '__main__':
    launch_windows()