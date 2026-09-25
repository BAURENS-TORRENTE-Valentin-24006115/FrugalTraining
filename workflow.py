"""Cycle de questionnaire, évaluation locale et lecture vocale."""

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
from settings import (
    DISTANT_MODEL_PROVIDER,
    QUESTIONNAIRE_PATH,
    TTS_VOICE,
    api_key_for,
    load_env_file,
)

# Force UTF-8 stdout on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    
    proc = subprocess.Popen(
        [sys.executable, str(beacon_script)],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )

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


async def run_cycle(env_values: dict[str, str]):
    """Exécute un cycle complet d'évaluation."""
    questionnaire_text = load_questionnaire(QUESTIONNAIRE_PATH)
    if not questionnaire_text:
        print("[!] Impossible de charger le questionnaire. Cycle interrompu.")
        return

    # Initial static text and TTS
    phrase_initiale = "Je peux te poser une question ?"
    print(f"\n[TTS] Prononciation : '{phrase_initiale}'")
    try:
        await speak_static_text(phrase_initiale, voice=TTS_VOICE)
    except Exception as e:
        print(f"[!] Avertissement TTS statique : {e}")

    # Response from the remote AI
    provider_distant = DISTANT_MODEL_PROVIDER if DISTANT_MODEL_PROVIDER else "mistral"
    print(f"\n[+] Instanciation de l'IA distante ({provider_distant.upper()})...")
    client_distant = AI(provider=provider_distant, api_key=api_key_for(provider_distant, env_values))

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

    if not reponse_distante.strip():
        print("\n[!] L'IA distante n'a renvoyé aucun texte. Évaluation locale annulée.")
        return

    print("\n--------------------------------")

    # Short evaluation by the local AI
    print("\n[+] Transmission de la réponse à l'IA Locale (Ministral) pour notation...")
    client_local = AI(provider="local")
    client_local.system_prompt = (
        "Tu es un évaluateur expert en sobriété numérique et en frugalisme. "
        "Réponds en 2 à 3 lignes de français oral, sans puces ni markdown. "
        "Donne une note sur 20 et un conseil clé d'amélioration."
    )

    prompt_evaluation = (
        "Voici la réponse donnée par l'IA candidate au questionnaire sur le frugalisme :\n\n"
        f"{reponse_distante}"
    )

    print("\n[+] Évaluation de Ministral (Synthèse vocale TTS en direct) :")
    stream_eval = sync_stream_to_async_gen(client_local.stream_chat(prompt_evaluation, max_tokens=100))
    
    # Stream the local AI evaluation through TTS
    try:
        await llm_stream_to_speech(stream_eval, TTS_VOICE)
    except Exception as e:
        print(f"\n[!] Erreur lors de la lecture TTS de l'évaluation : {e}")
    
    print("\n[+] Fin du cycle.")


async def main_async():
    print("=" * 60)
    print("        FrugalTraining - Cycle d'Évaluation d'IA        ")
    print("=" * 60)

    env_values = load_env_file()

    # Start or verify the local AI server
    start_ai_server()

    # Warm up and load Ministral into memory
    print("[+] Préchauffage et chargement en mémoire de l'IA locale (Ministral)...")
    try:
        client_warmup = AI(provider="local")
        client_warmup.chat("Bonjour", max_tokens=1)
        print("[OK] IA locale (Ministral) chargée et prête à répondre instantanément !")
    except Exception as e:
        print(f"[!] Note préchauffage : {e}")

    # Interactive loop for starting cycles (Y/N)
    while True:
        try:
            choix = input("\nVoulez-vous lancer un cycle ? (Y/N) : ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print("\nSortie du programme.")
            break

        if choix == "Y":
            await run_cycle(env_values)
        elif choix == "N":
            print("[+] Arrêt du programme.")
            break
        else:
            print("[!] Choix invalide. Veuillez entrer Y ou N.")


