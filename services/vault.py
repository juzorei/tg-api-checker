import hashlib
import hmac
import json
import os
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet


class Vault:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        db = directory / 'history.sqlite'
        secret = directory / 'vault.key'
        if not secret.exists():
            if db.exists():
                raise RuntimeError('Отсутствует vault.key для существующей базы')
            with os.fdopen(os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
                f.write(Fernet.generate_key())
        self.secret = secret.read_bytes()
        self.cipher = Fernet(self.secret)
        self.db = sqlite3.connect(db)
        self.db.execute('CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, owner INTEGER, url TEXT, fingerprint TEXT, payload BLOB, note TEXT DEFAULT "", created TEXT DEFAULT CURRENT_TIMESTAMP, updated TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(owner,url,fingerprint))')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, owner INTEGER, record_id INTEGER, state TEXT, payload BLOB, created TEXT DEFAULT CURRENT_TIMESTAMP)')
        self.db.execute("UPDATE jobs SET state='interrupted' WHERE state='running'")
        self.db.commit()
        for row in self.db.execute('SELECT payload FROM records LIMIT 1'):
            self.cipher.decrypt(row[0])

    def save(self, owner, url, key, result):
        url = url.rstrip('/')
        fingerprint = hmac.new(self.secret, key.encode(), hashlib.sha256).hexdigest()
        payload = self.cipher.encrypt(json.dumps({'key': key, 'result': result}, ensure_ascii=False).encode())
        with self.db:
            self.db.execute('INSERT INTO records(owner,url,fingerprint,payload) VALUES(?,?,?,?) ON CONFLICT(owner,url,fingerprint) DO UPDATE SET payload=excluded.payload,updated=CURRENT_TIMESTAMP', (owner, url, fingerprint, payload))
        return self.db.execute('SELECT id FROM records WHERE owner=? AND url=? AND fingerprint=?', (owner, url, fingerprint)).fetchone()[0]

    def get(self, owner, record_id):
        row = self.db.execute('SELECT id,url,payload,note,created,updated FROM records WHERE owner=? AND id=?', (owner, record_id)).fetchone()
        if not row:
            return None
        payload = json.loads(self.cipher.decrypt(row[2]))
        return dict(id=row[0], url=row[1], note=row[3], created=row[4], updated=row[5], **payload)

    def list(self, owner):
        return [self.get(owner, row[0]) for row in self.db.execute('SELECT id FROM records WHERE owner=? ORDER BY updated DESC,id DESC', (owner,)).fetchall()]

    def delete(self, owner, record_id):
        with self.db:
            self.db.execute('DELETE FROM jobs WHERE owner=? AND record_id=?', (owner, record_id))
            self.db.execute('DELETE FROM records WHERE owner=? AND id=?', (owner, record_id))

    def job_create(self, owner, rid, payload):
        encrypted = self.cipher.encrypt(json.dumps(payload).encode())
        with self.db:
            cursor = self.db.execute("INSERT INTO jobs(owner,record_id,state,payload) VALUES(?,?,'running',?)", (owner,rid,encrypted))
        return cursor.lastrowid

    def job_save(self, owner, jid, state, payload):
        encrypted = self.cipher.encrypt(json.dumps(payload).encode())
        with self.db:
            self.db.execute('UPDATE jobs SET state=?,payload=? WHERE owner=? AND id=?', (state,encrypted,owner,jid))

    def jobs(self, owner, rid):
        rows = self.db.execute('SELECT id,state,payload,created FROM jobs WHERE owner=? AND record_id=? ORDER BY id DESC', (owner,rid)).fetchall()
        return [dict(id=r[0],state=r[1],data=json.loads(self.cipher.decrypt(r[2])),created=r[3]) for r in rows]

    def note(self, owner, record_id, text):
        with self.db:
            self.db.execute('UPDATE records SET note=? WHERE owner=? AND id=?', (text[:120], owner, record_id))
