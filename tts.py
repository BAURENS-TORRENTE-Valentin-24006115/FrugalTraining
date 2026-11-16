import os
import asyncio
import edge_tts
import pygame
import re


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

    def queue_complete_sentences(buffer):
        """Queue every complete sentence in buffer and return the remainder."""
        nonlocal sentence_index
        # A model chunk can contain several sentences, or end midway through one.
        # Split at punctuation followed by whitespace/end, preserving the final
        # incomplete sentence for the next streamed fragment.
        while True:
            match = re.search(r"[.!?](?:[\"')\]]*)\s+|\n+", buffer)
            if not match:
                break
            sentence = buffer[:match.end()].strip()
            buffer = buffer[match.end():].lstrip()
            clean_sentence = re.sub(r'[*#_~`]', '', sentence).strip()
            if re.search(r'[a-zA-Z0-9À-ÿ]', clean_sentence):
                task = asyncio.create_task(
                    synthesize_sentence(clean_sentence, voice, sentence_index, audio_queue, rate, volume, pitch)
                )
                synthesis_tasks.append(task)
                sentence_index += 1
        return buffer
    
    first_token_received = False
    
    async for token in stream:
        if not first_token_received:
            first_token_received = True
            print("AI: ", end="", flush=True)

        print(token, end="", flush=True)
        sentence_buffer += token
        sentence_buffer = queue_complete_sentences(sentence_buffer)
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
