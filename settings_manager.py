"""Persistance et API du panneau administrateur."""

import json
import re
import threading
import webview
from pathlib import Path

from settings import AI_ENDPOINTS

ROOT = Path(__file__).resolve().parent
_LOCK = threading.RLock()
_ID = re.compile(r"^[a-z0-9_-]+$")


def read_items(path):
    path = Path(path)
    if not path.exists():
        if path.name == "models.json":
            path = ROOT / "assets/json/models.default.json"
        else:
            return []
    with _LOCK:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Format invalide : {path}")
    if path.name == "models.json":
        defaults_path = ROOT / "assets/json/models.default.json"
        if defaults_path.exists():
            defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
            default_keybinds = {
                item.get("id"): item.get("keybind")
                for item in defaults
                if isinstance(item, dict) and item.get("keybind")
            }
            for item in data:
                if isinstance(item, dict) and not item.get("keybind"):
                    item["keybind"] = default_keybinds.get(item.get("id"), "")
    return data

def read_json(path, default=None):
    try:
        with open(path) as f:
            donnees = json.load(f)
    except FileNotFoundError:
        # aucun mot de passe encore creer        
        return default
    return donnees

def write_items(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_score(path, model_id, score):
    with _LOCK:
        items = read_items(path)
        for item in items:
            if item["id"] == model_id:
                item["score"] = score
                break
        write_items(path, items)

class SettingsManager:
    def __init__(self, models_file=None, roles_file=None, style_file=None, is_admin=None, on_change=None, on_style_change=None):
        self.models_file = Path(models_file or ROOT / "assets/json/models.json")
        self.roles_file = Path(roles_file or ROOT / "assets/json/personas.json")
        self.style_file = Path(style_file or ROOT / "assets/json/style.json")
        self._on_style_change = on_style_change
        self.is_admin = is_admin or (lambda: False)
        self.on_change = on_change or (lambda: None)

    def _check(self):
        if not self.is_admin():
            raise PermissionError("Session administrateur expirée.")

    def get_all_settings(self):
        self._check()
        return {"models": read_items(self.models_file), "personas": read_items(self.roles_file)}

    def _save(self, path, item, kind):
        self._check()
        if not isinstance(item, dict) or not _ID.fullmatch(str(item.get("id", ""))):
            raise ValueError("Identifiant invalide.")
        required = ("name", "icon", "persona") if kind == "persona" else ("name", "provider", "model", "image")
        if any(not isinstance(item.get(field), str) or not item[field].strip() for field in required):
            raise ValueError("Champs obligatoires manquants.")
        if kind == "model":
            if (item["provider"] not in AI_ENDPOINTS and item["provider"] != "custom") or item["provider"] == "local":
                raise ValueError("Fournisseur distant invalide.")
            if item["provider"] == "custom" and (
                not isinstance(item.get("base_url"), str)
                or not item["base_url"].startswith(("https://", "http://"))
            ):
                raise ValueError("URL de base invalide pour le fournisseur personnalisé.")
            score = item.get("score", 0)
            if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
                raise ValueError("Score invalide.")
            item = {k: item.get(k) for k in (
                "id", "name", "provider", "model", "base_url", "api_key", "image", "score", "keybind"
            )}
            item["keybind"] = str(item.get("keybind") or "").strip().lower()
            if item["provider"] != "custom":
                item["base_url"] = ""
            item["api_key"] = item["api_key"] or ""
        else:
            keybind = str(item.get("keybind") or "").strip().lower()
            item = {k: item[k] for k in ("id", "name", "icon", "persona")}
            item["keybind"] = keybind
        with _LOCK:
            data = read_items(path)
            index = next((i for i, existing in enumerate(data) if existing["id"] == item["id"]), None)
            if index is None:
                data.append(item)
            else:
                data[index] = item
            write_items(path, data)
        self.on_change()
        return True

    def return_exhibition(self):
        """Ferme la fenêtre des paramètres pour revenir sur l'exposition."""
        fenetre = webview.active_window()
        if fenetre:
            fenetre.destroy()
        return True

    def get_style(self):
        """Returns the saved style (font scale in %)."""
        try:
            data = json.loads(self.style_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        if not isinstance(data, dict) or "font_scale" not in data:
            return {"font_scale": 100}
        return data

    def save_style(self, style):
        """Saves the style and applies it live on the answering AI window."""
        scale = max(50, min(200, int(style.get("font_scale", 100))))

        # Replaces self._write_json
        self.style_file.parent.mkdir(parents=True, exist_ok=True)
        self.style_file.write_text(json.dumps({"font_scale": scale}), encoding="utf-8")

        if self._on_style_change:
            self._on_style_change(scale)
        return True

    def save_persona(self, item):
        return self._save(self.roles_file, item, "persona")

    def delete_persona(self, item_id):
        return self._delete(self.roles_file, item_id)

    def save_model(self, item):
        return self._save(self.models_file, item, "model")

    def delete_model(self, item_id):
        return self._delete(self.models_file, item_id)

    def _delete(self, path, item_id):
        self._check()
        with _LOCK:
            data = [item for item in read_items(path) if item["id"] != item_id]
            write_items(path, data)
        self.on_change()
        return True
