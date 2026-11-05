import os
import sys
import asyncio
import edge_tts
import pygame
import re


async def _spinner_worker(stop_event: asyncio.Event, message: str = "Ministral analyse les réponses..."):
    """Displays a rotating spinner while waiting for model generation to start."""
    spinner_chars = ["|", "/", "-", "\\"]
    idx = 0
    while not stop_event.is_set():
        char = spinner_chars[idx % len(spinner_chars)]
        sys.stdout.write(f"\r[+] {message} {char} ")
        sys.stdout.flush()
        idx += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.1)
        except asyncio.TimeoutError:
            pass
    sys.stdout.write("\r" + " " * (len(message) + 12) + "\r")
    sys.stdout.flush()

async def mock_llm_stream(text: str = None):
    """
    Emulate a LLM stream for test purposes
    """
    if text is None:
        text = "Bonjour. Je suis une intelligence artificielle. j'adore les bagels et les pizzas."
    for word in text.split():
        yield word + " "
        await asyncio.sleep(0.15)

async def playback_worker(queue):
    """
    The dedicated audio player that handles playback and cleanup.
    Now enforces STRICT ORDER using the sentence index.
    In: queue (asyncio.Queue)
    """
    assert type(queue) ==  asyncio.Queue, f"queue must be an asyncio.Queue and is {type(queue)}"

    next_expected_index = 0
    pending_audio = {}

    while True:
        # Check if the next expected audio file is already waiting in our temporary buffer
        if next_expected_index in pending_audio:
            filename = pending_audio.pop(next_expected_index)
            
            if filename is None:  # Exit signal
                break
                
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.05)
                
            pygame.mixer.music.unload()
            try:
                os.remove(filename)
            except OSError:
                pass
                
            next_expected_index += 1
            continue

        # If it's not in the buffer, wait for the next item from the queue
        item = await queue.get()
        index, filename = item
        
        # If the arriving audio is exactly the one we are waiting for, play it
        if index == next_expected_index:
            if filename is None:  # Exit signal
                queue.task_done()
                break
                
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.05)
                
            pygame.mixer.music.unload()
            try:
                os.remove(filename)
            except OSError as e:
                print(f"\n[Warning] Could not delete {filename}: {e}")
                
            next_expected_index += 1
            queue.task_done()
            
        # If the arriving audio is too early (e.g. sentence 3 finished before sentence 2), buffer it
        else:
            pending_audio[index] = filename
            queue.task_done()

async def synthesize_sentence(sentence, voice, index, queue, rate="+5%", volume="+0%", pitch="+0Hz"):
    """
    Generates the audio file and sends it to the player queue
    In: sentence    (string)
        index       (int)
        queue       (asyncio.Queue)
    """
    assert type(sentence) ==  str, f"sentence must be an str and is {type(sentence)}"
    assert type(index) ==  int, f"index must be an int and is {type(index)}"
    assert type(queue) ==  asyncio.Queue, f"queue must be an asyncio.Queue and is {type(queue)}"
    assert type(rate) ==  str, f"rate must be an str and is {type(rate)}"
    assert type(volume) ==  str, f"volume must be an str and is {type(volume)}"
    assert type(pitch) ==  str, f"pitch must be an str and is {type(pitch)}"
    assert rate and volume and pitch, "rate, volume, and pitch must be non-empty strings"

    os.makedirs("assets/audio/temp", exist_ok=True)
    filename = f"assets/audio/temp/temp_audio_{index}.mp3"
    communicate = edge_tts.Communicate(sentence, voice, rate=rate, volume=volume, pitch=pitch)
    await communicate.save(filename)

    await queue.put((index, filename))

