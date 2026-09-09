"""Create private first-run configuration; never print credentials."""
from pathlib import Path
import secrets

root=Path(__file__).resolve().parent
target=root/'.env'
if not target.exists():
    content=(root/'.env.example').read_text(encoding='utf-8')
    content=content.replace('RADAR_ADMIN_PASSWORD=','RADAR_ADMIN_PASSWORD='+secrets.token_urlsafe(20),1)
    target.write_text(content,encoding='utf-8')
    print('Created private .env. Review locally; credentials are not printed.')
else:
    print('Existing private .env preserved.')
