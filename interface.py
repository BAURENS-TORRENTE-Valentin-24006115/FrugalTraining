"""Pont entre les fenêtres pywebview, la configuration et le workflow."""

import asyncio
import json
import re
import threading
from pathlib import Path

import admin_auth
import settings_manager
from settings import api_key_for, load_env_file

ROOT = Path(__file__).resolve().parent


class FrugalInterface:
    def __init__(self, models_file=None, roles_file=None, style_file=None, webview_module=None):
        self.models_file = Path(models_file or ROOT / "assets/json/models.json")
        self.roles_file = Path(roles_file or ROOT / "assets/json/personas.json")
        self.style_file = Path(style_file or ROOT / "assets/json/style.json")
        self.webview = webview_module
        self._admin = admin_auth.SessionAdmin()
        self._frugal_window = None
        self._answering_window = None
        self._settings_window = None
        self._cycle_lock = threading.Lock()
        self._running = False
        self._active_model_id = None
        self._score_recorded_for_cycle = False
        self.status = "Prêt à lancer un cycle."
        self.reponse_ia_frugal = "En attente de l'évaluation..."
        self.reponse_ia_repondante = "En attente de la réponse du modèle..."
        self.selected_role_id = None
        self.selected_model_id = None
        self.reload_settings()

    def reload_settings(self):
        self.roles = settings_manager.read_items(self.roles_file)
        self.models = settings_manager.read_items(self.models_file)
        self.style = settings_manager.read_json(self.style_file, default={"font_scale": 100})
        role_ids = {item["id"] for item in self.roles}
        model_ids = {item["id"] for item in self.models}
        if self.selected_role_id not in role_ids:
            self.selected_role_id = self.roles[0]["id"] if self.roles else None
        if self.selected_model_id not in model_ids:
            self.selected_model_id = self.models[0]["id"] if self.models else None
        self._broadcast()

    def _selected(self, items, item_id):
        return next((item for item in items if item["id"] == item_id), None)

    def _emit_js(self, window, function, *args):
        if window is not None:
            try:
                window.evaluate_js(f"window.{function}({', '.join(json.dumps(a, ensure_ascii=False) for a in args)})")
            except Exception as exc:
                print(f"[UI] {function}: {exc}")

    def _broadcast(self):
        data = self.obtenir_donnees()
        self._emit_js(self._frugal_window, "renderData", data)
        self._emit_js(self._answering_window, "renderData", data)

    def obtenir_donnees(self):
        safe_models = [{key: model.get(key) for key in ("id", "name", "image", "score", "keybind")}
                       for model in self.models]
        scores = [model["score"] for model in safe_models if isinstance(model.get("score"), (int, float))]
        role = self._selected(self.roles, self.selected_role_id)
        safe_roles = [{key: item.get(key) for key in ("id", "name", "icon", "keybind")}
                      for item in self.roles]
        return {
            "roles": safe_roles,
            "models": safe_models,
            "selected_role_id": self.selected_role_id,
            "selected_model_id": self.selected_model_id,
            "current_role_name": role["name"] if role else "",
            "current_role_icon": role.get("icon", "") if role else "",
            "average_score": f"{round(sum(scores) / len(scores)) if scores else 0}/100",
            "reponse_ia_frugal": self.reponse_ia_frugal,
            "reponse_ia_repondante": self.reponse_ia_repondante,
            "font_scale": self.style.get("font_scale", 100),
            "status": self.status,
            "running": self._running,
        }

    def select_role(self, role_id):
        if self._running or not self._selected(self.roles, role_id):
            return False
        self.selected_role_id = role_id
        self.reponse_ia_frugal = "En attente de l'évaluation..."
        self.reponse_ia_repondante = "En attente de la réponse du modèle..."
        self.status = "Prêt à lancer un cycle."
        self._broadcast()
        return True

    def select_model(self, model_id):
        if self._running or not self._selected(self.models, model_id):
            return False
        self.selected_model_id = model_id
        self.reponse_ia_frugal = "En attente de l'évaluation..."
        self.reponse_ia_repondante = "En attente de la réponse du modèle..."
        result = self.lancer_cycle()
        if not result["ok"]:
            self.status = result["message"]
        self._broadcast()
        return True

    def verifier_mot_de_passe_admin(self, password):
        return self._admin.connexion(password)

    def est_admin(self):
        return self._admin.est_connecte()

    def deconnecter_admin(self):
        self._admin.deconnexion()
        if self._settings_window:
            self._settings_window.destroy()
            self._settings_window = None

    def admin_configure(self):
        return admin_auth.password_exists()

    def initialiser_admin(self, password, confirmation):
        if password != confirmation or len(password) < 8:
            return False
        if not admin_auth.initialiser_mot_de_passe(password):
            return False
        return self._admin.connexion(password) == "ok"

    def ouvrir_panel_admin(self):
        if not self.est_admin():
            return False
        if self._settings_window:
            self._settings_window.show()
            return True
        panel = settings_manager.SettingsManager(
            self.models_file, self.roles_file,
            is_admin=self.est_admin, on_change=self.reload_settings, on_style_change=self.appliquer_taille_police
        )
        self._settings_window = self.webview.create_window(
            "Configuration - IA Frugal", str(ROOT / "assets/settings.html"),
            js_api=panel, width=900, height=650,
        )
        self._settings_window.events.closed += self._settings_closed
        return True

    def appliquer_taille_police(self, scale):
        """Applique la taille de police sur la fenêtre de l'IA répondante."""
        self.style["font_scale"] = scale
        if self._answering_window:
            self._answering_window.evaluate_js(f"window.setFontScale({int(scale)})")

    def apply_font_size(self, scale):
        """Applique la taille de police sur la fenêtre de l'IA répondante."""
        self.style["font_scale"] = scale
        if self._answering_window:
            self._answering_window.evaluate_js(f"window.setFontScale({int(scale)})")

    # --- Methods for Python side ---

    def get_current_prompt(self):
        """Returns the prompt/persona of the currently selected role."""
        return self.selected_role["persona"] if self.selected_role else ""

    def _settings_closed(self, *args):
        self._settings_window = None

    def push_frugal_ai_response(self, text, progressive=False):
        self.reponse_ia_frugal = text
        self._emit_js(self._frugal_window, "displayResponse", text, progressive)

    def push_answering_ai_response(self, text, progressive=False):
        self.reponse_ia_repondante = text
        self._emit_js(self._answering_window, "displayResponse", text, progressive)

    def _workflow_event(self, event, value):
        if event == "remote":
            self.push_answering_ai_response(value)
        elif event == "evaluation_chunk":
            self.push_frugal_ai_response(value, progressive=False)
        elif event == "score":
            self._record_cycle_score(value)
        elif event == "evaluation":
            self.push_frugal_ai_response(value)
            match = re.search(r"Note\s*:\s*(\d{1,3})\s*/\s*100", value, re.I)
            if match:
                self._record_cycle_score(int(match.group(1)))
        elif event == "status":
            self.status = value
            self._broadcast()

    def _record_cycle_score(self, mark):
        if self._score_recorded_for_cycle or self._active_model_id is None:
            return False
        model = self._selected(self.models, self._active_model_id)
        if not model:
            return False
        score = min(100, max(0, int(mark)))
        settings_manager.update_score(self.models_file, model["id"], score)
        self._score_recorded_for_cycle = True
        self.reload_settings()
        return True

    def lancer_cycle(self):
        with self._cycle_lock:
            if self._running:
                return {"ok": False, "message": "Un cycle est déjà en cours."}
            model = self._selected(self.models, self.selected_model_id)
            role = self._selected(self.roles, self.selected_role_id)
            if not model or not role:
                return {"ok": False, "message": "Ajoutez un modèle et un persona dans l'administration."}
            provider = model.get("provider") or model["id"]
            key = model.get("api_key") or api_key_for(provider, load_env_file())
            if not key:
                return {"ok": False, "message": f"Clé API manquante pour {model['name']}."}
            self._running = True
            self._active_model_id = model["id"]
            self._score_recorded_for_cycle = False
            self.status = "Démarrage du cycle..."
            self.push_frugal_ai_response("En attente de l'évaluation...")
            self.push_answering_ai_response("En attente de la réponse du modèle...")
            self._broadcast()

        def worker():
            try:
                from workflow import run_cycle, start_ai_server
                self._workflow_event("status", "Démarrage du serveur local...")
                start_ai_server()
                asyncio.run(run_cycle(
                    load_env_file(), model_config=model, persona_prompt=role["persona"],
                    persona_name=role["name"],
                    event_callback=self._workflow_event,
                ))
            except Exception as exc:
                self._workflow_event("status", f"Erreur : {exc}")
            finally:
                with self._cycle_lock:
                    self._running = False
                    self._active_model_id = None
                self._broadcast()

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "message": self.status}


def launch_windows(http_server=False, debug=False):
    import webview

    interface = FrugalInterface(webview_module=webview)
    screens = list(webview.screens)
    first = screens[0] if screens else None
    second = screens[1] if len(screens) > 1 else first
    two_screens = len(screens) > 1
    window_options = {"fullscreen": two_screens}
    if first and not two_screens:
        half_width = max(500, first.width // 2)
        window_options.update(width=half_width, height=max(500, first.height - 80))
    interface._frugal_window = webview.create_window(
        "IA Frugal", str(ROOT / "assets/frugal_ai.html"),
        js_api=interface, screen=first, x=first.x if first and not two_screens else None,
        y=first.y if first and not two_screens else None, **window_options,
    )
    interface._answering_window = webview.create_window(
        "IA Répondante", str(ROOT / "assets/answering_ai.html"),
        js_api=interface, screen=second,
        x=first.x + half_width if first and not two_screens else None,
        y=first.y if first and not two_screens else None, **window_options,
    )
    webview.start(http_server=http_server, debug=debug)


if __name__ == "__main__":
    launch_windows()
