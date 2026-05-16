"""
Quran Reels Generator - Mobile App Entry Point
This is the main entry point for the mobile app using BeeWare
"""

import sys
import os
import threading
import time

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import main Flask app
from quranreels.main import app

def start_flask_server():
    """Start Flask server in a separate thread"""
    # Run Flask on localhost (127.0.0.1) for mobile
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

def main():
    """Main entry point for the mobile app"""
    # Start Flask server in background thread
    flask_thread = threading.Thread(target=start_flask_server, daemon=True)
    flask_thread.start()
    
    # Wait a moment for server to start
    time.sleep(1)
    
    # For mobile apps, we'll use WebView to display the HTML
    # The actual WebView implementation will be handled by BeeWare
    # For now, we just keep the Flask server running
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")

if __name__ == '__main__':
    main()