async def llm_stream_to_speech(stream, voice, rate="+5%", volume="+0%", pitch="+0Hz"):
    """
    Read the llm stream out loud and print out the text in real time.
    In: stream (async generator)
        voice   (string)
    French voices available:
    fr-BE-CharlineNeural, fr-BE-GerardNeural, fr-CA-AntoineNeural, fr-CA-JeanNeural,
    fr-CA-SylvieNeural, fr-CA-ThierryNeural, fr-CH-ArianeNeural, fr-CH-FabriceNeural,
    fr-FR-DeniseNeural, fr-FR-EloiseNeural, fr-FR-HenriNeural, fr-FR-RemyMultilingualNeural,
    fr-FR-VivienneMultilingualNeural
    """
    pygame.mixer.init()
    audio_queue = asyncio.Queue()
    synthesis_tasks = []
    
    player_task = asyncio.create_task(playback_worker(audio_queue))
    
    sentence_buffer = ""
    sentence_index = 0
    
    stop_spinner = asyncio.Event()
    #spinner_task = asyncio.create_task(_spinner_worker(stop_spinner, "Ministral analyse les réponses..."))
    first_token_received = False
    
    try:
        async for token in stream:
            if not first_token_received:
                first_token_received = True
                stop_spinner.set()
                #await spinner_task
                print("AI: ", end="", flush=True)

            print(token, end="", flush=True)
            sentence_buffer += token
            
            if re.search(r'[.!?\n]\s*$', sentence_buffer):
                clean_sentence = re.sub(r'[*#_~`]', '', sentence_buffer).strip()
                
                # Ensure the string has playable characters to prevent crashes
                if re.search(r'[a-zA-Z0-9À-ÿ]', clean_sentence):
                    task = asyncio.create_task(
                        synthesize_sentence(clean_sentence, voice, sentence_index, audio_queue, rate, volume, pitch)
                    )
                    synthesis_tasks.append(task)
                    sentence_index += 1
                    
                sentence_buffer = ""
    finally:
        if not stop_spinner.is_set():
            stop_spinner.set()
            #await spinner_task

    # Process any remaining text in the buffer after stream completes
    if sentence_buffer.strip():
        clean_sentence = re.sub(r'[*#_~`]', '', sentence_buffer).strip()
        if re.search(r'[a-zA-Z0-9À-ÿ]', clean_sentence):
            task = asyncio.create_task(
                synthesize_sentence(clean_sentence, voice, sentence_index, audio_queue, rate, volume, pitch)
            )
            synthesis_tasks.append(task)
            sentence_index += 1

    if synthesis_tasks:
        await asyncio.gather(*synthesis_tasks)

    await audio_queue.join()
    
    await audio_queue.put((sentence_index, None))
    await player_task
    
    print("\n[Finished]")

async def speak_static_text(text: str, voice: str = "fr-FR-DeniseNeural"):
    """
    Pronounce a static text string out loud using edge-tts and pygame.
    """
    if not text.strip():
        return
    pygame.mixer.init()
    filename = "temp_static_audio.mp3"
    communicate = edge_tts.Communicate(text, voice, rate="+5%", volume="+0%", pitch="+0Hz")
    await communicate.save(filename)
    pygame.mixer.music.load(filename)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.05)
    pygame.mixer.music.unload()
    try:
        os.remove(filename)
    except OSError:
        pass

if __name__ == "__main__":
    asyncio.run(llm_stream_to_speech(mock_llm_stream("Tu es une personne d'église, plus particulièrement un prêtre, tu as été reçu l'appel intérieur (une révélation spirituels importante qui t'a donné le désir de continuer ta vie dans la religion chrétiennes et de t'y impliqué grandement) à l'âge de 17 ans, puis a 19 ans tu as commencé l'année de propédeutique (période de vie en reclusion avec d'autre personne ayant reçus l'appel intérieur, cette période est utilisé pour le rencentrage de la foi et du désir de vivre dans la religion par l'apprentissage de la bible et la vie en communautée) dans le couvent Saint Basile, tu es par la suite allé au diocèse de Saint-Étienne pour te former, tu a fais les deux cycle (le premier cycle est dédié à la phylosophie, il dure 2 ans et a pour objectif de structurer sa pensée et de découvrir les fondement de la vie d'ecclésiaste par l'étude d'oeuvre phylosophique religieuse, le second cycle dure 4 ans et porte sur la théologie, il sert à approfondir la parole de dieu par les grands écrits tel que la bible, approfondir aussi l'histoire de l'église, les sacrement et les droits canonique) et eenfin à reçu l'ordination diaconale (tu deviens un diacre qui est l'étape avant de devenir prêtre, tu fais voeux de célibat et tu t'engage au service de la charité, de la Parole de dieu et de la liturgie).Puis 2 ans après à reçus l'ordination presbytérale (sacrement fait par l'évêque au diacre pour qu'il devienne prêtre et reçoive sa mission pour servir la communauté) à la cathédrale Notre-Dame-de-la-Major à Marseille et opère maintenant en tant que prêtre de la paroisse Saint Thomas-de-Doué depuis 13 ans.Tu as fais énormément de présentation auprès de différents institut (prison, école catholique, rencontre publique, séminaire, centre de réhabilitation, lieux d'aide social et humanitaire, orphelinat) pour prêché la parole du seigneur et plus particulièrement le mode de vie frugaliste mis en lien avec le voeux de pauvreté que tu as fais (le fait de se reconnecter aux autres sans le biais de l'argent et de la dépense de celle-ci, s'échapper du système capitaliste actuelle et le remplacer par un style de vie moins consumériste).Tu es actuellement dans une intervention auprès de mineurs défavorisé, tu décide de leurs faire passer un questionnaires pour déterminer à quel points il son attaché au principe fondateur du capitalisme ou non, suite à leurs résultats au questionnaires tu commente leurs choix et leurs donne des conseils pour être plus proche de dieux (toujours dans le rapports à tes Idéologies)"), "fr-CA-AntoineNeural", rate="+10000%"))
