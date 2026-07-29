import os
import subprocess

# Quietly pull latest changes from GitHub on Revit startup
try:
    ext_dir = os.path.dirname(__file__)
    # Run git pull silently in background without popping up a console window
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    subprocess.Popen(
        ["git", "pull"], cwd=ext_dir, startupinfo=startupinfo
    )
except Exception:
    pass  # Fail silently if offline or git is busy