"""Interactive local launcher: secret input is hidden and never saved to disk."""
import getpass
import os
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.chdir(root)
if not os.environ.get('LLM_API_KEY'):
    os.environ['LLM_API_KEY'] = getpass.getpass('LLM API key (hidden): ').strip()
os.environ.setdefault('LLM_BASE_URL', 'https://shared1.multitool.works:4000/v1')
os.environ.setdefault('LLM_MODEL', 'gigachat-3-pro')
os.environ.setdefault('TRANSCRIPTION_MODEL', 'whisper-large-v3')
os.environ.setdefault('OPERATOR_TOKEN', secrets.token_urlsafe(32))
os.environ.setdefault('DATA_DIR', str(root / 'data'))
os.environ.setdefault('APP_ENV', 'development')
port = os.environ.get('PORT', '8080')
os.environ.setdefault('APP_ORIGIN', 'http://localhost:' + port)
os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'server.app:app', '--host', '127.0.0.1',
                         '--port', port, '--workers', '1', '--no-access-log'])
