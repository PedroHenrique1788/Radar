import io
import json
import os
from pathlib import Path
import threading
import urllib.error

import pytest

from radar.credentials import CredentialError,KeyStore,validate_key
from radar.gemini import GeminiClient,GeminiError,cut_record,record_signature
from radar.media import Cancelled
from radar.model import Cut,Media
from radar.settings import read_settings,save_settings

KEY='fake-test-credential-not-valid-for-any-service'


def result_data(score=72,ident=1,search=False):
    content={'cortes':[{'id':ident,'nota_editorial':score,'titulo':'Um bom gancho','justificativa':'Fala com contexto.',
                        'sugestao_edicao':'Revise o ritmo.','limitacoes':'Não recebi o vídeo.'}]}
    candidate={'finishReason':'STOP','content':{'parts':[{'text':json.dumps(content)}]}}
    if search:
        candidate['groundingMetadata']={'groundingChunks':[{'web':{'title':'Fonte','uri':'https://example.org/referencia'}},
                                                         {'web':{'title':'Inválida','uri':'javascript:alert(1)'}}]}
    return {'candidates':[candidate],'usageMetadata':{'promptTokenCount':120,'candidatesTokenCount':80,'totalTokenCount':200}}


class Transport:
    def __init__(self,*responses):self.responses=list(responses);self.requests=[]
    def open(self,request,timeout):
        self.requests.append(request)
        response=self.responses.pop(0)
        if isinstance(response,Exception):raise response
        return io.BytesIO(json.dumps(response).encode())


def inputs():
    media=Media('/private/user/source.mp4',100,1920,1080,30,'h264',0,[],0)
    cut=Cut(1,10,30,45,'Título local','Heurística','Olha como consegui concluir a missão!')
    return media,cut


def test_models_are_discovered_and_key_is_only_a_header():
    t=Transport({'models':[{'name':'models/gemini-fast-flash','supportedGenerationMethods':['generateContent']},
                            {'name':'models/gemini-fast-image','supportedGenerationMethods':['generateContent']}],
                 'nextPageToken':'token / next'},
                {'models':[{'name':'models/gemini-fast-flash-lite','supportedGenerationMethods':['generateContent']}]})
    models=GeminiClient(KEY,t).list_models()
    assert models==['gemini-fast-flash-lite','gemini-fast-flash']
    assert len(t.requests)==2 and 'pageToken=token%20%2F%20next' in t.requests[1].full_url
    for r in t.requests:
        assert KEY not in r.full_url and r.data is None
        assert dict((k.lower(),v) for k,v in r.header_items())['x-goog-api-key']==KEY


def test_review_only_sends_cut_text_and_preserves_local_times_and_scores():
    media,cut=inputs()
    t=Transport(result_data())
    original=(cut.start,cut.end,cut.score,cut.title)
    data=GeminiClient(KEY,t).review(media,[cut],model='gemini-fast-flash')
    body=json.loads(t.requests[0].data)
    encoded=t.requests[0].data.decode()
    assert '/private/' not in encoded and KEY not in encoded
    assert (cut.start,cut.end,cut.score,cut.title)==original
    assert data['reviews'][0]['nota_editorial']==72
    assert data['input_signatures']['1']==record_signature(cut_record(cut))
    assert data['inputs'][0]['inicio']=='00:00:10.000'
    assert 'tools' not in body and body['generationConfig']['responseMimeType']=='application/json'
    assert not data['search_confirmed'] and data['usage']['totalTokenCount']==200


def test_search_is_explicit_and_only_google_grounding_counts_as_sources():
    media,cut=inputs()
    t=Transport(result_data(search=True),result_data())
    data=GeminiClient(KEY,t).review(media,[cut],model='gemini-fast-flash',search=True)
    body=json.loads(t.requests[0].data)
    assert body['tools']==[{'googleSearch':{}}]
    assert 'responseMimeType' not in body['generationConfig']
    assert data['search_requested'] and data['search_confirmed'] and len(data['sources'])==1
    no_sources=GeminiClient(KEY,t).review(media,[cut],model='gemini-fast-flash',search=True)
    assert no_sources['search_requested'] and not no_sources['search_confirmed']


