import os
import subprocess
import sys

def build():
    print("Starting build process for Quran Reels Generator...")
    
    # 1. Install PyInstaller if not present
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. Build command
    # --onefile: single executable
    # --add-data: include UI.html
    # --icon: use app_icon.ico
    # --name: set output name
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--add-data", f"UI.html{os.pathsep}.",
        "--icon", "app_icon.ico",
        "--name", "QuranReelsGen",
        "--hidden-import", "threading",
        "--hidden-import", "time",
        "--collect-all", "flask",
        "--collect-all", "flask_cors",
        "main.py"
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    
    print("\n" + "="*50)
    print("Build Complete!")
    print("Your EXE is located in the 'dist' folder.")
    print("Note: Make sure 'ffmpeg.exe' and 'magick.exe' are in the same folder as the EXE or in your system PATH.")
    print("="*50)

if __name__ == "__main__":
    build()
