import os
import sys

# Ensure project root and backend are both discoverable
root_path = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.join(root_path, 'backend')

if root_path not in sys.path:
    sys.path.insert(0, root_path)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from backend.app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
