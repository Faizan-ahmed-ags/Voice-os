# Windows installer 0.3.1

This package contains the JARVIS 0.3 desktop application with a private CPython
3.13.15 Windows x64 runtime. Setup uses NSIS and installs under Program Files.

The final build report is included in the source package. Actual Windows sound
hardware, physical shortcuts, UAC, and paste into real desktop apps still need
Windows testing. The installer is unsigned; no code-signing certificate is used.

Test microphone and Test voice are provided in the app for the first hardware
check. Desktop transcription needs a working Groq key and account quota. No
user API key is included in this package or used for development testing.

This installer does not install the web app, connect Gmail, or implement an
ElevenLabs conversational agent. Local Windows voice playback is included.
