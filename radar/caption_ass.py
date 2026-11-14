"""Four libass styles, using existing word times rather than guessed durations."""
from decimal import Decimal,ROUND_HALF_UP
import re
import textwrap

from .captions import CaptionStyle


def clock(seconds):
    centis=max(0,int((Decimal(str(seconds))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP)))
    h,rest=divmod(centis,360000);m,rest=divmod(rest,6000);s,cs=divmod(rest,100)
    return f'{h}:{m:02}:{s:02}.{cs:02}'


def color(value):return '&H'+value[5:7]+value[3:5]+value[1:3]+'&'


def literal(text):
    # ASS has no reliable plain-text quoting for arbitrary override blocks.
    # Keep the stored/SRT text intact; use literal-looking glyphs in ASS.
    return re.sub(r'[\x00-\x1f]+',' ',text).replace('\\','＼').replace('{','｛').replace('}','｝')


def wrapped_words(words,limit):
    result=[];used=0
    for word in words:
        text=literal(word['word'].strip())
        punctuation=bool(re.fullmatch(r'[,.;:!?]+',text))
        prefix='' if not result or punctuation else '\\N' if used+len(text)+1>limit else ' '
        if prefix=='\\N':used=0
        pieces=textwrap.wrap(text,width=limit,break_long_words=True,break_on_hyphens=False) or ['']
        result.append(prefix+'\\N'.join(pieces));used=len(pieces[-1]) if len(pieces)>1 else used+len(text)+(prefix==' ')
    return result


def pop_tags(age):
    if age>=220:return ''
    if age<120:
        scale=92+16*age/120
        return f'\\fscx{scale:.2f}\\fscy{scale:.2f}\\t(0,{round(120-age)},\\fscx108\\fscy108)\\t({round(120-age)},{round(220-age)},\\fscx100\\fscy100)'
    scale=108-8*(age-120)/100
    return f'\\fscx{scale:.2f}\\fscy{scale:.2f}\\t(0,{round(220-age)},\\fscx100\\fscy100)'


def write_ass(path,entries,cut,width,height):
    if not 16<=width<=16384 or not 16<=height<=16384:raise ValueError('Resolução de legenda inválida.')
    lines=['[Script Info]','ScriptType: v4.00+',f'PlayResX: {width}',f'PlayResY: {height}',
           'WrapStyle: 2','ScaledBorderAndShadow: yes','','[V4+ Styles]',
           'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding']
    prepared=[]
    for index,entry in enumerate(entries):
        style=CaptionStyle.from_record(entry.get('style'));ratio=min(width,height)/720
        size=max(8.,style.size*ratio);name=f'Cue{index}'
        # Style colors have an alpha byte; inline tags below use the BGR form.
        ass_color=lambda value:'&H00'+value[5:7]+value[3:5]+value[1:3]
        lines.append(f'Style: {name},{style.font},{size:.2f},{ass_color(style.color)},{ass_color(style.color)},{ass_color(style.outline_color)},{ass_color(style.shadow_color)},'
                     f'{-1 if style.bold else 0},0,0,0,100,100,0,0,1,{style.outline*ratio:.2f},{style.shadow*ratio:.2f},5,0,0,0,1')
        prepared.append((entry,style,name,max(4,min(100,int(width*.9/(size*.58))))))
    lines+=['','[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    def emit(a,b,name,tags,text):
        a=max(0.,a-cut.start);b=min(cut.duration,b-cut.start)
        if b>a and clock(b)!=clock(a):lines.append(f'Dialogue: 0,{clock(a)},{clock(b)},{name},,0,0,0,,{{{tags}}}{text}')
    for entry,style,name,limit in prepared:
        a,b=max(cut.start,entry['start']),min(cut.end,entry['end'])
        if b<=a:continue
        tags=f'\\an5\\pos({style.x*width:.2f},{style.y*height:.2f})'
        words=entry.get('words') or []
        if style.effect not in ('highlight','karaoke') or not words:
            text='\\N'.join(textwrap.wrap(literal(entry['text']),width=limit,break_long_words=True,break_on_hyphens=False))
            animation=pop_tags(max(0.,(a-entry.get('cue_start',entry['start']))*1000)) if style.effect=='pop' else ''
            emit(a,b,name,tags+animation,text);continue
        parts=wrapped_words(words,limit)
        boundaries=sorted({a,b,*[max(a,min(b,w[k])) for w in words for k in ('start','end')]})
        for left,right in zip(boundaries,boundaries[1:]):
            if right<=left:continue
            active=next((i for i,w in enumerate(words) if w['start']<=left+1e-7<w['end']),None)
            text=[]
            for i,(word,part) in enumerate(zip(words,parts)):
                base=color(style.color);accent=color(style.highlight)
                if style.effect=='highlight':text.append('{\\1c'+(accent if i==active else base)+'}'+part)
                elif i==active:
                    duration=max(1,round((right-left)*100))
                    text.append('{\\1c'+accent+'\\2c'+base+f'\\kf{duration}'+'}'+part+'{\\k0}')
                else:
                    tone=accent if word['end']<=left+1e-7 else base
                    text.append('{\\1c'+tone+'\\2c'+tone+'\\k0}'+part)
            emit(left,right,name,tags,''.join(text))
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return path
