RETRO ASCII VIDEO PLAYER

Bu klasör, dışa aktarılan ASCII video oynatıcısını içerir.
This folder contains an exported ASCII video player.

Çalıştırma / Running
--------------------
run.bat dosyasına çift tıklayın veya "python run.py" komutunu çalıştırın.
Double-click run.bat or run "python run.py".

Python, Pygame ve NumPy gerekir: pip install pygame numpy
Requires Python, Pygame, and NumPy: pip install pygame numpy

Klavye / Keyboard
-----------------
Space       Oynat/duraklat / Play/pause
Up / Down   Hız / Speed: 0.5x–2.0x
Left/Right  Geri/ileri sar / Seek backward/forward
R           CRT efektini aç/kapat / Toggle CRT
F1          Yardım / Help
Esc / Q     Çıkış / Quit

Dosyalar / Files
----------------
run.py, run.bat         Oynatıcı ve başlatıcı / Player and launcher
ascii_data.npz         ASCII kareleri / ASCII frames
config.json            Oynatma ayarları / Playback settings
audio.wav              Varsa ses kaydı / Audio track, when included
standalone_player.spec EXE paketleme ayarları / EXE build configuration

EXE oluşturma / Building an EXE
------------------------------
pip install pyinstaller pygame numpy
pyinstaller standalone_player.spec

Ayrıntılı seçenekler / More options: python run.py --help
