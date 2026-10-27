#!/usr/bin/env python3
"""Local website + private committee applications, SQLite, SMTP outbox and calendar.

No third-party packages. Runtime records and credentials live outside the web root.
"""
import argparse
import contextlib
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http.cookies import SimpleCookie, CookieError
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

UTC = timezone.utc
STOCKHOLM = ZoneInfo('Europe/Stockholm')
STATUSES = ['new', 'reviewed', 'shortlisted', 'interview', 'accepted', 'not-selected']
COOKIE = 'hc_committee_session'


class Problem(Exception):
    def __init__(self, message, status=400, fields=None):
        self.message, self.status, self.fields = message, status, fields or {}


def stamp(dt=None):
    return (dt or datetime.now(UTC)).astimezone(UTC).isoformat(timespec='seconds')


def text(value, label, maximum=200, required=True):
    if not isinstance(value, str):
        raise Problem(f'{label} is invalid.')
    value = value.strip()
    if (required and not value) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise Problem(f'Please check {label.lower()}.')
    return value


def email(value):
    value = text(value, 'Email', 254)
    if not re.fullmatch(r"[^\s<>@,;:]+@[^\s<>@,;:]+\.[^\s<>@,;:]+", value):
        raise Problem('Please enter a valid email address.')
    return value


def integer(value, label, low, high):
    if isinstance(value, bool):
        raise Problem(f'{label} is invalid.')
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise Problem(f'{label} is invalid.')
    if str(result) != str(value) or not low <= result <= high:
        raise Problem(f'{label} must be between {low} and {high}.')
    return result


def local_time(value):
    try:
        raw = datetime.strptime(value, '%Y-%m-%dT%H:%M')
    except (TypeError, ValueError):
        raise Problem('Choose a valid interview date and time.')
    local = raw.replace(tzinfo=STOCKHOLM)
    if local.astimezone(UTC).astimezone(STOCKHOLM).replace(tzinfo=None) != raw:
        raise Problem('This time does not exist in Stockholm because of daylight saving time.')
    if local.utcoffset() != local.replace(fold=1).utcoffset():
        raise Problem('This time is ambiguous in Stockholm. Please choose another time.')
    return local.astimezone(UTC)


