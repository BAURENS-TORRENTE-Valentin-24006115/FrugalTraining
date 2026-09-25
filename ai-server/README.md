# Serveur local

Python 3.11+ est requis pour le bootstrap. Les dépendances Beacon s'installent
dans un environnement propre à `ai-server`. Le TTS n'intervient pas ici.

## Commandes

Depuis la racine du dépôt :

```powershell
python ai-server/beacon.py --check-only
python ai-server/beacon.py --setup-only
python ai-server/beacon.py --offline --verify-only
python ai-server/beacon.py --offline
```

`--setup-only` (alias `--no-launch`) prépare les sources, le binaire, le venv,
les dépendances **et le modèle**. Il ne charge pas le modèle. `--verify-only`
démarre les deux services sur les ports configurés, génère un token puis les
arrête. Le démarrage normal vérifie aussi cette génération avant d'annoncer
que l'inférence est disponible.

`--offline` (alias `--start-only`) interdit les téléchargements et les commandes
pip. Un artefact manquant, corrompu ou incompatible avec la configuration produit
une erreur explicite. Effectuer une première préparation en ligne avant ce mode.
Une installation ancienne sans manifeste binaire doit être préparée une fois.

`--update` renouvelle explicitement les versions configurées (et le modèle).
Les sources Beacon et llama sont récupérées par archive HTTPS, sans Git installé.
Les anciennes URL terminées par `.git` restent acceptées comme URL de source.
`--force-rebuild` compile llama depuis la référence configurée ; CMake et un compilateur
C++ sont alors requis. Ces options ne peuvent pas être combinées avec `--offline`.
Sous Windows, la compilation utilise Visual Studio 2022 x64.

## Configuration

`config.json` surcharge les valeurs de `configs.py`. Les clés inconnues et les
valeurs invalides font échouer le démarrage. Les variables système `BEACON_*`,
`LLAMA_*`, `MODELS_DIR`, `TARGET_DEVICE` et les paramètres mémoire hérités ne
peuvent pas remplacer silencieusement la configuration de cette instance.
Le fichier `.env` du dépôt téléchargé n'est pas réécrit.

| Clé | Valeur par défaut | Effet |
| --- | --- | --- |
| `backend` | `auto` | Préférence `cuda`, `vulkan`, `metal`, `cpu` ou détection automatique |
| `device` | `auto` | Sélection native de llama (`auto`), ou identifiant exact tel que `Vulkan0` |
| `beacon_host` | `127.0.0.1` | Adresse d'écoute API |
| `beacon_port` | `11343` | Port API |
| `llama_port` | `null` | Choix d'un port local libre ; un entier impose un port |
| `context_size` | `4096` | Contexte envoyé à Beacon pour le modèle chargé au démarrage |
| `max_vram_ratio` | `0.90` | Fraction maximale de la VRAM totale |
| `vram_margin_mib` | `512` | Ancienne option conservée pour compatibilité ; non appliquée par Beacon |
| `startup_timeout_seconds` | `300` | Délai d’attente du bootstrap pour l’API, puis pour le modèle |
| `idle_timeout_seconds` | `300` | Délai de veille géré par Beacon ; `0` désactive la veille |
| `llama_release_repo` | dépôt MAIA | Dépôt réellement utilisé dans l'URL des binaires |
| `llama_release_tag` | `v1.0.0` | Version du binaire |
| `beacon_tag` | `v1.0.0` | Ref exact des sources Beacon |
| `llama_tag` | `main` | Ref des sources pour la compilation |
| `default_model_revision` | `main` | Révision Hugging Face du modèle |
| `default_model_sha256` | `null` | SHA256 attendu du modèle, si fourni |
| `binary_sha256` | `{}` | Mapping nom d'archive → SHA256 attendu |

Le template d'URL binaire accepte `{repo}`, `{tag}`, `{os}`, `{arch}`, `{backend}`
et `{ext}`. Un template personnalisé contenant son propre dépôt le remplace.
L'ancienne clé `llama_releases_repo` est acceptée comme alias, mais les deux
orthographes ne peuvent pas être présentes ensemble.

