from pathlib import Path
import pytest
from radar.export import export_transcript,transcript_entries
from radar.model import Cut


def test_transcript_contains_only_original_time_words_after_manual_edit(tmp_path):
    speech=[{'start':80,'end':120,'text':'fora antes dentro depois','words':[
        {'start':81,'end':82,'word':' fora'}, {'start':88,'end':89,'word':' antes'},
        {'start':91.2,'end':93.5,'word':' dentro'}, {'start':117,'end':119,'word':' depois'}]}]
    cut=Cut(1,80,120,50,'Reação','Teste','ESTE TEXTO ANTIGO NÃO DEVE SER EXPORTADO')
    cut.start,cut.end=90,100
    path=export_transcript(cut,speech,tmp_path/'fala.txt')
    text=path.read_text(encoding='utf-8')
    assert 'Início no original: 00:01:30.000' in text
    assert 'Fim no original: 00:01:40.000' in text
    assert '[00:01:31.200 --> 00:01:33.500] dentro' in text
    assert 'fora' not in text and 'antes' not in text and 'depois' not in text and 'ANTIGO' not in text
    with pytest.raises(FileExistsError):export_transcript(cut,speech,path)


def test_transcript_no_speech_creates_no_empty_file(tmp_path):
    path=tmp_path/'empty.txt'
    with pytest.raises(ValueError,match='não tem fala transcrita'):
        export_transcript(Cut(1,0,20,50,'Teste','Teste'),[],path)
    assert not path.exists()


def test_segments_without_words_never_include_outside_speech(tmp_path):
    cut=Cut(1,10,30,50,'Teste','Teste')
    segments=[{'start':8,'end':12,'text':'frase de fora'}, {'start':15,'end':20,'text':'frase interna'}]
    text=export_transcript(cut,segments,tmp_path/'fala.txt').read_text(encoding='utf-8')
    assert 'frase interna' in text and 'frase de fora' not in text
    assert 'foram omitidos' in text
    with pytest.raises(ValueError,match='faltam tempos por palavra'):
        export_transcript(cut,segments[:1],tmp_path/'unknown.txt')


def test_partially_clipped_word_has_an_explicit_note(tmp_path):
    cut=Cut(1,10,20,50,'Teste','Teste')
    speech=[{'start':9,'end':12,'text':'olá','words':[{'start':9.8,'end':11,'word':'olá'}]}]
    text=export_transcript(cut,speech,tmp_path/'partial.txt').read_text(encoding='utf-8')
    assert 'palavras parcialmente' in text
    assert '[00:00:10.000 --> 00:00:11.000] olá' in text
