"""Extract stereo PCM audio and manage playback timing."""

from __future__ import annotations

import io
import logging
import os
import time
import wave
from typing import Self

import av
import pygame

logger = logging.getLogger(__name__)


class AudioEngine:
    """
    Extract 44.1kHz stereo PCM, play audio, and track playback time.
    """

    def __init__(self, video_path: str) -> None:
        """
        Initialize the audio engine with a video file path.

        Args:
            video_path: Path to the media file.

        Raises:
            FileNotFoundError: If the media file does not exist.
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(
                f"[HATA / ERROR] Video dosyası bulunamadı / Video file not found: {video_path}"
            )

        self.video_path = os.path.abspath(video_path)
        self.sample_rate = 44100
        self.channels = 2
        self.sample_width = 2  # 16-bit PCM (2 bytes per sample per channel)

        self._pcm_data: bytes | None = None
        self._wav_bytes: bytes | None = None
        self._wav_buffer: io.BytesIO | None = None

        self._is_loaded = False
        self._is_playing = False
        self._is_paused = False
        self._paused_seek = False
        self._play_start_perf = 0.0
        self._start_offset = 0.0
        self._paused_time = 0.0

        # Probe container for audio stream
        self.has_audio = False
        self.duration = 0.0

        try:
            with av.open(self.video_path) as container:
                # Video duration fallback
                if container.duration is not None and container.duration > 0:
                    self.duration = float(container.duration / 1e6)

                if container.streams.audio:
                    self.has_audio = True
                    audio_stream = container.streams.audio[0]
                    if (
                        audio_stream.duration is not None
                        and audio_stream.duration > 0
                        and audio_stream.time_base is not None
                    ):
                        self.duration = float(audio_stream.duration * audio_stream.time_base)
        except (av.FFmpegError, OSError) as err:
            logger.debug("Failed opening video container for audio probe: %s", err)
            self.has_audio = False

    def _extract_pcm(self) -> bytes:
        """Demux and resample audio stream to 44.1kHz 16-bit stereo PCM bytes."""
        if self._pcm_data is not None:
            return self._pcm_data

        if not self.has_audio:
            self._pcm_data = b""
            return self._pcm_data

        try:
            with av.open(self.video_path) as container:
                if not container.streams.audio:
                    self.has_audio = False
                    self._pcm_data = b""
                    return self._pcm_data

                audio_stream = container.streams.audio[0]
                resampler = av.AudioResampler(
                    format="s16",
                    layout="stereo",
                    rate=self.sample_rate,
                )

                chunks = []
                for frame in container.decode(audio_stream):
                    for resampled in resampler.resample(frame):
                        chunks.append(resampled.to_ndarray().tobytes())

                # Flush any remaining frames from resampler
                for resampled in resampler.resample(None):
                    chunks.append(resampled.to_ndarray().tobytes())

                self._pcm_data = b"".join(chunks)

                # Update exact audio duration from resampled PCM bytes
                bytes_per_second = self.sample_rate * self.channels * self.sample_width
                if bytes_per_second > 0 and len(self._pcm_data) > 0:
                    self.duration = len(self._pcm_data) / bytes_per_second

                return self._pcm_data
        except (av.FFmpegError, OSError) as err:
            logger.warning("Error demuxing/resampling audio: %s", err)
            self.has_audio = False
            self._pcm_data = b""
            return self._pcm_data

    def _get_wav_bytes(self) -> bytes:
        """Construct standard 16-bit stereo PCM WAV in memory."""
        if self._wav_bytes is not None:
            return self._wav_bytes

        pcm = self._extract_pcm()
        if not pcm:
            self._wav_bytes = b""
            return self._wav_bytes

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.sample_width)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm)

        self._wav_bytes = wav_io.getvalue()
        return self._wav_bytes

    def extract_audio_file(self, output_wav_path: str) -> bool:
        """
        Export 16-bit 44.1kHz stereo PCM WAV file without requiring external ffmpeg binary.

        Args:
            output_wav_path: Destination WAV file path.

        Returns:
            True if audio was extracted and saved, False if video has no audio.
        """
        if not self.has_audio:
            return False

        wav_bytes = self._get_wav_bytes()
        if not wav_bytes:
            return False

        abs_path = os.path.abspath(output_wav_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with open(abs_path, "wb") as f:
            f.write(wav_bytes)

        return True

    def load_for_playback(self) -> bool:
        """
        Initialize Pygame mixer and load extracted audio buffer for playback.

        Returns:
            True if audio was loaded successfully, False if video has no audio.
        """
        if not self.has_audio:
            return False

        wav_bytes = self._get_wav_bytes()
        if not wav_bytes:
            return False

        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=self.channels)

        self._wav_buffer = io.BytesIO(wav_bytes)
        try:
            pygame.mixer.music.load(self._wav_buffer)
            self._is_loaded = True
            return True
        except (pygame.error, OSError) as err:
            logger.warning("Failed loading audio into pygame mixer: %s", err)
            self._is_loaded = False
            return False

    def play(self, start_time: float = 0.0) -> None:
        """
        Start audio playback at the specified timestamp in seconds.

        Args:
            start_time: Starting offset in seconds.
        """
        start_time = max(0.0, float(start_time))
        if self.duration > 0:
            start_time = min(self.duration, start_time)

        if self.has_audio and self._is_loaded:
            try:
                pygame.mixer.music.play(loops=0, start=start_time)
            except pygame.error as err:
                logger.debug("Failed playing music at %s: %s", start_time, err)

        self._start_offset = start_time
        self._play_start_perf = time.perf_counter()
        self._is_playing = True
        self._is_paused = False
        self._paused_seek = False

    def pause(self) -> None:
        """Pause playback seamlessly and freeze master clock."""
        if self._is_playing and not self._is_paused:
            self._paused_time = self.get_master_time()
            self._is_paused = True
            self._paused_seek = False
            if self.has_audio and self._is_loaded:
                try:
                    pygame.mixer.music.pause()
                except pygame.error as err:
                    logger.debug("Failed pausing music: %s", err)

    def resume(self) -> None:
        """Resume playback seamlessly from paused timestamp."""
        if self._is_playing and self._is_paused:
            self._is_paused = False
            self._start_offset = self._paused_time
            self._play_start_perf = time.perf_counter()
            if self.has_audio and self._is_loaded:
                if self._paused_seek:
                    try:
                        pygame.mixer.music.play(loops=0, start=self._start_offset)
                    except pygame.error as err:
                        logger.debug("Failed restarting music on resume after seek: %s", err)
                    self._paused_seek = False
                else:
                    try:
                        pygame.mixer.music.unpause()
                    except pygame.error as err:
                        logger.debug("Failed unpausing music: %s", err)

    def stop(self) -> None:
        """Stop playback and reset master clock."""
        self._is_playing = False
        self._is_paused = False
        self._paused_seek = False
        self._start_offset = 0.0
        self._paused_time = 0.0
        if self.has_audio and self._is_loaded:
            try:
                pygame.mixer.music.stop()
            except pygame.error as err:
                logger.debug("Failed stopping music: %s", err)

    def get_master_time(self) -> float:
        """
        Get sub-millisecond precision master playback timestamp in seconds.

        Returns:
            Current playback timestamp in seconds.
        """
        if not self._is_playing:
            return self._start_offset

        if self._is_paused:
            return self._paused_time

        elapsed = time.perf_counter() - self._play_start_perf
        current = self._start_offset + elapsed

        if self.duration > 0:
            current = min(current, self.duration)

        return current

    def seek(self, seconds: float) -> float:
        """
        Seek audio playback to target seconds and reset master clock baseline.

        Args:
            seconds: Target timestamp in seconds.

        Returns:
            Clamped target timestamp that was seeked to.
        """
        target_seconds = max(0.0, float(seconds))
        if self.duration > 0:
            target_seconds = min(self.duration, target_seconds)

        self._start_offset = target_seconds
        self._play_start_perf = time.perf_counter()

        if self._is_paused:
            self._paused_time = target_seconds
            self._paused_seek = True

        if self.has_audio and self._is_loaded:
            if self._is_playing and not self._is_paused:
                try:
                    pygame.mixer.music.play(loops=0, start=target_seconds)
                except pygame.error as err:
                    logger.debug("Failed seeking music with play: %s", err)
            else:
                try:
                    pygame.mixer.music.set_pos(target_seconds)
                except pygame.error as err:
                    logger.debug("Failed seeking music with set_pos: %s", err)

        return target_seconds

    @staticmethod
    def is_frame_late(frame_pts: float, master_time: float, frame_duration: float) -> bool:
        """
        Determine if a video frame has lagged behind audio playback.

        Args:
            frame_pts: Presentation timestamp of current video frame.
            master_time: Current master clock position.
            frame_duration: Nominal duration of a single frame (1.0 / fps).

        Returns:
            True if frame_pts < master_time - frame_duration (triggering frame drop).
        """
        return frame_pts < (master_time - frame_duration)

    def close(self) -> None:
        """Clean up audio mixer playback and buffers."""
        self.stop()
        self._wav_buffer = None
        self._pcm_data = None
        self._wav_bytes = None
        self._is_loaded = False
        self._paused_seek = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
