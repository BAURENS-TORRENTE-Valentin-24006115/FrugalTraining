import asyncio
from array import array
import os
import random
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
        # Preserve the original sample when the mixer format cannot be interpolated safely.
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
