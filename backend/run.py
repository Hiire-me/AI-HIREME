"""
Entry point for the Autonomous Job Agent backend.
Run with: python run.py
"""
import sys, os
# Ensure the backend directory is in sys.path (needed for embedded Python)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
