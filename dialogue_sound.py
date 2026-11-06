import asyncio
from array import array
import os
import random
import sys
import pygame

# Initialize Pygame mixer
if not pygame.mixer.get_init():
    pygame.mixer.init(frequency=44100, size=-16, channels=2)


def load_audio_file(file_path: str) -> pygame.mixer.Sound:
    """Load a sample in Pygame's mixer format without optional array packages."""
    return pygame.mixer.Sound(file_path)


def load_sample_folder(folder_path: str) -> list[pygame.mixer.Sound]:
    """Loads all MP3, WAV, or OGG files from a folder into memory."""
    valid_extensions = (".mp3", ".wav", ".ogg")
    sample_list = []

    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
        return sample_list

    for filename in sorted(os.listdir(folder_path)):
        if filename.lower().endswith(valid_extensions):
            file_path = os.path.join(folder_path, filename)
            sample_list.append(load_audio_file(file_path))

    return sample_list


def pitch_shift_samples(
    samples: pygame.mixer.Sound, pitch_factor: float
) -> pygame.mixer.Sound:
    """Pitch-shift mixer PCM with linear interpolation using only the stdlib."""
    if pitch_factor <= 0:
        raise ValueError("pitch_factor doit être supérieur à zéro.")

    mixer_config = pygame.mixer.get_init()
    if not mixer_config or mixer_config[1] != -16:
        # The app initializes the mixer as signed 16-bit PCM. Keep playback
        # robust if another caller initialized Pygame with a different format.
        return samples

    channels = mixer_config[2]
    source = array("h")
    source.frombytes(samples.get_raw())
    frame_count = len(source) // channels
    if frame_count < 2:
        return samples

    output_frames = max(1, int(frame_count / pitch_factor))
    shifted = array("h")
    for out_frame in range(output_frames):
        source_pos = min(out_frame * pitch_factor, frame_count - 1)
        left = int(source_pos)
        right = min(left + 1, frame_count - 1)
        fraction = source_pos - left
        for channel in range(channels):
            a = source[left * channels + channel]
            b = source[right * channels + channel]
            value = round(a + (b - a) * fraction)
            shifted.append(max(-32768, min(32767, value)))

    return pygame.mixer.Sound(buffer=shifted.tobytes())


async def play_multi_sample_word_dialogue(
    text: str,
    samples_list: list[pygame.mixer.Sound],
    word_delay: float = 0.12,
    pitch_jitter: float = 0.05,
):
    """Prints text word-by-word and plays one pitch-shifted blip per word."""
    if not samples_list:
        raise ValueError("The provided samples_list is empty.")

    sound_cache = {}
    words = text.split(" ")

    for idx, word in enumerate(words):
        # Add space after word unless it's the last word
        spacer = " " if idx < len(words) - 1 else ""
        sys.stdout.write(word + spacer)
        sys.stdout.flush()

        # Skip sound generation for empty words (multiple spaces)
        if not word.strip():
            await asyncio.sleep(word_delay)
            continue

        # 1. Pick sample and pitch variation
        sample_idx = random.randrange(len(samples_list))
        selected_samples = samples_list[sample_idx]
        pitch_factor = round(
            random.uniform(1.0 - pitch_jitter, 1.0 + pitch_jitter), 2
        )

        # 2. Retrieve or generate sound object
        cache_key = (sample_idx, pitch_factor)
        if cache_key not in sound_cache:
            sound_cache[cache_key] = pitch_shift_samples(
                selected_samples, pitch_factor
            )
        sound_cache[cache_key].set_volume(0.20)

        # 3. Play sound clip
        sound_cache[cache_key].play()

        # 4. Determine delay based on punctuation at end of word
        current_delay = word_delay
        clean_word = word.rstrip()
        if clean_word.endswith((",", ";", ":")):
            current_delay *= 1.8
        elif clean_word.endswith((".", "!", "?")):
            current_delay *= 2.5

        await asyncio.sleep(current_delay)

    print()


async def play_generation_feedback(samples_list, interval=0.16, pitch_jitter=0.05):
    """Play short samples periodically while generation is active; stop on cancel."""
    if not samples_list:
        raise ValueError("La bibliothèque de sons est vide.")

    sound_cache = {}
    active_channel = None
    try:
        while True:
            sample_idx = random.randrange(len(samples_list))
            pitch_factor = round(random.uniform(1.0 - pitch_jitter, 1.0 + pitch_jitter), 2)
            key = (sample_idx, pitch_factor)
            if key not in sound_cache:
                sound_cache[key] = pitch_shift_samples(samples_list[sample_idx], pitch_factor)
            sound_cache[key].set_volume(0.40)
            active_channel = sound_cache[key].play()
            await asyncio.sleep(interval)
    finally:
        if active_channel is not None:
            active_channel.stop()


# --- Execution Block ---
if __name__ == "__main__":

    async def main():
        folder_path = "assets/audio/answering_ia_dialogue"
        samples_library = load_sample_folder(folder_path)

        if not samples_library:
            print(f"[!] No audio files found in '{folder_path}'. Please add some .mp3, .wav, or .ogg files first.")
            return

        long_text = "This approach is much better for long paragraphs! Instead of firing off a sound effect on every single letter, it triggers once per word, making dialogue reading significantly faster and much easier on the ears."

        await play_multi_sample_word_dialogue(
            text=long_text,
            samples_list=samples_library,
            word_delay=0.04,
            pitch_jitter=0.15, 
        )

    asyncio.run(main())