def private_json(path, data):
    temporary = path.with_suffix('.tmp')
    with open(temporary, 'w', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


class Applications:
    def __init__(self, root, data_dir, recipient='', password=None):
        self.root, self.data_dir = Path(root).resolve(), Path(data_dir).resolve()
        if self.root == self.data_dir or self.root in self.data_dir.parents:
            raise ValueError('Application data must live outside the web root.')
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.data_dir, 0o700)
        self.meta = json.loads((self.root / 'site/data/committee-roles.json').read_text())
        self.roles = {r['id']: r for r in self.meta['roles']}
        self.config_path = self.data_dir / 'settings.json'
        self.lock = threading.RLock()
        self.config = json.loads(self.config_path.read_text()) if self.config_path.exists() else {
            'notification_email': recipient, 'public_url': 'http://127.0.0.1:4174',
            'smtp_host': '', 'smtp_port': 587, 'smtp_security': 'starttls',
            'smtp_username': '', 'smtp_password': '', 'smtp_sender': ''}
        private_json(self.config_path, self.config)
        self.password_path = self.data_dir / 'admin-password.txt'
        if password is None:
            if not self.password_path.exists():
                with open(self.password_path, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
                    stream.write(secrets.token_urlsafe(24) + '\n')
            password = self.password_path.read_text().strip()
        if len(password) < 12:
            raise ValueError('The admin password must have at least 12 characters.')
        self.salt = secrets.token_bytes(32)
        self.password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), self.salt, 240000)
        self.sessions, self.rates = {}, {}
        self.db_path = self.data_dir / 'applications.sqlite3'
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS applications (
              id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE, request_key TEXT NOT NULL UNIQUE,
              payload_hash TEXT NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
              email TEXT NOT NULL, programme TEXT NOT NULL, has_experience TEXT NOT NULL,
              experience TEXT NOT NULL, interests TEXT NOT NULL, roles TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'new', notes TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
              id TEXT PRIMARY KEY, application_id TEXT REFERENCES applications(id),
              recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
              reply_to TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
              attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
              last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, sent_at TEXT);
            CREATE TABLE IF NOT EXISTS interviews (
              id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(id),
              role_id TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
              interviewer TEXT NOT NULL, location TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled',
              created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS applications_created ON applications(created_at);
            CREATE INDEX IF NOT EXISTS interviews_times ON interviews(starts_at, ends_at);
            ''')
            db.execute("UPDATE outbox SET status='pending' WHERE status='sending'")
        os.chmod(self.db_path, 0o600)
        self.wake, self.stop = threading.Event(), threading.Event()
        self.mail_lock = threading.Lock()
        self.mailer = self.send_smtp

    @contextlib.contextmanager
    def db(self):
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def rate(self, key, maximum, seconds):
        now = time.monotonic()
        with self.lock:
            self.rates = {k: [t for t in v if now-t < seconds] for k, v in self.rates.items()}
            values = self.rates.setdefault(key, [])
            if len(values) >= maximum:
                raise Problem('Too many attempts. Please try again later.', 429)
            values.append(now)

    def login(self, password):
        if not isinstance(password, str) or len(password) > 500:
            raise Problem('Incorrect password.', 401)
        check = hashlib.pbkdf2_hmac('sha256', password.encode(), self.salt, 240000)
        if not hmac.compare_digest(check, self.password_hash):
            raise Problem('Incorrect password.', 401)
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.sessions = {k: v for k, v in self.sessions.items() if v > time.time()}
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = time.time()+8*3600
        return token

    def authenticated(self, token):
        with self.lock:
            return self.sessions.get(hashlib.sha256(token.encode()).hexdigest(), 0) > time.time()

    def logout(self, token):
        with self.lock:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    def submit(self, data):
        if data.get('website'):
            raise Problem('Please leave the website field empty.')
        fields = {}
        for name, label in [('firstName', 'First name'), ('lastName', 'Last name'), ('email', 'Email')]:
            try:
                fields[name] = email(data.get(name)) if name == 'email' else text(data.get(name), label, 80)
            except Problem as error:
                raise Problem(error.message, fields={name: error.message})
        if data.get('programme') not in self.meta['programmes']:
            raise Problem('Choose your programme and year.', fields={'programme': 'Choose your programme and year.'})
        if data.get('hasExperience') not in ['yes', 'no']:
            raise Problem('Tell us whether you have previous experience.', fields={'hasExperience': 'Choose yes or no.'})
        experience = data.get('experience', '')
        if not isinstance(experience, str) or len(experience) > 5000 or '\x00' in experience:
            raise Problem('Experience must be no longer than 5,000 characters.', fields={'experience': 'Use up to 5,000 characters.'})
        if data['hasExperience'] == 'yes' and not experience.strip():
            raise Problem('Tell us a little about your experience.', fields={'experience': 'Tell us a little about your experience.'})
        for key, allowed in [('interests', self.meta['interests']), ('roles', self.roles)]:
            values = data.get(key)
            if not isinstance(values, list) or not values or len(values) > len(allowed) or any(not isinstance(v, str) or v not in allowed for v in values) or len(set(values)) != len(values):
                raise Problem('Select at least one ' + ('interest.' if key == 'interests' else 'role.'), fields={key: 'Select at least one option.'})
        if data.get('contactConsent') is not True:
            raise Problem('Please confirm that we may contact you about your application.', fields={'contactConsent': 'Please confirm.'})
        key = text(data.get('requestKey'), 'Request reference', 100)
        payload = {**fields, 'programme': data['programme'], 'hasExperience': data['hasExperience'],
                   'experience': experience.strip(), 'interests': data['interests'], 'roles': data['roles']}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        identifier, now = str(uuid4()), stamp()
        reference = 'HC-' + identifier[:8].upper()
        with self.lock:
            recipient = self.config['notification_email']
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT reference,payload_hash FROM applications WHERE request_key=?', (key,)).fetchone()
            if prior:
                if prior['payload_hash'] != digest:
                    raise Problem('This submission reference has already been used. Please reload the form.', 409)
                return {'reference': prior['reference']}
            db.execute('''INSERT INTO applications
              (id,reference,request_key,payload_hash,first_name,last_name,email,programme,has_experience,experience,interests,roles,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (identifier,reference,key,digest,fields['firstName'],fields['lastName'],fields['email'],data['programme'],data['hasExperience'],experience.strip(),json.dumps(data['interests']),json.dumps(data['roles']),now,now))
            role_names = '\n'.join('- '+self.roles[r]['name'] for r in data['roles'])
            body = (f"New committee application {reference}\n\nName: {fields['firstName']} {fields['lastName']}\n"
                    f"Email: {fields['email']}\nProgramme: {data['programme']}\nInterests: {', '.join(data['interests'])}\n"
                    f"\nApplied roles:\n{role_names}\n\nPrevious experience: {data['hasExperience']}\n{experience.strip() or 'No additional details.'}\n\n"
                    f"Review privately: {self.config['public_url'].rstrip('/')}/committee/#{identifier}\n")
            self.queue(db, recipient, f"Committee application — {fields['firstName']} {fields['lastName']}", body, identifier, fields['email'])
        self.wake.set()
        return {'reference': reference}

    @staticmethod
    def queue(db, recipient, subject, body, application_id=None, reply_to=''):
        db.execute('INSERT INTO outbox (id,application_id,recipient,subject,body,reply_to,created_at) VALUES (?,?,?,?,?,?,?)',
                   (str(uuid4()), application_id, recipient, subject, body, reply_to, stamp()))

    @staticmethod
    def application(row):
        result = dict(row)
        for key in ['roles', 'interests']:
            result[key] = json.loads(result[key])
        result.pop('request_key', None)
        result.pop('payload_hash', None)
        return result

    def list_applications(self, query):
        conditions, values = [], []
        for key in ['status', 'programme']:
            if query.get(key):
                conditions.append(key+'=?'); values.append(query[key])
        if query.get('role'):
            conditions.append('roles LIKE ?'); values.append('%"'+query['role']+'"%')
        if query.get('search'):
            conditions.append("(first_name||' '||last_name||' '||email) LIKE ?")
            values.append('%'+query['search'][:150]+'%')
        offset = integer(query.get('offset', '0'), 'Page', 0, 1000000)
        where = ' WHERE '+' AND '.join(conditions) if conditions else ''
        with self.db() as db:
            total = db.execute('SELECT COUNT(*) FROM applications'+where, values).fetchone()[0]
            rows = db.execute('SELECT * FROM applications'+where+' ORDER BY created_at DESC,id LIMIT 50 OFFSET ?', values+[offset]).fetchall()
            counts = dict(db.execute('SELECT status,COUNT(*) FROM applications GROUP BY status').fetchall())
        return {'items': [self.application(r) for r in rows], 'total': total, 'offset': offset, 'limit': 50, 'counts': counts}

    def get_application(self, identifier, db=None):
        if db is None:
            with self.db() as connection:
                return self.get_application(identifier, connection)
        row = db.execute('SELECT * FROM applications WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise Problem('Application not found.', 404)
        return self.application(row)

    def update_application(self, identifier, data):
        if data.get('status') not in STATUSES:
            raise Problem('Choose a valid application status.')
        notes = data.get('notes', '')
        if not isinstance(notes, str) or len(notes) > 8000 or '\x00' in notes:
            raise Problem('Notes must be no longer than 8,000 characters.')
        with self.db() as db:
            self.get_application(identifier, db)
            db.execute('UPDATE applications SET status=?,notes=?,updated_at=? WHERE id=?', (data['status'],notes,stamp(),identifier))
        return self.get_application(identifier)

    def interviews(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('''SELECT i.*,a.first_name,a.last_name,a.email,a.programme
              FROM interviews i JOIN applications a ON a.id=i.application_id
              WHERE i.status='scheduled' ORDER BY i.starts_at,i.id''')]

    @staticmethod
    def conflict(db, application_id, interviewer, start, end):
        rows = db.execute('''SELECT application_id,interviewer FROM interviews WHERE status='scheduled'
          AND starts_at < ? AND ends_at > ?''', (stamp(end),stamp(start))).fetchall()
        return any(r['application_id']==application_id or r['interviewer'].casefold()==interviewer.casefold() for r in rows)

    def add_interviews(self, drafts):
        if not isinstance(drafts, list) or not 1 <= len(drafts) <= 200:
            raise Problem('Choose between 1 and 200 interviews.')
        made = []
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for item in drafts:
                if not isinstance(item, dict):
                    raise Problem('Invalid interview.')
                app = self.get_application(item.get('applicationId', ''), db)
                role = item.get('roleId')
                if role not in app['roles']:
                    raise Problem('The interview role must be one the candidate applied for.')
                start = local_time(item.get('localStart'))
                if start <= datetime.now(UTC):
                    raise Problem('Choose a future interview time.')
                end = start + timedelta(minutes=integer(item.get('duration',20), 'Duration', 10, 120))
                interviewer = text(item.get('interviewer','Committee'), 'Interviewer', 120)
                location = text(item.get('location',''), 'Location', 500, False)
                if self.conflict(db, app['id'], interviewer, start, end):
                    raise Problem('This slot overlaps another interview for the candidate or interviewer. Refresh the agenda.', 409)
                identifier = str(uuid4())
                db.execute('INSERT INTO interviews (id,application_id,role_id,starts_at,ends_at,interviewer,location,created_at) VALUES (?,?,?,?,?,?,?,?)',
                           (identifier,app['id'],role,stamp(start),stamp(end),interviewer,location,stamp()))
                db.execute("UPDATE applications SET status='interview',updated_at=? WHERE id=?", (stamp(),app['id']))
                made.append(identifier)
        return {'created': made}

    def plan(self, data):
        start, end = local_time(data.get('localStart')), local_time(data.get('localEnd'))
        if start <= datetime.now(UTC) or end <= start or end-start > timedelta(hours=16):
            raise Problem('Choose a future interview window of up to 16 hours.')
        minutes = integer(data.get('duration',20), 'Duration', 10, 120)
        pause = integer(data.get('breakMinutes',5), 'Break', 0, 60)
        interviewer = text(data.get('interviewer','Committee'), 'Interviewer', 120)
        location = text(data.get('location',''), 'Location', 500, False)
        role = data.get('roleId','')
        if role and role not in self.roles:
            raise Problem('Choose a valid role.')
        existing = self.interviews()
        already = {x['application_id'] for x in existing}
        with self.db() as db:
            candidates = [self.application(r) for r in db.execute("SELECT * FROM applications WHERE status='shortlisted' ORDER BY created_at,id")]
        candidates = [a for a in candidates if a['id'] not in already and (not role or role in a['roles'])]
        order = list(self.roles)
        candidates.sort(key=lambda a: (order.index(role or a['roles'][0]), a['created_at'], a['id']))
        drafts, skipped = [], []
        for app in candidates:
            while start+timedelta(minutes=minutes) <= end:
                finish = start+timedelta(minutes=minutes)
                busy = any(x['interviewer'].casefold()==interviewer.casefold() and datetime.fromisoformat(x['starts_at']) < finish and datetime.fromisoformat(x['ends_at']) > start for x in existing)
                if not busy:
                    break
                start += timedelta(minutes=5)
            if start+timedelta(minutes=minutes) > end:
                skipped.append({'name': app['first_name']+' '+app['last_name'], 'reason': 'No slot left in this window.'})
                continue
            drafts.append({'applicationId': app['id'], 'name': app['first_name']+' '+app['last_name'],
              'roleId': role or app['roles'][0], 'localStart': start.astimezone(STOCKHOLM).strftime('%Y-%m-%dT%H:%M'),
              'duration': minutes, 'interviewer': interviewer, 'location': location})
            start += timedelta(minutes=minutes+pause)
        return {'drafts': drafts, 'skipped': skipped}

    def cancel_interview(self, identifier):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT application_id FROM interviews WHERE id=? AND status='scheduled'", (identifier,)).fetchone()
            if row is None:
                raise Problem('Interview not found.', 404)
            db.execute("UPDATE interviews SET status='cancelled' WHERE id=?", (identifier,))
            other = db.execute("SELECT 1 FROM interviews WHERE application_id=? AND status='scheduled'", (row[0],)).fetchone()
            if not other:
                db.execute("UPDATE applications SET status='shortlisted',updated_at=? WHERE id=? AND status='interview'", (stamp(),row[0]))
        return {'cancelled': True}

    def settings(self):
        with self.lock:
            result = {k: v for k, v in self.config.items() if k != 'smtp_password'}
            result['smtp_password_set'] = bool(self.config.get('smtp_password'))
        result['smtp_ready'] = self.smtp_ready()
        with self.db() as db:
            result['mail_counts'] = dict(db.execute('SELECT status,COUNT(*) FROM outbox GROUP BY status').fetchall())
            last = db.execute("SELECT last_error FROM outbox WHERE last_error!='' ORDER BY created_at DESC LIMIT 1").fetchone()
            result['last_mail_error'] = last[0] if last else ''
        return result

    def smtp_ready(self):
        with self.lock:
            return bool(self.config.get('smtp_host') and self.config.get('smtp_sender') and self.config.get('notification_email'))

    def save_settings(self, data):
        with self.lock:
            config = dict(self.config)
            config['notification_email'] = email(data.get('notification_email'))
            public = text(data.get('public_url',config['public_url']), 'Website URL', 500)
            parsed = urlsplit(public)
            if parsed.scheme not in ['http','https'] or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise Problem('Enter a valid website URL without credentials or query parameters.')
            config['public_url'] = public.rstrip('/')
            host = text(data.get('smtp_host',''), 'SMTP host', 250, False)
            if host and not re.fullmatch(r'[A-Za-z0-9.-]+', host):
                raise Problem('Enter the SMTP hostname without a URL or path.')
            config['smtp_host'] = host
            config['smtp_port'] = integer(data.get('smtp_port',587), 'SMTP port', 1, 65535)
            if data.get('smtp_security') not in ['starttls','ssl']:
                raise Problem('Choose STARTTLS or SSL/TLS.')
            config['smtp_security'] = data['smtp_security']
            config['smtp_username'] = text(data.get('smtp_username',''), 'SMTP username', 250, False)
            sender = text(data.get('smtp_sender',''), 'Sender email', 254, False)
            config['smtp_sender'] = email(sender) if sender else ''
            password = data.get('smtp_password','')
            if not isinstance(password, str) or len(password) > 1000 or '\x00' in password:
                raise Problem('Invalid SMTP password.')
            account_changed = host != self.config.get('smtp_host') or config['smtp_username'] != self.config.get('smtp_username')
            if account_changed and config['smtp_username'] and self.config.get('smtp_password') and not password:
                raise Problem('Re-enter the SMTP password when changing the host or username.')
            if password:
                config['smtp_password'] = password
            if config['smtp_username'] and host and not config['smtp_password']:
                raise Problem('Enter the SMTP password for this username.')
            if host and not config['smtp_sender']:
                raise Problem('Enter the sender email address.')
            private_json(self.config_path, config)
            self.config = config
        self.wake.set()
        return self.settings()

    def test_email(self):
        if not self.smtp_ready():
            raise Problem('Configure the SMTP sender first.', 422)
        with self.db() as db:
            self.queue(db, self.config['notification_email'], 'Hiking Club — email delivery test', 'The committee email connection is working. This is a test, not an application.')
        self.wake.set()
        return {'queued': True}

    def retry_mail(self):
        if not self.smtp_ready():
            raise Problem('Configure the SMTP sender first.', 422)
        with self.db() as db:
            db.execute("UPDATE outbox SET status='pending',attempts=0,next_attempt=0,last_error='' WHERE status='failed'")
        self.wake.set()
        return {'queued': True}

    @staticmethod
    def send_smtp(job, config):
        message = EmailMessage()
        message['From'], message['To'], message['Subject'] = config['smtp_sender'], job['recipient'], job['subject']
        message['Message-ID'] = '<'+job['id']+'@'+config['smtp_sender'].split('@')[-1]+'>'
        if job['reply_to']:
            message['Reply-To'] = job['reply_to']
        message.set_content(job['body'])
        secure = ssl.create_default_context()
        if config['smtp_security'] == 'ssl':
            smtp = smtplib.SMTP_SSL(config['smtp_host'],config['smtp_port'],timeout=20,context=secure)
        else:
            smtp = smtplib.SMTP(config['smtp_host'],config['smtp_port'],timeout=20)
        with smtp:
            if config['smtp_security'] == 'starttls':
                smtp.starttls(context=secure)
            if config['smtp_username']:
                smtp.login(config['smtp_username'],config['smtp_password'])
            smtp.send_message(message)

    def deliver_one(self):
        if not self.mail_lock.acquire(blocking=False):
            return False
        try:
            if not self.smtp_ready():
                return False
            with self.lock:
                config = dict(self.config)
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute("SELECT * FROM outbox WHERE status='pending' AND next_attempt<=? ORDER BY created_at LIMIT 1", (time.time(),)).fetchone()
                if row is None:
                    return False
                job = dict(row)
                if not job['recipient']:
                    job['recipient'] = config['notification_email']
                db.execute("UPDATE outbox SET status='sending' WHERE id=?", (job['id'],))
            try:
                self.mailer(job, config)
            except Exception as error:
                attempts = job['attempts']+1
                with self.db() as db:
                    detail = str(error).replace(config.get('smtp_password') or '\x00','[hidden]')[:500]
                    db.execute('UPDATE outbox SET status=?,attempts=?,next_attempt=?,last_error=? WHERE id=?',
                        ('failed' if attempts>=5 else 'pending',attempts,time.time()+min(3600,30*2**attempts),detail,job['id']))
            else:
                with self.db() as db:
                    db.execute("UPDATE outbox SET status='sent',sent_at=?,last_error='' WHERE id=?", (stamp(),job['id']))
            return True
        finally:
            self.mail_lock.release()

    def worker(self):
        while not self.stop.is_set():
            try:
                while not self.stop.is_set() and self.deliver_one():
                    pass
            except Exception:
                logging.exception('Email queue temporarily unavailable')
            self.wake.wait(15)
            self.wake.clear()

    def calendar(self):
        def escape(value):
            return value.replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
        lines = ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Hiking Club//Committee interviews//EN','CALSCALE:GREGORIAN','METHOD:PUBLISH','X-WR-CALNAME:Hiking Club committee interviews','X-WR-TIMEZONE:Europe/Stockholm']
        for item in self.interviews():
            role = self.roles[item['role_id']]['name']
            lines += ['BEGIN:VEVENT','UID:'+item['id']+'@hikingclub.local','DTSTAMP:'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'),
              'DTSTART:'+datetime.fromisoformat(item['starts_at']).strftime('%Y%m%dT%H%M%SZ'),
              'DTEND:'+datetime.fromisoformat(item['ends_at']).strftime('%Y%m%dT%H%M%SZ'),
              'SUMMARY:'+escape(role+' — '+item['first_name']+' '+item['last_name']),
              'DESCRIPTION:'+escape('Candidate: '+item['first_name']+' '+item['last_name']+'\nEmail: '+item['email']+'\nProgramme: '+item['programme']+'\nRole: '+role+'\nInterviewer: '+item['interviewer']),
              'LOCATION:'+escape(item['location']),'STATUS:CONFIRMED','END:VEVENT']
        lines.append('END:VCALENDAR')
        folded = []
        for line in lines:
            chunk = ''
            for char in line:
                if len((chunk+char).encode('utf-8')) > 75:
                    folded.append(chunk)
                    chunk = ' '
                chunk += char
            folded.append(chunk)
        return ('\r\n'.join(folded)+'\r\n').encode('utf-8')


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server, directory=str(server.application.root))

    @property
    def app(self):
        return self.server.application

    def end_headers(self):
        if urlsplit(self.path).path.startswith(('/committee','/apply')):
            self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        super().end_headers()

    def log_message(self, fmt, *args):
        # Request bodies, submitted answers and passwords are never logged.
        logging.info('%s %s', self.command, urlsplit(self.path).path)

    def respond(self, data, status=200, cookie=None, content_type='application/json; charset=utf-8'):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(body)

    def checked_host(self):
        raw = self.headers.get('Host','')
        try:
            parsed = urlsplit('http://'+raw)
            valid = parsed.hostname in self.server.allowed_hosts and not parsed.username and not parsed.password and not parsed.path
        except ValueError:
            valid = False
        if not valid:
            raise Problem('This host is not allowed.', 403)
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://'+raw,'https://'+raw):
            raise Problem('This origin is not allowed.', 403)

    def body(self):
        if self.headers.get('Transfer-Encoding'):
            self.close_connection = True
            raise Problem('Unsupported request encoding.', 400)
        try:
            size = int(self.headers.get('Content-Length','0'))
        except ValueError:
            raise Problem('Invalid request length.')
        if not 0 < size <= 40000:
            self.close_connection = True
            raise Problem('Request is too large or empty.', 413)
        if self.headers.get_content_type() != 'application/json':
            raise Problem('Send the form as JSON.', 415)
        try:
            value = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            raise Problem('Invalid request data.')
        if not isinstance(value, dict):
            raise Problem('Invalid request data.')
        return value

    def token(self):
        try:
            jar = SimpleCookie(self.headers.get('Cookie',''))
            return jar[COOKIE].value if COOKIE in jar else ''
        except CookieError:
            return ''

    def cookie(self, token, expire=False):
        value = f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if expire else 28800}'
        if self.server.secure_cookie:
            value += '; Secure'
        return value

    def api(self):
        try:
            self.checked_host()
            path = urlsplit(self.path).path.rstrip('/')
            method = self.command
            if path == '/api/committee/apply' and method == 'POST':
                self.app.rate('apply:'+self.client_address[0], 20, 900)
                return self.respond(self.app.submit(self.body()), 201)
            if path == '/api/committee/login' and method == 'POST':
                self.app.rate('login:'+self.client_address[0], 10, 600)
                return self.respond({'authenticated': True}, cookie=self.cookie(self.app.login(self.body().get('password'))))
            if not self.app.authenticated(self.token()):
                raise Problem('Sign in to the committee workspace.', 401)
            data = self.body() if method in ['POST','PATCH','DELETE'] else {}
            if path == '/api/committee/session' and method == 'GET':
                return self.respond({'authenticated': True})
            if path == '/api/committee/logout' and method == 'POST':
                self.app.logout(self.token())
                return self.respond({'authenticated': False}, cookie=self.cookie('',True))
            if path == '/api/committee/applications' and method == 'GET':
                query = {k:v[0] for k,v in parse_qs(urlsplit(self.path).query).items()}
                return self.respond(self.app.list_applications(query))
            prefix = '/api/committee/applications/'
            if path.startswith(prefix) and method in ['GET','PATCH']:
                identifier = path[len(prefix):]
                return self.respond(self.app.get_application(identifier) if method == 'GET' else self.app.update_application(identifier,data))
            if path == '/api/committee/interviews':
                if method == 'GET':
                    return self.respond({'items': self.app.interviews()})
                if method == 'POST':
                    return self.respond(self.app.add_interviews(data.get('interviews')),201)
            if path.startswith('/api/committee/interviews/') and method == 'DELETE':
                return self.respond(self.app.cancel_interview(path.rsplit('/',1)[-1]))
            if path == '/api/committee/planner' and method == 'POST':
                return self.respond(self.app.plan(data))
            if path == '/api/committee/calendar.ics' and method == 'GET':
                return self.respond(self.app.calendar(),content_type='text/calendar; charset=utf-8')
            if path == '/api/committee/settings':
                if method == 'GET':
                    return self.respond(self.app.settings())
                if method == 'POST':
                    return self.respond(self.app.save_settings(data))
            if path == '/api/committee/email-test' and method == 'POST':
                return self.respond(self.app.test_email(),202)
            if path == '/api/committee/email-retry' and method == 'POST':
                return self.respond(self.app.retry_mail(),202)
            raise Problem('Not found.',404)
        except Problem as error:
            self.respond({'error':error.message,'fields':error.fields},error.status)
        except Exception:
            logging.exception('Committee request failed')
            self.respond({'error':'Something went wrong. Please try again.'},500)

    def do_GET(self):
        if urlsplit(self.path).path.startswith('/api/'):
            return self.api()
        try:
            self.checked_host()
            path = unquote(urlsplit(self.path).path)
            pieces = Path(path).parts
            if any(part.startswith('.') or part in ['server','tools','graphify-out','storage-cleanup','brand-figma'] for part in pieces):
                raise Problem('Not found.',404)
            target = Path(self.translate_path(self.path)).resolve()
            if target != self.app.root and self.app.root not in target.parents:
                raise Problem('Not found.',404)
            allowed = {'.html','.css','.js','.json','.bin','.svg','.webp','.png','.jpg','.jpeg','.woff2','.woff','.ico','.mp4','.webm','.pdf'}
            if not target.is_dir() and target.suffix.lower() not in allowed:
                raise Problem('Not found.',404)
            return super().do_GET()
        except Problem as error:
            self.respond({'error':error.message},error.status)

    def do_HEAD(self):
        try:
            self.checked_host()
        except Problem:
            self.send_error(403); return
        # Do not bypass GET's static-path checks through SimpleHTTPRequestHandler.do_HEAD.
        self.send_error(405)

    def do_POST(self): self.api()
    def do_PATCH(self): self.api()
    def do_DELETE(self): self.api()
    def list_directory(self, path): self.send_error(404); return None


