import os
os.environ['DATABASE_URL']='sqlite:///./test.db'
os.environ['JWT_SECRET_KEY']='test-secret-long-enough'
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.core.database import Base, get_db
from app.main import app

engine=create_engine('sqlite:///./test.db',connect_args={'check_same_thread':False})
Base.metadata.create_all(engine)
Session=sessionmaker(bind=engine)

def override_db():
    db=Session()
    try: yield db
    finally: db.close()
app.dependency_overrides[get_db]=override_db
client=TestClient(app)

def test_signup_login_and_me():
    email='test-auth@example.com'
    r=client.post('/api/auth/signup',json={'full_name':'Test User','email':email,'password':'password123','role':'USER'})
    assert r.status_code==201
    token=r.json()['access_token']
    r2=client.post('/api/auth/login',json={'email':email,'password':'password123'})
    assert r2.status_code==200
    r3=client.get('/api/auth/me',headers={'Authorization':f'Bearer {token}'})
    assert r3.status_code==200 and r3.json()['email']==email

def test_duplicate_signup():
    r=client.post('/api/auth/signup',json={'full_name':'Duplicate','email':'test-auth@example.com','password':'password123','role':'USER'})
    assert r.status_code==409

def test_invalid_login():
    r=client.post('/api/auth/login',json={'email':'test-auth@example.com','password':'wrong-password'})
    assert r.status_code==401
