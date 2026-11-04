import asyncio
import os
import random
import sys
import numpy as np
import pygame

# Initialize Pygame mixer
if not pygame.mixer.get_init():
    pygame.mixer.init(frequency=44100, size=-16, channels=2)


def load_audio_file(file_path: str) -> np.ndarray:
    """Loads an MP3, WAV, or OGG file directly into a NumPy array using Pygame."""
    sound = pygame.mixer.Sound(file_path)
    samples = pygame.sndarray.array(sound)

    if samples.ndim == 1:
        samples = np.column_stack((samples, samples))
    return samples


def load_sample_folder(folder_path: str) -> list[np.ndarray]:
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
    samples: np.ndarray, pitch_factor: float
) -> pygame.mixer.Sound:
    """Pitch-shifts raw audio samples using linear interpolation."""
    original_len = len(samples)
    new_len = int(original_len / pitch_factor)

    old_indices = np.linspace(0, original_len - 1, original_len)
    new_indices = np.linspace(0, original_len - 1, new_len)

    left_channel = np.interp(new_indices, old_indices, samples[:, 0])
    right_channel = np.interp(new_indices, old_indices, samples[:, 1])

    shifted_samples = np.column_stack((left_channel, right_channel)).astype(
        np.int16
    )
    return pygame.sndarray.make_sound(shifted_samples)


async def play_multi_sample_word_dialogue(
    text: str,
    samples_list: list[np.ndarray],
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