def make_server(app, port=4174, bind='127.0.0.1', allowed_hosts=None, secure_cookie=False):
    server = ThreadingHTTPServer((bind,port), Handler)
    server.daemon_threads = True
    server.application = app
    server.allowed_hosts = set(allowed_hosts or ['127.0.0.1','localhost'])
    server.secure_cookie = secure_cookie
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--data-dir',type=Path,default=Path.home()/'Document/HikingClubData')
    parser.add_argument('--notify-email',default='')
    parser.add_argument('--port',type=int,default=4174)
    args = parser.parse_args()
    os.umask(0o077)
    app = Applications(args.root,args.data_dir,args.notify_email,password=os.environ.get('HC_ADMIN_PASSWORD'))
    server = make_server(app,args.port)
    thread = threading.Thread(target=app.worker,daemon=True)
    thread.start()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    print(f'Applications: http://127.0.0.1:{args.port}/apply/',flush=True)
    print(f'Committee: http://127.0.0.1:{args.port}/committee/',flush=True)
    print(f'Private data: {app.data_dir}',flush=True)
    if 'HC_ADMIN_PASSWORD' not in os.environ:
        print(f'Admin password file: {app.password_path}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop.set(); app.wake.set(); server.server_close()


if __name__ == '__main__':
    main()
