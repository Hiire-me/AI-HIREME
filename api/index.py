"""
Vercel serverless entrypoint for the Flask application.
Vercel expects an `app` WSGI callable in this file.
"""
import sys
import os

# Add project root and backend directory to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(root_dir, 'backend')

if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app

app = create_app()