@pytest.mark.parametrize('status',[400,401,403,404,429,503])
def test_http_errors_never_expose_key_or_retry_with_another_model(status):
    media,cut=inputs()
    error=urllib.error.HTTPError('https://service.invalid/',status,KEY,{},io.BytesIO(KEY.encode()))
    t=Transport(error)
    with pytest.raises(GeminiError) as failure:
        GeminiClient(KEY,t).review(media,[cut],model='gemini-fast-flash')
    assert KEY not in str(failure.value)
    import traceback
    assert KEY not in ''.join(traceback.format_exception(failure.value))
    assert len(t.requests)==1
    assert failure.value.status==status


def test_rate_limit_retains_safe_retry_after_without_sending_another_request():
    media,cut=inputs()
    error=urllib.error.HTTPError('https://service.invalid/',429,KEY,{'Retry-After':'120'},io.BytesIO(KEY.encode()))
    transport=Transport(error)
    with pytest.raises(GeminiError) as failure:
        GeminiClient(KEY,transport).review(media,[cut],model='gemini-fast-flash')
    assert failure.value.status==429 and failure.value.retry_after==120
    assert KEY not in str(failure.value) and len(transport.requests)==1


@pytest.mark.parametrize('header,expected',[(None,0),('invalid',0),('-20',0),('1.2',2),('nan',0),('inf',0),('90000',86400)])
def test_retry_after_is_bounded_and_untrusted_text_is_discarded(header,expected):
    from radar.gemini import _retry_after
    assert _retry_after(header)==expected


def test_http_date_retry_after_is_supported():
    from datetime import datetime,timedelta,timezone
    from email.utils import format_datetime
    from radar.gemini import _retry_after
    header=format_datetime(datetime.now(timezone.utc)+timedelta(seconds=60),usegmt=True)
    assert 59<=_retry_after(header)<=60


@pytest.mark.parametrize('payload',[result_data(score=101),result_data(score=float('nan')),result_data(ident=9),
                                     {'candidates':[{'finishReason':'MAX_TOKENS'}]}, {'candidates':[]}])
def test_invalid_or_truncated_reviews_are_not_accepted(payload):
    media,cut=inputs()
    with pytest.raises(GeminiError):GeminiClient(KEY,Transport(payload)).review(media,[cut],model='gemini-fast-flash')


def test_no_transcript_and_cancelled_calls_do_not_contact_api():
    media,cut=inputs()
    t=Transport()
    with pytest.raises(GeminiError,match='Não há fala'):
        GeminiClient(KEY,t).review(media,[cut],speech=[],model='gemini-fast-flash')
    cancel=threading.Event();cancel.set()
    with pytest.raises(Cancelled):GeminiClient(KEY,t).list_models(cancel)
    assert not t.requests


@pytest.mark.parametrize('key',['','a b','key\nheader','non-ascii-🔑','a\x7fb'])
def test_credential_header_validation(key):
    with pytest.raises(CredentialError):validate_key(key)


def test_common_preferences_refuse_secret_fields(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_settings({'channel_name':'CEFASGAMER','accent':'#278cff'})
    with pytest.raises(ValueError):save_settings({'gemini_api_key':KEY})
    assert KEY not in json.dumps(read_settings())


def test_key_is_either_windows_protected_or_explicitly_not_persisted(tmp_path):
    store=KeyStore(tmp_path/'key.dpapi')
    if os.name!='nt':
        with pytest.raises(CredentialError):store.save(KEY)
        assert not store.exists()
        return
    store.save(KEY)
    assert store.exists() and KEY.encode() not in store.path.read_bytes()
    assert store.load()==KEY
    store.delete()
    assert not store.exists() and store.load()==''


def test_redirect_handler_refuses_to_forward_credentials():
    from radar.gemini import _NoRedirect
    assert _NoRedirect().redirect_request(None,None,302,'redirect',{},'https://other.invalid/') is None
