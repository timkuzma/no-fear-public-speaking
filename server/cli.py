"""Operator-issued invitations and recovery codes; run only after identity checking."""
import argparse
import hashlib
import os
import secrets
from pathlib import Path
from .locking import data_lock
from .store import Store, now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', default=os.environ.get('DATA_DIR', str(Path(__file__).resolve().parent.parent / 'data')))
    commands = parser.add_subparsers(dest='command', required=True)
    invite = commands.add_parser('invite')
    invite.add_argument('--uses', type=int, default=1)
    invite.add_argument('--hours', type=int, default=72)
    reset = commands.add_parser('reset')
    reset.add_argument('email')
    reset.add_argument('--minutes', type=int, default=30)
    args = parser.parse_args()
    with data_lock(args.data_dir, shared=True):
        store = Store(args.data_dir)
        raw = secrets.token_urlsafe(32)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        if args.command == 'invite':
            if not 1 <= args.uses <= 100 or not 1 <= args.hours <= 720:
                parser.error('uses must be 1–100 and hours 1–720')
            store.execute('INSERT INTO invites VALUES(?,?,?)', (hashed, now() + args.hours * 3600, args.uses))
        else:
            if not 1 <= args.minutes <= 120:
                parser.error('minutes must be 1–120')
            user = store.one('SELECT id FROM users WHERE email=?', (args.email.strip().lower(),))
            if not user:
                parser.error('account not found')
            with store.connect() as db:
                db.execute('DELETE FROM resets WHERE user_id=?', (user['id'],))
                db.execute('INSERT INTO resets VALUES(?,?,?)', (hashed, user['id'], now() + args.minutes * 60))
        print(raw)


if __name__ == '__main__':
    main()
