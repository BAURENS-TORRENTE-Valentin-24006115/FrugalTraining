"""Cycle de questionnaire, évaluation locale et lecture vocale."""

import sys
import os
import time
import asyncio
import threading
import re
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

def log_measurement(cycle_id: str, name: str, seconds: float, details: str = "") -> None:
    """Print one timing measurement to the console."""
    line = f"[{cycle_id}] {name}: {seconds:.3f} s"
    if details:
        line += f" | {details}"
    print(f"\n[METRIC] {line}", flush=True)


def plain_text(text: str) -> str:
    """Retire les marqueurs Markdown résiduels du texte destiné à l'écran et au TTS."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s+|[-*]\s+)", "", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text)
    return text.replace("*", "").replace("`", "")

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
    for _ in range(200):
        if is_local_server_ready():
            print("\n[OK] Serveur IA local opérationnel !")
            return proc
        if proc.poll() is not None:
            raise RuntimeError("Le serveur IA local s'est arrêté pendant son démarrage.")
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1.5)

    raise RuntimeError("Le serveur IA local n'a pas répondu dans les 5 minutes.")


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


async def run_cycle(env_values: dict[str, str], model_config: dict | None = None,
                    persona_prompt: str = "", persona_name: str = "", event_callback=None):
    """Exécute un cycle complet d'évaluation."""
    def emit(event, value):
        if event_callback:
            event_callback(event, value)

    cycle_started = time.perf_counter()
    cycle_id = time.strftime("%Y%m%d-%H%M%S")

    stage_started = time.perf_counter()
    questionnaire_text = load_questionnaire(QUESTIONNAIRE_PATH)
    log_measurement(cycle_id, "lecture_questionnaire", time.perf_counter() - stage_started,
                    f"{len(questionnaire_text)} caractères")
    if not questionnaire_text:
        print("[!] Impossible de charger le questionnaire. Cycle interrompu.")
        raise RuntimeError("Questionnaire introuvable ou illisible.")

    # Initial static text and TTS
    phrase_initiale = "Je peux te poser une question ?"
    print(f"\n[TTS] Prononciation : '{phrase_initiale}'")
    stage_started = time.perf_counter()
    try:
        await speak_static_text(phrase_initiale, voice=TTS_VOICE)
    except Exception as e:
        print(f"[!] Avertissement TTS statique : {e}")
    log_measurement(cycle_id, "tts_initiale", time.perf_counter() - stage_started)

    # The local service is started before the cycle; chat applies its system prompt.
    client_local = AI(provider="local")

    provider_distant = (model_config or {}).get("provider") or DISTANT_MODEL_PROVIDER
    print(f"\n[+] Instanciation de l'IA distante ({provider_distant.upper()})...")
    client_distant = AI(
        provider=provider_distant,
        model=(model_config or {}).get("model"),
        base_url=(model_config or {}).get("base_url"),
        api_key=(model_config or {}).get("api_key") or api_key_for(provider_distant, env_values),
    )
    client_distant.system_prompt = (
        f"{persona_prompt.strip()}\n\n"
        "Réponds dans ce rôle au questionnaire. Utilise uniquement du texte brut : "
        "aucun Markdown, aucune puce, aucun titre décoratif, aucun texte en gras ou en italique. "
        "Garde les numéros des questions et réponds clairement en français."
    )
    emit("status", f"Réponse de {client_distant.model} en cours...")

    prompt_distant = (
        f"{phrase_initiale}\n\n"
        f"Voici le questionnaire sur le frugalisme :\n{questionnaire_text}\n\n"
        "Pour chaque question, indique uniquement : son numéro, la réponse choisie et une brève explication. "
        "Ne te note pas et ne t'évalue pas toi-même. N'ajoute ni introduction, ni conclusion, ni développement supplémentaire."
    )

    print(f"[+] Envoi du questionnaire à l'IA distante ({client_distant.model})...")
    print("\n--- Réponse de l'IA Distante ---")
    remote_sound_task = None
    sound_samples = []
    try:
        from dialogue_sound import load_sample_folder, play_generation_feedback
        sample_path = Path(__file__).resolve().parent / "assets/audio/answering_ia_dialogue"
        sound_samples = load_sample_folder(str(sample_path))
        if sound_samples:
            print(f"[TTS distant] Bibliothèque chargée : {len(sound_samples)} sons ; démarrage au premier fragment.")
        else:
            print("[!] Bibliothèque de sons distante vide ; sons de génération désactivés.")
    except Exception as exc:
        print(f"[!] Impossible de démarrer les sons de la réponse distante : {exc}")

    async def stop_remote_sound():
        if not remote_sound_task:
            return
        remote_sound_task.cancel()
        try:
            await remote_sound_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"\n[!] Erreur à l'arrêt des sons distants : {exc}")

    reponse_distante = ""
    remote_started = time.perf_counter()
    remote_first_token_at = None
    remote_chunk_count = 0
    last_ui_update = 0.0
    try:
        async for token in sync_stream_to_async_gen(client_distant.stream_chat(prompt_distant)):
            if remote_first_token_at is None:
                remote_first_token_at = time.perf_counter()
                if sound_samples:
                    remote_sound_task = asyncio.create_task(
                        play_generation_feedback(sound_samples, interval=0.16)
                    )
            print(token, end="", flush=True)
            reponse_distante += token
            remote_chunk_count += 1
            if time.perf_counter() - last_ui_update >= 0.1:
                emit("remote", reponse_distante)
                last_ui_update = time.perf_counter()
    except Exception as exc:
        await stop_remote_sound()
        log_measurement(cycle_id, "generation_distante_echec", time.perf_counter() - remote_started, str(exc))
        raise RuntimeError(f"Génération distante échouée : {exc}") from exc
    await stop_remote_sound()
    emit("remote", reponse_distante)
    if remote_first_token_at is not None:
        log_measurement(cycle_id, "delai_premier_token_distant", remote_first_token_at - remote_started)
    log_measurement(cycle_id, "generation_distante_totale", time.perf_counter() - remote_started,
                    f"{remote_chunk_count} morceaux de flux, {len(reponse_distante)} caractères")
    if not reponse_distante.strip():
        print("\n[!] L'IA distante n'a renvoyé aucun texte. Évaluation locale annulée.")
        raise RuntimeError("Le modèle distant n'a renvoyé aucun texte.")

    print("\n--------------------------------")

    # Chat completions carries the persona as a real system message.
    print("\n[+] Génération de l'évaluation de Ministral...")
    emit("status", "Évaluation locale en cours...")
    client_local.system_prompt = (
        "Tu es un évaluateur de sobriété numérique et de frugalisme. "
        f"Ton rôle pour cette évaluation est : {persona_name.strip() or 'Évaluateur'}. "
        "Tu incarnes le persona suivant et tu t'adresses à la personne décrite dans ce rôle. "
        "Évalue la réponse avec ses valeurs, son vocabulaire et son point de vue, sans abandonner la tâche de notation :\n"
        f"{persona_prompt.strip()}\n\n"
        "Ta tâche est de noter la réponse d'une autre IA, pas de répondre à sa place. "
        "Donne une note entière de 0 à 20. Réponds uniquement en français et en texte brut, sans Markdown, "
        "sans astérisques, titres, puces ni liste. Fais 2 ou 3 phrases et 80 mots maximum. "
        "Commence exactement par « Note : X/20 » en remplaçant X par la note. "
        "Après la note, indique un point réussi puis un seul conseil concret, en restant dans le rôle. "
        "N'invente pas de citation religieuse ni de fait biographique. Ne donne ni grille de notation ni introduction. "
        "Termine par une phrase complète."
    )
    client_local.temperature = 0.2
    prompt_evaluation = f"Réponse de l'IA à évaluer :\n{reponse_distante}"

    print("\n[+] Évaluation de Ministral (Synthèse vocale TTS) :")
    final_started = time.perf_counter()
    final_text = ""
    final_chunk_count = 0
    last_evaluation_update = 0.0
    score_emitted = False
    tts_error = None

    async def audio_stream(audio_queue):
        while True:
            fragment = await audio_queue.get()
            if fragment is None:
                break
            yield fragment

    async def generate_local_evaluation(prompt):
        nonlocal final_text, final_chunk_count, last_evaluation_update, score_emitted, tts_error
        final_text = ""
        final_chunk_count = 0
        score_emitted = False
        audio_queue: asyncio.Queue = asyncio.Queue()
        tts_task = asyncio.create_task(llm_stream_to_speech(audio_stream(audio_queue), TTS_VOICE))
        try:
            async for fragment in sync_stream_to_async_gen(
                client_local.stream_chat(prompt, keep_history=False, max_tokens=768)
            ):
                final_text += fragment
                final_chunk_count += 1
                audio_queue.put_nowait(plain_text(fragment))
                if not score_emitted:
                    score_match = re.search(r"Note\s*:\s*(\d{1,2})\s*/\s*20", final_text, re.I)
                    if score_match:
                        emit("score", int(score_match.group(1)))
                        score_emitted = True
                if time.perf_counter() - last_evaluation_update >= 0.08:
                    emit("evaluation_chunk", plain_text(final_text))
                    last_evaluation_update = time.perf_counter()
            emit("evaluation_chunk", plain_text(final_text))
        finally:
            audio_queue.put_nowait(None)
        try:
            await tts_task
        except Exception as exc:
            tts_error = exc
            print(f"\n[!] Erreur TTS pendant l'évaluation : {exc}")

    await generate_local_evaluation(prompt_evaluation)
    if not final_text.strip():
        log_measurement(cycle_id, "relance_evaluation_finale_apres_sortie_vide", 0.0)
        await generate_local_evaluation(
            prompt_evaluation + "\n\nRéponds maintenant, en commençant par « Note : »."
        )
    final_generation_seconds = time.perf_counter() - final_started
    if not final_text.strip():
        log_measurement(cycle_id, "generation_ministral_final_echec", final_generation_seconds,
                        "sortie vide après une relance")
        raise RuntimeError("Ministral a terminé sans texte d'évaluation après une relance.")
    final_text = plain_text(final_text).strip()
    emit("evaluation", final_text.strip())

    final_total = time.perf_counter() - final_started
    log_measurement(cycle_id, "generation_ministral_final", final_generation_seconds,
                    f"{final_chunk_count} fragments de sortie")
    log_measurement(cycle_id, "traitement_tts_evaluation_et_attente", max(0, final_total - final_generation_seconds))
    log_measurement(cycle_id, "duree_totale_cycle", time.perf_counter() - cycle_started)
    
    print("\n[+] Fin du cycle.")
    emit("status", f"Cycle terminé. Audio indisponible : {tts_error}" if tts_error else "Cycle terminé.")


async def main_async():
    print("=" * 60)
    print("        FrugalTraining - Cycle d'Évaluation d'IA        ")
    print("=" * 60)

    env_values = load_env_file()

    # Start or verify the local AI server
    start_ai_server()

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


