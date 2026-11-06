# Serveur IA local

Ce dossier prépare et lance MAIA-Beacon avec `llama.cpp` et Ministral. Beacon
gère le chargement du modèle et expose son API locale. Python 3.11 ou plus récent
est nécessaire.

## Démarrage

Depuis la racine du dépôt, prépare une première fois les composants avec accès
Internet :

```powershell
python ai-server/beacon.py --setup-only
```

Puis démarre le serveur avec les fichiers déjà installés :

```powershell
python ai-server/beacon.py --offline
```

Le serveur reste actif jusqu’à son arrêt. Sans `--offline`, le script peut
télécharger les composants manquants.

## Commandes utiles

| Commande | Usage |
| --- | --- |
| `python ai-server/beacon.py --check-only` | Affiche la configuration et le matériel détecté, sans démarrer le serveur. |
| `python ai-server/beacon.py --setup-only` | Installe ou prépare le binaire, Beacon, l’environnement Python et le modèle, sans lancer l’API. Alias : `--no-launch`. |
| `python ai-server/beacon.py --offline` | Lance le serveur avec les composants locaux uniquement. Alias : `--start-only`. |
| `python ai-server/beacon.py --offline --verify-only` | Démarre les services, vérifie une vraie génération, puis les arrête. |
| `python ai-server/beacon.py --update` | Met à jour les composants selon les versions configurées. |
| `python ai-server/beacon.py --force-rebuild` | Compile llama.cpp depuis les sources ; CMake et un compilateur C++ sont requis. |

`--offline` ne peut pas être combiné avec `--update` ou `--force-rebuild`.
`--setup-only` prépare les composants, mais ne charge pas le modèle en mémoire.

## Configuration

Les réglages se trouvent dans [`config.json`](config.json). Ce fichier remplace
les valeurs par défaut définies dans `configs.py`. Une clé inconnue ou une valeur
invalide fait échouer le démarrage.

| Réglage | Valeur par défaut | Rôle |
| --- | --- | --- |
| `backend` | `auto` | Backend de calcul : détection automatique, CUDA, Vulkan, Metal ou CPU. |
| `device` | `auto` | Périphérique transmis à llama.cpp, par exemple `Vulkan0`. |
| `beacon_host` / `beacon_port` | `127.0.0.1` / `11343` | Adresse et port de l’API Beacon. |
| `llama_port` | `null` | Port de llama.cpp ; `null` laisse choisir un port libre. |
| `context_size` | `4096` | Taille de contexte demandée au chargement initial du modèle. |
| `max_vram_ratio` | `0.90` | Part maximale de VRAM communiquée à Beacon. |
| `startup_timeout_seconds` | `300` | Délai maximal d’attente du démarrage et du chargement. |
| `idle_timeout_seconds` | `300` | Délai avant la mise en veille gérée par Beacon ; `0` la désactive. |
| `beacon_tag` | `v1.0.0` | Version des sources MAIA-Beacon. |
| `llama_release_tag` | `v1.0.0` | Version du binaire llama.cpp précompilé. |

Le modèle par défaut est défini par `default_model_repo`, `default_model_file`
et `default_model_revision` dans `configs.py`. `default_model_sha256` et
`binary_sha256` permettent de renseigner les sommes de contrôle attendues.

## Démarrage du modèle

`beacon.py` prépare les composants, puis lance `deps/MAIA-Beacon/main.py` sans
remplacer ses routes ou fonctions. Le script attend que l’API réponde, demande
à Beacon de charger le modèle et valide le démarrage avec une génération courte.
Le service n’est annoncé prêt qu’après cette vérification.

Beacon pilote le chargement du modèle, l’utilisation de la mémoire, le proxy HTTP
et la veille. `context_size` concerne le chargement initial ; les requêtes API
peuvent avoir leurs propres paramètres de génération.

## Compatibilité et limites

Windows x64 est la plateforme actuellement prise en charge. Windows ARM64 n’est
pas pris en charge. Les chemins Linux et macOS existent, mais ne sont pas encore
validés sur toutes les configurations.

La version Beacon installée (`v1.0.0`) peut arrêter les processus
`llama-server` par leur nom. Plusieurs installations Beacon ne sont donc pas
isolées et ne doivent pas être lancées en parallèle.
