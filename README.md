# FrugalTraining

Application à deux fenêtres : un modèle distant répond au questionnaire, puis le modèle local MAIA/Ministral évalue sa réponse. La fenêtre « IA Frugal » affiche l'évaluation et les scores ; la fenêtre « IA Répondante » affiche la réponse distante.

## Installation

```powershell
python -m pip install -r requirements.txt
python main.py
```

Au premier lancement, ouvrez l'administration avec **Ctrl + Maj + A** et créez un mot de passe de huit caractères minimum. Le panneau permet de gérer les personas, les fournisseurs et les identifiants de modèles. Choisissez un modèle et un persona dans la fenêtre Frugal, puis cliquez sur **Lancer un cycle**. Les sélections sont bloquées pendant le cycle.

Les modèles proposés se trouvent dans `assets/json/models.default.json`. Les modifications et scores sont enregistrés dans `assets/json/models.json`, ignoré par Git. Vous pouvez ajouter un modèle via un endpoint compatible OpenAI (`/chat/completions`). Les clés API peuvent être saisies dans l'administration ou fournies dans `.env` avec `MISTRAL_API`, `GEMINI_API` et `DEEPSEEK_API`. Un modèle personnalisé demande sa propre clé dans l'administration. `admin_password.json` est également local et ignoré par Git.

Le serveur local est lancé automatiquement lors du premier cycle. Il faut que ses dépendances et son modèle soient installés selon `ai-server/README.md`. L'interface peut s'ouvrir et les paramètres peuvent être édités sans serveur ni clé API ; le cycle indique l'erreur si une dépendance manque.

L'ancien mode console reste disponible avec `python main.py --cli`. Pour vérifier le pont de configuration sans accès réseau :

```powershell
python -m unittest discover -s tests -v
```
