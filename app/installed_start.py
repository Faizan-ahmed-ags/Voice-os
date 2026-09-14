"""Start the installed app without writing to Program Files or user Python paths."""
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import runpy
import sys
import threading


def main():
    app = Path(__file__).resolve().parent
    # -I removes ambient Python paths. Add only our installer-owned app folder.
    sys.path.insert(0, str(app))
    sys.dont_write_bytecode = True
    # This distribution bundles standard PortAudio, without its optional ASIO DLL.
    os.environ.pop('SD_ENABLE_ASIO', None)
    data = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'JARVISVoice'
    data.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('jarvis.startup')
    logger.setLevel(logging.ERROR)
    handler = RotatingFileHandler(data / 'startup.log', maxBytes=250_000, backupCount=1, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)

    def show_error(kind, error, trace):
        # Standard traceback does not include frame locals, API keys, or recordings.
        logger.error('Unexpected application error', exc_info=(kind, error, trace))
        ctypes.windll.user32.MessageBoxW(None,
            'JARVIS encountered an error. Details were saved to:\n\n'
            + str(data / 'startup.log')
            + '\n\nIf this happens at startup, reinstall JARVIS Voice.',
            'JARVIS Voice', 0x10)

    sys.excepthook = show_error
    threading.excepthook = lambda args: show_error(args.exc_type, args.exc_value, args.exc_traceback)
    import tkinter
    tkinter.Tk.report_callback_exception = lambda self, kind, error, trace: show_error(kind, error, trace)
    try:
        runpy.run_path(str(app / 'jarvis_voice.py'), run_name='__main__')
    except SystemExit:
        raise
    except BaseException:
        show_error(*sys.exc_info())


if __name__ == '__main__':
    try:
        main()
    except Exception:
        ctypes.windll.user32.MessageBoxW(None,
            'JARVIS could not start. Check that your Windows user folder is writable, '
            'then reinstall JARVIS Voice if the problem continues.', 'JARVIS Voice', 0x10)
