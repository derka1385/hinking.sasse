#!/usr/bin/env python3
"""Recruitment integration checks. Uses temporary private data and no real emails."""
import concurrent.futures
import contextlib
from datetime import datetime, timezone
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('committee_server', ROOT/'site/server/applications.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecruitmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base/'web'
        (self.root/'site/data').mkdir(parents=True)
        (self.root/'site/data/committee-roles.json').write_bytes((ROOT/'site/data/committee-roles.json').read_bytes())
        (self.root/'apply').mkdir()
        (self.root/'apply/index.html').write_text('<h1>Apply</h1>')
        self.app = module.Applications(self.root,self.base/'private','board@example.com',password='a-long-test-password')
        self.role = 'head-finance'

    def tearDown(self):
        self.temporary.cleanup()

    def payload(self, **values):
        return {'firstName':'Åsa','lastName':'Test','email':'asa@example.com','programme':'BSc 2nd year',
                'hasExperience':'yes','experience':'I helped organise a hike.','interests':['Hiking','Mountaineering'],
                'roles':[self.role],'contactConsent':True,'website':'','requestKey':str(uuid4()),**values}

    def create(self, **values):
        result = self.app.submit(self.payload(**values))
        with self.app.db() as db:
            identifier = db.execute('SELECT id FROM applications WHERE reference=?',(result['reference'],)).fetchone()[0]
        return self.app.get_application(identifier)

    def configure(self, **values):
        return self.app.save_settings({'notification_email':'next-board@example.com','public_url':'http://127.0.0.1:4174',
          'smtp_host':'smtp.example.com','smtp_port':587,'smtp_security':'starttls','smtp_sender':'club@example.com',
          'smtp_username':'club@example.com','smtp_password':'private-smtp-password',**values})

    def booking(self, app, local='2099-06-12T10:00', **values):
        return {'applicationId':app['id'],'roleId':self.role,'localStart':local,'duration':20,
                'interviewer':'Åsa committee','location':'SSE, room A; floor 2',**values}

    def test_required_data_and_eight_roles(self):
        self.assertEqual(len(self.app.roles),8)
        self.assertEqual(self.app.meta['programmes'],['BSc 1st year','BSc 2nd year','BSc 3rd year','MSc'])
        for value in [dict(firstName=''),dict(lastName=''),dict(email='bad-email'),dict(email='a@x.com\r\nBcc: x@y.com'),
                      dict(programme='Other'),dict(roles=[]),dict(roles=['invented']),dict(interests=[]),
                      dict(interests=[{}]),dict(contactConsent=False),dict(experience=''),dict(website='spam')]:
            with self.subTest(value=value), self.assertRaises(module.Problem):
                self.app.submit(self.payload(**value))
        app=self.create(hasExperience='no',experience='')
        self.assertEqual(app['experience'],'')
        self.assertNotIn('request_key',app)
        self.assertNotIn('payload_hash',app)

    def test_idempotency_and_persistence(self):
        payload=self.payload()
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.app.submit(payload),range(2)))
        self.assertEqual(results[0],results[1])
        with self.app.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM applications').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
        with self.assertRaises(module.Problem):
            self.app.submit({**payload,'firstName':'Changed'})
        again=module.Applications(self.root,self.base/'private',password='a-long-test-password')
        self.assertEqual(again.list_applications({})['total'],1)
        with self.assertRaises(ValueError):
            module.Applications(self.root,self.root/'data',password='a-long-test-password')

    def test_email_waits_then_sends_once_and_recipient_changes(self):
        self.create()
        sent=[]
        self.app.mailer=lambda job,config:sent.append(job)
        self.assertFalse(self.app.deliver_one())
        settings=self.configure()
        self.assertNotIn('smtp_password',settings)
        self.assertTrue(settings['smtp_password_set'])
        self.assertTrue(self.app.deliver_one())
        self.assertEqual(sent[0]['recipient'],'board@example.com')
        self.assertEqual(sent[0]['reply_to'],'asa@example.com')
        self.assertIn('Head of Finance',sent[0]['body'])
        self.assertIn('BSc 2nd year',sent[0]['body'])
        self.assertFalse(self.app.deliver_one())
        self.create(email='second@example.com')
        self.assertTrue(self.app.deliver_one())
        self.assertEqual(sent[1]['recipient'],'next-board@example.com')

    def test_email_failure_retry_and_password_redaction(self):
        self.create();self.configure()
        def fail(job,config):
            raise RuntimeError('Rejected private-smtp-password')
        self.app.mailer=fail
        for _ in range(5):
            self.assertTrue(self.app.deliver_one())
            with self.app.db() as db:db.execute('UPDATE outbox SET next_attempt=0')
        settings=self.app.settings()
        self.assertEqual(settings['mail_counts']['failed'],1)
        self.assertNotIn('private-smtp-password',settings['last_mail_error'])
        self.app.retry_mail()
        self.app.mailer=lambda job,config:None
        self.assertTrue(self.app.deliver_one())
        self.assertEqual(self.app.settings()['mail_counts']['sent'],1)

    def test_smtp_account_change_requires_its_password(self):
        self.configure()
        with self.assertRaises(module.Problem):
            self.configure(smtp_host='different.example.com',smtp_password='')
        self.assertEqual(self.app.config['smtp_host'],'smtp.example.com')
        self.configure(notification_email='updated@example.com',smtp_password='')
        self.assertEqual(self.app.config['notification_email'],'updated@example.com')

    def test_smtp_uses_tls_and_reply_to(self):
        jobs=[]
        class SMTP:
            def __init__(self,*args,**kwargs):self.tls=False;self.logged=False
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def starttls(self,context):self.tls=True
            def login(self,user,password):self.logged=True
            def send_message(self,message):
                assert self.tls and self.logged
                jobs.append(message)
        app=self.create();self.configure()
        with self.app.db() as db:job=dict(db.execute('SELECT * FROM outbox').fetchone())
        with patch.object(module.smtplib,'SMTP',SMTP):self.app.send_smtp(job,self.app.config)
        self.assertEqual(str(jobs[0]['Reply-To']),app['email'])
        self.assertIn('Åsa',str(jobs[0]['Subject']))

    def test_interview_conflicts_and_atomic_batch(self):
        a,b=self.create(),self.create(email='second@example.com')
        made=self.app.add_interviews([self.booking(a)])
        self.assertEqual(self.app.get_application(a['id'])['status'],'interview')
        with self.assertRaises(module.Problem):self.app.add_interviews([self.booking(b,interviewer='åsa committee')])
        with self.assertRaises(module.Problem):self.app.add_interviews([self.booking(a,interviewer='Another panel')])
        with self.assertRaises(module.Problem):
            self.app.add_interviews([self.booking(b,'2099-06-12T12:00'),self.booking(a,'2099-06-12T12:10')])
        self.assertEqual(len(self.app.interviews()),1)
        self.app.cancel_interview(made['created'][0])
        self.assertEqual(self.app.get_application(a['id'])['status'],'shortlisted')
        self.assertEqual(self.app.interviews(),[])

    def test_concurrent_bookings_cannot_overlap(self):
        a,b=self.create(),self.create(email='second@example.com')
        def book(candidate):
            try:self.app.add_interviews([self.booking(candidate)]);return True
            except module.Problem:return False
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(book,[a,b]))
        self.assertEqual(sum(results),1)

    def test_planner_is_preview_only_and_uses_shortlist(self):
        a,b,c=self.create(),self.create(email='b@example.com'),self.create(email='c@example.com')
        for app in [a,b,c]:self.app.update_application(app['id'],{'status':'shortlisted','notes':'Reviewed'})
        self.create(email='not-shortlisted@example.com')
        self.app.add_interviews([self.booking(a)])
        plan=self.app.plan({'localStart':'2099-06-12T10:00','localEnd':'2099-06-12T11:00','duration':20,'breakMinutes':5,'interviewer':'Åsa committee','roleId':self.role})
        self.assertEqual(len(plan['drafts']),1)
        self.assertEqual(plan['drafts'][0]['localStart'],'2099-06-12T10:20')
        self.assertEqual(len(plan['skipped']),1)
        self.assertEqual(len(self.app.interviews()),1)
        self.app.add_interviews(plan['drafts'])
        self.assertEqual(len(self.app.interviews()),2)

    def test_calendar_escapes_utf8_folds_and_stockholm_time(self):
        app=self.create(firstName='É'*70)
        self.app.add_interviews([self.booking(app)])
        raw=self.app.calendar()
        content=raw.decode('utf-8')
        self.assertIn('DTSTART:20990612T080000Z',content)
        self.assertIn('SSE\\, room A\\; floor 2',content)
        self.assertIn('METHOD:PUBLISH',content)
        self.assertNotIn('ATTENDEE',content)
        self.assertTrue(all(len(line)<=75 for line in raw.split(b'\r\n')))
        for value in ['2027-03-28T02:30','2027-10-31T02:30']:
            with self.assertRaises(module.Problem):module.local_time(value)

    def test_http_auth_origin_and_private_static_paths(self):
        server=module.make_server(self.app,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        port=server.server_address[1]
        def request(method,path,data=None,cookie='',origin=None):
            client=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
            headers={'Content-Type':'application/json','Cookie':cookie}
            if origin:headers['Origin']=origin
            client.request(method,path,body=json.dumps(data).encode() if data is not None else None,headers=headers)
            response=client.getresponse();body=response.read();result=(response.status,dict(response.getheaders()),body);client.close();return result
        try:
            for path in ['applications','settings','interviews','calendar.ics']:
                self.assertEqual(request('GET','/api/committee/'+path)[0],401)
            self.assertEqual(request('POST','/api/committee/apply',self.payload(),origin='https://evil.example')[0],403)
            response=request('POST','/api/committee/apply',self.payload())
            self.assertEqual(response[0],201)
            self.assertNotIn(b'asa@example.com',response[2])
            response=request('POST','/api/committee/login',{'password':'a-long-test-password'})
            self.assertEqual(response[0],200)
            cookie=response[1]['Set-Cookie'];self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
            token=cookie.split(';',1)[0]
            response=request('GET','/api/committee/applications',cookie=token)
            self.assertEqual(json.loads(response[2])['total'],1)
            (self.root/'private-leak.json').symlink_to(self.app.config_path)
            for path in ['/site/server/applications.py','/.git/config','/private-leak.json','/site/%2e%2e/secret.json']:
                self.assertEqual(request('GET',path)[0],404,path)
            self.assertEqual(request('GET','/apply/')[0],200)
            self.assertEqual(request('POST','/api/committee/logout',{},cookie=token)[0],200)
            self.assertEqual(request('GET','/api/committee/applications',cookie=token)[0],401)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    unittest.main(verbosity=2)
