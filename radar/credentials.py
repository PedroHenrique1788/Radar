"""Gemini credential storage: Windows DPAPI, bound to the current OS user."""
import ctypes
import os
from pathlib import Path
import tempfile


class CredentialError(RuntimeError):
    pass


def _protect(data, decrypt=False):
    if os.name != 'nt':
        raise CredentialError('Salvar a chave protegida está disponível no Windows. Aqui, use a chave somente nesta sessão.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    source=Blob(len(data),buffer)
    output=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    function=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    kernel.LocalFree.restype=ctypes.c_void_p
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):
        raise CredentialError('O Windows não conseguiu proteger/abrir a chave deste usuário. Configure a chave novamente.')
    try:
        return ctypes.string_at(output.data,output.size)
    finally:
        kernel.LocalFree(output.data)


class KeyStore:
    def __init__(self,path=None):
        self.path=Path(path or 'config/gemini_key.dpapi')

    def exists(self):
        return self.path.is_file()

    def save(self,key):
        key=validate_key(key)
        protected=_protect(key.encode('utf-8'))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='key-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'wb') as out:
                out.write(protected)
            os.chmod(name,0o600)
            os.replace(name,self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def load(self):
        if not self.exists():
            return ''
        try:
            return validate_key(_protect(self.path.read_bytes(),decrypt=True).decode('utf-8'))
        except (OSError,UnicodeError,ValueError):
            raise CredentialError('Não foi possível ler a chave salva. Remova-a e configure uma nova chave.') from None

    def delete(self):
        self.path.unlink(missing_ok=True)


def validate_key(key):
    key=str(key).strip()
    if not key or len(key)>2048 or not key.isascii() or any(c.isspace() or ord(c)<32 or ord(c)==127 for c in key):
        raise CredentialError('Cole uma chave válida do Google AI Studio, sem espaços ou quebras de linha.')
    return key
