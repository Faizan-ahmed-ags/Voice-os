' JARVIS autostart — runs at every Windows logon.
' 1) Starts the MetaTrader 5 terminal (the bridge attaches to it for real orders)
' 2) Starts the JARVIS console (UI + API on 127.0.0.1:8765, daily scheduler,
'    trade learner, and the local LLM brain) as a hidden background process
' Double-click-safe: if the console is already running, the launcher just
' re-binds or opens nothing new (it retries the port and exits quietly).

Set sh = CreateObject("WScript.Shell")
jarvisDir = "C:\Users\User\OneDrive\Documents\jarvis"

sh.CurrentDirectory = jarvisDir

' 1) MetaTrader 5 terminal (normal window — you can watch your account)
sh.Run """C:\Program Files\MetaTrader 5\terminal64.exe""", 1, False

' 2) JARVIS console, hidden, no browser popup
sh.Environment("PROCESS").Item("JARVIS_NO_BROWSER") = "1"
sh.Run """C:\Users\User\OneDrive\Documents\jarvis\.venv\Scripts\pythonw.exe"" """ & _
        jarvisDir & "\start_jarvis.py""", 0, False
