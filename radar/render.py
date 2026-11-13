"""CPU export presets and subtitle text; independent of the analysis profile."""
from dataclasses import asdict,dataclass
import math
import re
import textwrap


PRESETS={'leve':(24,'veryfast'),'equilibrado':(20,'fast'),'qualidade':(18,'medium')}
MODES={'original':'Original','landscape':'Horizontal 16:9','vertical_crop':'Vertical 9:16 — recorte',
       'vertical_blur':'Vertical 9:16 — fundo desfocado'}


@dataclass
class RenderOptions:
    mode: str='original'
    resolution: int=720
    preset: str='equilibrado'
    crop_x: float=.5
    crop_y: float=.5
    burn_subtitles: bool=False

    def validate(self):
        if self.mode not in MODES:raise ValueError('Formato de exportação inválido.')
        if isinstance(self.resolution,bool) or self.resolution not in (720,1080):raise ValueError('Escolha resolução 720 ou 1080.')
        if self.preset not in PRESETS:raise ValueError('Preset de qualidade inválido.')
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=1 for v in (self.crop_x,self.crop_y)):
            raise ValueError('Posição do recorte deve ficar entre 0 e 1.')
        if not isinstance(self.burn_subtitles,bool):raise ValueError('Escolha se deseja gravar legendas no vídeo.')
        return self

    def record(self):self.validate();return asdict(self)

    @classmethod
    def from_record(cls,value=None):
        if value is None:return cls()
        if isinstance(value,cls):return cls(**value.record()).validate()
        if not isinstance(value,dict):raise ValueError('Configuração de exportação inválida.')
        try:return cls(**value).validate()
        except TypeError:raise ValueError('Configuração de exportação incompatível.') from None

    def dimensions(self,media):
        if self.mode=='original':return media.width+(media.width%2),media.height+(media.height%2)
        short=self.resolution;long=short*16//9
        return (short,long) if self.mode.startswith('vertical') else (long,short)


def for_cut(options,cut):
    result=RenderOptions.from_record(options)
    if cut.framing:
        if not isinstance(cut.framing,dict) or set(cut.framing)!={'crop_x','crop_y'}:raise ValueError('Enquadramento individual inválido.')
        result.crop_x=cut.framing['crop_x'];result.crop_y=cut.framing['crop_y']
    return result.validate()


def video_filters(source,media,options,output='v',subtitles=False):
    """source already starts at PTS zero. Coordinates are explicit, no tracking."""
    opts=RenderOptions.from_record(options);w,h=opts.dimensions(media)
    if opts.mode=='original':chain=f'{source}pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1'
    elif opts.mode=='vertical_crop':
        chain=f'{source}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}:x=(iw-ow)*{opts.crop_x}:y=(ih-oh)*{opts.crop_y},setsar=1'
    elif opts.mode=='vertical_blur':
        return (f'{source}split=2[bgsource][fgsource];'
                f'[bgsource]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=12:2,setsar=1[background];'
                f'[fgsource]scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1[foreground];'
                f'[background][foreground]overlay=(W-w)/2:(H-h)/2'+(',subtitles=filename=captions.ass' if subtitles else '')+f'[{output}]')
    else:chain=f'{source}scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1'
    return chain+(',subtitles=filename=captions.ass' if subtitles else '')+f'[{output}]'


def write_ass(path,entries,cut,width,height):
    """Fixed style and literal text: transcript cannot inject ASS overrides."""
    font=max(16,round(min(width,height)*.052));margin=max(12,round(height*.065))
    lines=['[Script Info]','ScriptType: v4.00+',f'PlayResX: {width}',f'PlayResY: {height}',
           'WrapStyle: 0','ScaledBorderAndShadow: yes','','[V4+ Styles]',
           'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
           f'Style: Default,Arial,{font},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,24,24,{margin},1',
           '','[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    def clock(t):
        cs=max(0,round(t*100));hours,rem=divmod(cs,360000);minutes,rem=divmod(rem,6000);seconds,cs=divmod(rem,100)
        return f'{hours}:{minutes:02}:{seconds:02}.{cs:02}'
    for entry in entries:
        text=re.sub(r'[\x00-\x1f]+',' ',entry['text']).replace('\\','/').replace('{','(').replace('}',')')
        text=' '.join(text.split())
        wrapped='\\N'.join(textwrap.wrap(text,width=32 if height>width else 58,break_long_words=True))
        a=max(0,entry['start']-cut.start);b=min(cut.duration,entry['end']-cut.start)
        if wrapped and b>a:lines.append(f'Dialogue: 0,{clock(a)},{clock(b)},Default,,0,0,0,,{wrapped}')
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return path