Le backend réellement installé est enregistré dans `state.json`. CUDA est essayé
avant Vulkan puis CPU, avec validation de l'exécutable **et** des périphériques
à chaque étape. Un GPU explicitement choisi doit exister ; sa disparition ne
provoque pas une sélection silencieuse d'un autre GPU.
Si un CPU est en cache alors qu'un GPU est recommandé, un démarrage en ligne
réessaie les binaires GPU avant de réutiliser le CPU. Les échecs de sonde CUDA
affichent maintenant la sortie brute de `--version` et `--list-devices`.

Windows x64 est pris en charge. Windows ARM64 échoue explicitement avant toute
réparation de DLL ; il n'est pas encore pris en charge. Les chemins Linux/macOS
x64/ARM64 existent mais nécessitent une validation sur les machines concernées.

## Reprise et propriété des ressources

Les sources et binaires sont préparés dans un dossier temporaire puis validés
avant publication. Les versions précédentes sont conservées dans des dossiers
`.previous-*`, et un venv non fonctionnel est conservé avant recréation. Les
sources modifiées localement sont conservées dans ces sauvegardes lors d'une
mise à jour. Les téléchargements échoués ne remplacent jamais le fichier existant.
Sous Windows, si un antivirus ou un indexeur verrouille momentanément le dossier
d'extraction après la sonde du binaire, la publication réessaie puis copie les
fichiers dans un nouveau dossier avant de les publier. L'ancien dossier reste
restaurable si cette opération échoue.

Un verrou système empêche deux setups ou deux serveurs de partager simultanément
la même installation. Il se libère aussi après un crash. Le bootstrap refuse un
port occupé et termine son propre arbre de processus à l’arrêt.
Attention : le tag Beacon installé contient encore une fonction qui arrête tous
les processus `llama-server` par nom. Les installations simultanées ne sont donc
pas isolées ; cette limitation doit être corrigée dans MAIA-Beacon.

Les checksums locaux détectent les changements accidentels ; ils ne prouvent pas
l'origine d'un premier téléchargement. Pour une installation reproductible,
renseigner les SHA256 attendus et des références de source immuables plutôt que `main`.
Les fichiers GGUF locaux sont contrôlés puis adoptés ; la génération réelle
détecte les incompatibilités que le seul en-tête ne peut pas révéler.
## Rôle de ai-server et de MAIA-Beacon

`beacon.py` prépare les binaires, le modèle et le venv, puis lance directement
`deps/MAIA-Beacon/main.py`. `maia_setup.py` transmet la configuration par
l’environnement du processus. Aucune fonction ni route de Beacon n’est remplacée.

MAIA-Beacon gère le chargement du modèle, l’optimisation mémoire, le proxy HTTP
et la veille. `ai-server` attend `/v1/models`, envoie le modèle et `context_size`
à `/api/select`, attend son état `running` dans `/api/status`, puis demande une
génération d’un token. Le démarrage n’est validé que si cette génération réussit.

`context_size` concerne le chargement initial, pas une limite globale de l’API.
`device` est transmis via `LLAMA_ARG_DEVICE` et `max_vram_ratio` via
`MAX_VRAM_PERCENT`. La sélection automatique et la télémétrie dépendent de Beacon
et de llama ; le choix du GPU le plus libre n’est plus imposé localement.
`vram_margin_mib` reste accepté pour les anciens fichiers de configuration mais
n’est pas appliqué ; un message au lancement le rappelle.

Les délais internes, les reprises après manque de mémoire, le streaming et la
concurrence suivent désormais le comportement du tag Beacon installé. Son délai
de chargement interne est actuellement de 180 secondes ; augmenter le délai du
bootstrap ne change pas cette limite. Les corrections de ces comportements
appartiennent au dépôt MAIA-Beacon.