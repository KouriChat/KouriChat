import pytest
from flask import Flask, session
from network.routes.http_routes.base_routes import BaseRoutes
from utils.token_config import TokenConfig
from config import SettingReader
import hashlib
import json

@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test_secret_key'
    app.config['TESTING'] = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def base_routes(app):
    return BaseRoutes(app)

@pytest.fixture
def mock_config(monkeypatch):
    mock_settings = {
        'categories': {
            'auth_settings': {
                'settings': {
                    'admin_password': {
                        'value': hashlib.sha256('test_password'.encode()).hexdigest()
                    }
                }
            }
        }
    }
    
    def mock_get_config():
        return mock_settings
    
    monkeypatch.setattr(SettingReader, 'get_config', mock_get_config)
    return mock_settings

def test_index(client, base_routes):
    response = client.get('/')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'ok'
    assert data['message'] == 'KouriChat server is running'

def test_login_success(client, base_routes, mock_config):
    response = client.post('/login',
                         json={'password': 'test_password', 'remember_me': True})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'success'
    assert data['message'] == '登录成功'
    assert 'token' in data
    with client.session_transaction() as sess:
        assert sess['logged_in'] is True

def test_login_wrong_password(client, base_routes, mock_config):
    response = client.post('/login',
                         json={'password': 'wrong_password'})
    assert response.status_code == 401
    data = json.loads(response.data)
    assert data['status'] == 'error'
    assert data['message'] == '密码错误'

def test_login_empty_password(client, base_routes, mock_config):
    response = client.post('/login',
                         json={'password': ''})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['status'] == 'error'
    assert data['message'] == '密码不能为空'

def test_login_no_password_initialized(client, base_routes, monkeypatch):
    mock_settings = {
        'categories': {
            'auth_settings': {
                'settings': {
                    'admin_password': {
                        'value': ''
                    }
                }
            }
        }
    }
    
    def mock_get_config():
        return mock_settings
    
    monkeypatch.setattr(SettingReader, 'get_config', mock_get_config)
    
    response = client.post('/login',
                         json={'password': 'test_password'})
    assert response.status_code == 403
    data = json.loads(response.data)
    assert data['status'] == 'error'
    assert data['message'] == '需要先初始化密码'

def test_init_password(client, base_routes):
    response = client.post('/init_password')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'ok'
    assert data['message'] == 'init password success'

def test_logout(client, base_routes):
    response = client.get('/logout')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'ok'
    assert data['message'] == 'logout success'