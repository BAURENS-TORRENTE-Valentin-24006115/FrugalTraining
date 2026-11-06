import json
import os

import webview

class SettingsManager:
    def __init__(self, models_file='assets/json/models.json', roles_file='assets/json/personas.json',
                 style_file='assets/json/style.json', on_style_change=None):
        self.models_file = models_file
        self.roles_file = roles_file
        self.style_file = style_file
        self._on_style_change = on_style_change
        self._window_settings = None

    def _read_json(self, filepath):
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        return []

    def _write_json(self, filepath, data):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # --- Methods called from JS ---

    def get_all_settings(self):
        """Returns all models and personas to JavaScript."""
        return {
            "models": self._read_json(self.models_file),
            "personas": self._read_json(self.roles_file)
        }

    def save_persona(self, item):
        """Adds or updates a persona."""
        data = self._read_json(self.roles_file)
        existing_idx = next((i for i, x in enumerate(data) if x["id"] == item["id"]), None)
        
        if existing_idx is not None:
            data[existing_idx] = item
        else:
            data.append(item)
            
        self._write_json(self.roles_file, data)
        return True

    def delete_persona(self, item_id):
        """Removes a persona by ID."""
        data = self._read_json(self.roles_file)
        data = [x for x in data if x["id"] != item_id]
        self._write_json(self.roles_file, data)
        return True

    def save_model(self, item):
        """Adds or updates an AI model."""
        data = self._read_json(self.models_file)
        existing_idx = next((i for i, x in enumerate(data) if x["id"] == item["id"]), None)
        
        if existing_idx is not None:
            data[existing_idx] = item
        else:
            data.append(item)
            
        self._write_json(self.models_file, data)
        return True

    def delete_model(self, item_id):
        """Removes an AI model by ID."""
        data = self._read_json(self.models_file)
        data = [x for x in data if x["id"] != item_id]
        self._write_json(self.models_file, data)
        return True

    def return_exhibition(self):
        """Ferme la fenêtre des paramètres pour revenir sur l'exposition."""
        fenetre = self._window_settings or webview.active_window()
        if fenetre:
            fenetre.destroy()
        return True

    def get_style(self):
        """Returns the saved style (font scale in %)."""
        data = self._read_json(self.style_file)
        if not isinstance(data, dict) or "font_scale" not in data:
            return {"font_scale": 100}
        return data

    def save_style(self, style):
        """Saves the style and applies it live on the answering AI window."""
        scale = max(50, min(200, int(style.get("font_scale", 100))))
        self._write_json(self.style_file, {"font_scale": scale})
        if self._on_style_change:
            self._on_style_change(scale)
        return True

def launch_settings():
    settings_api = SettingsManager()

    # Create Settings Window
    window_settings = webview.create_window(
        title="Configuration - IA Frugal",
        url="assets/settings.html",
        js_api=settings_api,
        width=900,
        height=600
    )

    settings_api._window_settings = window_settings
    webview.start()

if __name__ == "__main__":
    launch_settings()