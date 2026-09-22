"""
Main Execution Script for FrugalTraining
Orchestrates Local AI Server startup, Questionnaire flow, Cloud/Local Distant Model interactions,
and TTS evaluation output.
"""

import sys
import os
import time
import asyncio
import threading
import urllib.request
import subprocess
from pathlib import Path
from typing import Optional, AsyncGenerator

from ai import AI
from tts import llm_stream_to_speech, speak_static_text

# Force UTF-8 stdout on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==========================================
# CONFIGURATION CONSTANTS
# ==========================================
# Modèle distant à utiliser : "deepseek", "mistral", "gemini", ou "local".
# Si défini sur "local" ou None, utilise par défaut le serveur IA local (Ministral sur AI SERVER).
DISTANT_MODEL_PROVIDER: str = "mistral"

# Configuration de la voix TTS
TTS_VOICE: str = "fr-FR-DeniseNeural"

# Chemin vers le Questionnaire PDF
QUESTIONNAIRE_PATH: Path = Path(__file__).resolve().parent / "Questionnaire.pdf"


def is_local_server_ready(host: str = "127.0.0.1", port: int = 11343) -> bool:
    """Vérifie si le serveur IA local MAIA Beacon / llama-cpp est opérationnel."""
    url = f"http://{host}:{port}/v1/models"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FrugalTraining-Healthcheck"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_ai_server() -> Optional[subprocess.Popen]:
    """Lance le serveur IA local s'il n'est pas déjà actif."""
    if is_local_server_ready():
        print("[+] Serveur IA local (MAIA Beacon) déjà actif et prêt.")
        return None

    print("[+] Lancement du serveur IA local en arrière-plan (ai-server/beacon.py)...")
    beacon_script = Path(__file__).resolve().parent / "ai-server" / "beacon.py"
    
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    proc = subprocess.Popen([sys.executable, str(beacon_script)], env=env)

    print("[+] Attente de la disponibilité du serveur IA local...")
    for _ in range(40):
        if is_local_server_ready():
            print("\n[OK] Serveur IA local opérationnel !")
            return proc
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1.5)

    print("\n[!] Attention : Le serveur n'a pas répondu dans le temps imparti. Poursuite de l'exécution...")
    return proc


def load_questionnaire(pdf_path: Path) -> str:
    """
    Extrait le texte du fichier Questionnaire.pdf pour l'envoyer aux IA.
    Les endpoints HTTP standard (/v1/chat/completions) reçoivent le texte extrait du PDF.
    """
    if not pdf_path.exists():
        print(f"[!] Fichier {pdf_path} introuvable.")
        return ""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        text = "\n".join([page.extract_text() or "" for page in reader.pages])
        return text.strip()
    except Exception as e1:
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(str(pdf_path))
            text = "\n".join([page.extract_text() or "" for page in reader.pages])
            return text.strip()
        except Exception:
            print(f"[!] Erreur lors de la lecture du Questionnaire PDF : {e1}")
            return ""


async def sync_stream_to_async_gen(sync_gen) -> AsyncGenerator[str, None]:
    """Exécute le flux synchrone dans un thread d'arrière-plan pour laisser l'event loop asyncio libre d'animer le spinner."""
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def producer():
        try:
            for item in sync_gen:
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=producer, daemon=True).start()

    while True:
        item = await queue.get()
        if item is None:
            break
        if isinstance(item, Exception):
            raise item
        yield item


async def run_cycle():
    """Exécute un cycle complet d'évaluation."""
    questionnaire_text = load_questionnaire(QUESTIONNAIRE_PATH)
    if not questionnaire_text:
        print("[!] Impossible de charger le questionnaire. Cycle interrompu.")
        return

    # 1. Texte statique et TTS initial
    phrase_initiale = "Je peux te poser une question ?"
    print(f"\n[TTS] Prononciation : '{phrase_initiale}'")
    try:
        await speak_static_text(phrase_initiale, voice=TTS_VOICE)
    except Exception as e:
        print(f"[!] Avertissement TTS statique : {e}")

    # 2. Choix de l'IA distante (utilisant la classe AI)
    provider_distant = DISTANT_MODEL_PROVIDER if DISTANT_MODEL_PROVIDER else "mistral"
    print(f"\n[+] Instanciation de l'IA distante ({provider_distant.upper()})...")
    client_distant = AI(provider=provider_distant)

    prompt_distant = (
        f"{phrase_initiale}\n\n"
        f"Voici le questionnaire sur le frugalisme :\n{questionnaire_text}\n\n"
        "Merci de répondre de manière claire et détaillée."
    )

    print(f"[+] Envoi du questionnaire à l'IA distante ({client_distant.model})...")
    print("\n--- Réponse de l'IA Distante ---")
    
    reponse_distante = ""
    try:
        for token in client_distant.stream_chat(prompt_distant):
            print(token, end="", flush=True)
            reponse_distante += token
    except Exception as e:
        print(f"\n[!] Erreur lors de la génération par l'IA distante : {e}")
        return

    print("\n--------------------------------")

    # 3. Évaluation très courte par l'IA Locale sur les notions du frugalisme
    print("\n[+] Transmission de la réponse à l'IA Locale (Ministral) pour notation...")
    client_local = AI(provider="local")
    
    prompt_evaluation = (
        "Tu es un évaluateur expert en sobriété numérique et en frugalisme. "
        "Voici la réponse donnée par l'IA candidate au questionnaire sur le frugalisme :\n\n"
        f"{reponse_distante}\n\n"
        "CONSIGNE STRICTE : Donne directement une conclusion ultra-courte de 2 à 3 lignes en français oral, sans astérisques, sans puces et sans mise en forme markdown :\n"
        "Donne la note globale sur 20, puis un conseil clé d'amélioration pour la sobriété et le frugalisme."
    )

    print("\n[+] Évaluation de Ministral (Synthèse vocale TTS en direct) :")
    stream_eval = sync_stream_to_async_gen(client_local.stream_chat(prompt_evaluation, max_tokens=100))
    
    # Lecture TTS en streaming de l'évaluation de l'IA locale
    try:
        await llm_stream_to_speech(stream_eval, TTS_VOICE)
    except Exception as e:
        print(f"\n[!] Erreur lors de la lecture TTS de l'évaluation : {e}")
    
    print("\n[+] Fin du cycle.")


async def main_async():
    print("=" * 60)
    print("        FrugalTraining - Cycle d'Évaluation d'IA        ")
    print("=" * 60)

    # 1. Démarrage/Vérification du serveur IA local
    start_ai_server()

    # 2. Préchauffage et chargement immédiat de Ministral en mémoire
    print("[+] Préchauffage et chargement en mémoire de l'IA locale (Ministral)...")
    try:
        client_warmup = AI(provider="local")
        client_warmup.chat("Bonjour", max_tokens=1)
        print("[OK] IA locale (Ministral) chargée et prête à répondre instantanément !")
    except Exception as e:
        print(f"[!] Note préchauffage : {e}")

    # 3. Boucle interactive pour lancer les cycles (Y/N)
    while True:
        try:
            choix = input("\nVoulez-vous lancer un cycle ? (Y/N) : ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print("\nSortie du programme.")
            break

        if choix == "Y":
            await run_cycle()
        elif choix == "N":
            print("[+] Arrêt du programme.")
            break
        else:
            print("[!] Choix invalide. Veuillez entrer Y ou N.")


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[+] Interruption du programme.")


if __name__ == "__main__":
    main()
