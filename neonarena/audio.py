"""Short local WAV effects. The game also works on computers without audio."""

from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtMultimedia import QMediaDevices, QSoundEffect

from .storage import resource


class Audio(QObject):
    def __init__(self, volume=55, muted=False, parent=None):
        super().__init__(parent)
        self.effects = {}
        self.available = bool(QMediaDevices.audioOutputs())
        names = ("shot", "dash", "hurt", "upgrade", "over", "wave") if self.available else ()
        for name in names:
            effect = QSoundEffect(self)
            effect.setSource(QUrl.fromLocalFile(str(resource(f"assets/{name}.wav"))))
            self.effects[name] = effect
        self.set_volume(volume, muted)

    def set_volume(self, volume, muted=False):
        self.volume = max(0, min(100, int(volume)))
        self.muted = muted
        for effect in self.effects.values():
            effect.setVolume(0 if muted else self.volume / 100 * 0.65)

    def play(self, name):
        effect = self.effects.get(name)
        if effect is not None and not self.muted:
            effect.play()
