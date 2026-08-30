"""
Interfaz común entre LocalAudioIO (micro/altavoz local) y TwilioAudioIO
(llamada telefónica real vía Media Streams). PizzeriaCallSession solo
conoce este Protocol - no le importa ni sabe cuál de las dos implementaciones
está usando en cada caso.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class AudioIO(Protocol):
    def open(self, loop=None) -> None: ...

    def close(self) -> None: ...

    async def read_chunk(self) -> bytes: ...

    async def write_chunk(self, data: bytes) -> None: ...

    def clear_output_buffer(self) -> None: ...

    async def wait_until_speaker_drained(
        self, timeout: float = 10.0, poll_interval: float = 0.2
    ) -> None: ...
