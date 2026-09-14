"""Offline Windows speech playback. No credentials or cloud requests."""
from pathlib import Path
import os
import subprocess
import threading

SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$text = [Console]::In.ReadToEnd()
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $speaker.SetOutputToDefaultAudioDevice(); $speaker.Speak($text) }
finally { $speaker.Dispose() }
'''

class Speaker:
    def __init__(self):
        self.lock=threading.Lock()
        self.process=None
        self.generation=0

    def stop(self):
        with self.lock:
            self.generation+=1
            process=self.process
            self.process=None
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=1)
            except subprocess.TimeoutExpired: process.kill()

    def say(self,text,on_error):
        self.stop()
        with self.lock:token=self.generation
        def run():
            proc=None
            try:
                exe=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
                with self.lock:
                    if token!=self.generation:return
                    proc=subprocess.Popen([str(exe),'-NoProfile','-NonInteractive','-Command',SCRIPT],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    self.process=proc
                _,err=proc.communicate(text.encode('utf-8'),timeout=180)
                with self.lock:
                    if token!=self.generation:return
                if proc.returncode:
                    on_error('Windows voice playback failed. Check the speaker volume and installed Windows speech voices.')
            except Exception as exc:
                if proc and proc.poll() is None:proc.kill()
                with self.lock:
                    current=token==self.generation
                if current:on_error('Could not play Windows speech: '+str(exc))
            finally:
                with self.lock:
                    if self.process is proc:self.process=None
        threading.Thread(target=run,daemon=True).start()
