import base64
import hashlib


def _derive_key(secret):
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_message(message, secret):
    if secret is None:
        return message
    data = message.encode("utf-8")
    key = _derive_key(secret)
    encrypted = bytes(value ^ key[index % len(key)] for index, value in enumerate(data))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_message(message, secret):
    if secret is None:
        return message
    encrypted = base64.urlsafe_b64decode(message.encode("ascii"))
    key = _derive_key(secret)
    data = bytes(value ^ key[index % len(key)] for index, value in enumerate(encrypted))
    return data.decode("utf-8")
