# encryption.py
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import os

def get_cipher():
    SALT = os.getenv('ENCRYPTION_SALT', 'default_salt').encode()
    PASSPHRASE = os.getenv('ENCRYPTION_PASSPHRASE', 'default_pass').encode()
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
        backend=default_backend()
    )
    ENCRYPTION_KEY = base64.urlsafe_b64encode(kdf.derive(PASSPHRASE))
    return Fernet(ENCRYPTION_KEY)

def encrypt_session(session_str: str) -> str:
    cipher_suite = get_cipher()
    encrypted = cipher_suite.encrypt(session_str.encode())
    return encrypted.decode()

def decrypt_session(enc: str) -> str:
    cipher_suite = get_cipher()
    return cipher_suite.decrypt(enc.encode()).decode()