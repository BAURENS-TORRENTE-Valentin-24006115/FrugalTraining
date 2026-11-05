"""Cycle de questionnaire, évaluation locale et lecture vocale."""

import sys
import os
import time
import asyncio
import threading
import queue
import json
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
    cycle_started = time.perf_counter()
    cycle_id = time.strftime("%Y%m%d-%H%M%S")

    stage_started = time.perf_counter()
    questionnaire_text = load_questionnaire(QUESTIONNAIRE_PATH)
    log_measurement(cycle_id, "lecture_questionnaire", time.perf_counter() - stage_started,
                    f"{len(questionnaire_text)} caractères")
    if not questionnaire_text:
        print("[!] Impossible de charger le questionnaire. Cycle interrompu.")
        return

    # Initial static text and TTS
    phrase_initiale = "Je peux te poser une question ?"
    print(f"\n[TTS] Prononciation : '{phrase_initiale}'")
    stage_started = time.perf_counter()
    try:
        await speak_static_text(phrase_initiale, voice=TTS_VOICE)
    except Exception as e:
        print(f"[!] Avertissement TTS statique : {e}")
    log_measurement(cycle_id, "tts_initiale", time.perf_counter() - stage_started)

    # Start local model loading while the remote model is answering.
    print("\n[+] Chargement de Ministral en parallèle de la génération distante...")
    client_local = AI(provider="local")
    local_slot_id = 0
    prefill_prefix = (
        "Tu es un évaluateur expert en sobriété numérique et en frugalisme. "
        "La réponse candidate commence ci-dessous.\n"
        "Réponse candidate :\n"
    )
    local_ready = threading.Event()
    local_errors: list[Exception] = []

    def load_local_model():
        started = time.perf_counter()
        try:
            client_local.chat("Prépare-toi à recevoir la réponse candidate.", max_tokens=1)
            log_measurement(cycle_id, "chargement_et_prewarm_ministral", time.perf_counter() - started)
            local_ready.set()
        except Exception as exc:
            log_measurement(cycle_id, "chargement_ministral_echec", time.perf_counter() - started,
                            str(exc))
            local_errors.append(exc)
            local_ready.set()

    threading.Thread(target=load_local_model, daemon=True).start()

    # Response from the remote AI
    provider_distant = DISTANT_MODEL_PROVIDER if DISTANT_MODEL_PROVIDER else "mistral"
    print(f"\n[+] Instanciation de l'IA distante ({provider_distant.upper()})...")
    client_distant = AI(provider=provider_distant, api_key=api_key_for(provider_distant, env_values))

    prompt_distant = (
        f"{phrase_initiale}\n\n"
        f"Voici le questionnaire sur le frugalisme :\n{questionnaire_text}\n\n"
        "Pour chaque question, indique uniquement : son numéro, la réponse choisie et une brève explication. "
        "Ne te note pas et ne t'évalue pas toi-même. N'ajoute ni introduction, ni conclusion, ni développement supplémentaire."
    )

    print(f"[+] Envoi du questionnaire à l'IA distante ({client_distant.model})...")
    print("\n--- Réponse de l'IA Distante ---")
    
    reponse_distante = ""
    pending = ""
    # This keeps the first roughly half of the shorter questionnaire answer
    # available for Ministral while the remote model is still generating.
    chunk_size = 2300
    remote_started = time.perf_counter()
    remote_first_token_at = None
    remote_finished_at = None
    local_queue_drained_at = None
    remote_token_count = 0
    fragments_count = 0
    merged_fragments_count = 0
    fragment_processing_seconds = 0.0
    cached_prompt_tokens = 0
    newly_evaluated_tokens = 0
    accumulated_local_text = ""
    remote_queue: queue.Queue = queue.Queue()
    local_queue: asyncio.Queue = asyncio.Queue()

    def receive_remote_stream():
        nonlocal remote_finished_at
        try:
            for token in client_distant.stream_chat(prompt_distant):
                remote_queue.put(token)
        except Exception as exc:
            remote_queue.put(exc)
        finally:
            remote_finished_at = time.perf_counter()
            remote_queue.put(None)

    async def process_local_fragments():
        nonlocal fragments_count, merged_fragments_count, fragment_processing_seconds
        nonlocal cached_prompt_tokens, newly_evaluated_tokens, accumulated_local_text
        while True:
            fragment = await local_queue.get()
            if fragment is None:
                local_queue.task_done()
                break
            pending_fragments = [fragment]
            saw_end = False
            while True:
                try:
                    queued_fragment = local_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if queued_fragment is None:
                    local_queue.task_done()
                    saw_end = True
                    break
                pending_fragments.append(queued_fragment)
            try:
                if not local_ready.is_set():
                    await asyncio.to_thread(local_ready.wait)
                if local_errors:
                    raise local_errors[0]
                merged_fragments_count += len(pending_fragments)
                accumulated_local_text += "".join(pending_fragments)
                payload = {
                    "model": client_local.model,
                    "prompt": prefill_prefix + accumulated_local_text,
                    "n_predict": 0,
                    "stream": False,
                    "temperature": 0,
                    "cache_prompt": True,
                    "id_slot": local_slot_id,
                    "timings_per_token": True,
                }
                request = urllib.request.Request(
                    f"{client_local.base_url}/completions",
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                fragment_started = time.perf_counter()
                def prefill_request():
                    with urllib.request.urlopen(request, timeout=300) as response:
                        return json.load(response)
                result = await asyncio.to_thread(prefill_request)
                fragment_processing_seconds += time.perf_counter() - fragment_started
                fragments_count += 1
                timings = result.get("timings", {})
                cached_prompt_tokens += int(timings.get("cache_n", 0))
                newly_evaluated_tokens += int(timings.get("prompt_n", 0))
            finally:
                for _ in pending_fragments:
                    local_queue.task_done()
            if saw_end:
                break

    threading.Thread(target=receive_remote_stream, daemon=True).start()
    local_worker = asyncio.create_task(process_local_fragments())
    try:
        while True:
            token = await asyncio.to_thread(remote_queue.get)
            if token is None:
                break
            if isinstance(token, Exception):
                raise token
            if remote_first_token_at is None:
                remote_first_token_at = time.perf_counter()
            print(token, end="", flush=True)
            reponse_distante += token
            pending += token
            remote_token_count += 1
            # Queue coherent fragments while Ministral is loading; process in order once ready.
            while len(pending) >= chunk_size:
                split_at = max(pending.rfind(mark, 0, chunk_size + 1) for mark in (". ", "! ", "? ", "\n"))
                if split_at < 0:
                    split_at = chunk_size
                else:
                    split_at += 1
                fragment, pending = pending[:split_at].strip(), pending[split_at:].lstrip()
                if fragment:
                    print("\n[+] Transmission d'un fragment à Ministral...")
                    await local_queue.put(fragment)
        if pending.strip():
            await local_queue.put(pending.strip())
        await local_queue.put(None)
        await local_queue.join()
        local_queue_drained_at = time.perf_counter()
        await local_worker
    except Exception as e:
        if not local_worker.done():
            local_worker.cancel()
        print(f"\n[!] Erreur lors de la génération par l'IA distante : {e}")
        log_measurement(cycle_id, "generation_distante_echec", time.perf_counter() - remote_started,
                        str(e))
        return

    # Stop the remote timer when its producer finishes, excluding local queue drain time.
    remote_total = (remote_finished_at or time.perf_counter()) - remote_started
    if remote_first_token_at is not None:
        log_measurement(cycle_id, "delai_premier_token_distant", remote_first_token_at - remote_started)
    log_measurement(cycle_id, "generation_distante_totale", remote_total,
                    f"{remote_token_count} morceaux de flux, {len(reponse_distante)} caractères")
    log_measurement(cycle_id, "traitement_fragments_ministral", fragment_processing_seconds,
                    f"{merged_fragments_count} fragments fusionnés en {fragments_count} préévaluations, "
                    f"{newly_evaluated_tokens} nouveaux tokens, "
                    f"{cached_prompt_tokens} tokens en cache, slot {local_slot_id}; "
                    f"moyenne {fragment_processing_seconds / max(fragments_count, 1):.3f} s/appel")
    if remote_finished_at is not None and local_queue_drained_at is not None:
        post_api_wait = max(0.0, local_queue_drained_at - remote_finished_at)
        log_measurement(cycle_id, "attente_apres_fin_api_pour_vider_file_ministral", post_api_wait)

    if not reponse_distante.strip():
        print("\n[!] L'IA distante n'a renvoyé aucun texte. Évaluation locale annulée.")
        return

    print("\n--------------------------------")

    # Extend the exact cached prompt and generate the assessment in the same llama.cpp slot.
    print("\n[+] Ministral a assimilé la réponse. Génération de son évaluation finale...")
    prompt_evaluation = (
        prefill_prefix + accumulated_local_text +
        "\n\nÉvalue la réponse candidate en français oral, sans puces ni markdown, en 2 ou 3 lignes et 50 mots maximum. "
        "Commence obligatoirement par « Note : X/20 ». Puis donne un point réussi et un seul conseil clé d'amélioration. "
        "Termine par une phrase complète."
    )

    print("\n[+] Évaluation de Ministral (Synthèse vocale TTS) :")
    final_started = time.perf_counter()
    result_final = await asyncio.to_thread(
        client_local.complete_completion,
        prompt_evaluation,
        240,
        local_slot_id,
        True,
    )
    final_text = "".join(choice.get("text", "") for choice in result_final.get("choices", []))
    final_token_count = result_final.get("usage", {}).get("completion_tokens", 0)
    if not final_text.strip():
        log_measurement(cycle_id, "relance_evaluation_finale_apres_sortie_vide", 0.0)
        result_final = await asyncio.to_thread(
            client_local.complete_completion,
            prompt_evaluation + "\n\nRéponds en 50 mots maximum et commence par « Note : ».",
            240,
            local_slot_id,
            True,
        )
        final_text = "".join(choice.get("text", "") for choice in result_final.get("choices", []))
        final_token_count = result_final.get("usage", {}).get("completion_tokens", 0)
    final_generation_seconds = time.perf_counter() - final_started
    if not final_text.strip():
        log_measurement(cycle_id, "generation_ministral_final_echec", final_generation_seconds,
                        "sortie vide après une relance")
        raise RuntimeError("Ministral a terminé sans texte d'évaluation après une relance.")

    async def final_text_stream():
        yield final_text

    stream_eval = final_text_stream()

    # Send the final generated evaluation to TTS.
    try:
        await llm_stream_to_speech(stream_eval, TTS_VOICE)
    except Exception as e:
        print(f"\n[!] Erreur lors de la lecture TTS de l'évaluation : {e}")

    final_total = time.perf_counter() - final_started
    log_measurement(cycle_id, "generation_ministral_final", final_generation_seconds,
                    f"{final_token_count} tokens de sortie")
    log_measurement(cycle_id, "traitement_tts_evaluation_et_attente", max(0, final_total - final_generation_seconds))
    log_measurement(cycle_id, "duree_totale_cycle", time.perf_counter() - cycle_started)
    
    print("\n[+] Fin du cycle.")


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


