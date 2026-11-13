"""Small Tk timeline: real peaks, zoom/pan, cursor, cut selection and IN/OUT."""
import math
import tkinter as tk
from tkinter import ttk
from .model import timestamp


class Timeline(ttk.Frame):
    def __init__(self,parent,*,on_seek=lambda t:None,on_select=lambda i:None,on_range=lambda a,b:None):
        super().__init__(parent)
        self.duration=0.;self.view=(0.,1.);self.cursor=0.;self.range=(0.,0.)
        self.cuts=[];self.waveform=None;self.selected_id=None;self.drag=None
        self.on_seek=on_seek;self.on_select=on_select;self.on_range=on_range
        self.canvas=tk.Canvas(self,height=125,bg='#081322',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.scroll=ttk.Scrollbar(self,orient='horizontal',command=self.pan);self.scroll.pack(fill='x')
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<Button-1>',self.press);self.canvas.bind('<B1-Motion>',self.motion);self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<Control-MouseWheel>',lambda e:self.zoom(.5 if e.delta>0 else 2.))

    def set_media(self,duration):
        self.duration=float(duration);self.view=(0.,max(.001,self.duration));self.cursor=0.
        self.range=(0.,min(30.,self.duration));self.waveform=None;self.cuts=[];self.selected_id=None;self.draw()

    def update_cuts(self,cuts):self.cuts=list(cuts);self.draw()

    def select_cut(self,cut):
        self.selected_id=cut.id;self.range=(cut.start,cut.end);self.draw()

    def set_cursor(self,value,notify=True):
        self.cursor=max(0.,min(self.duration,float(value)));self.draw()
        if notify:self.on_seek(self.cursor)

    def set_range(self,a,b,notify=True):
        self.range=(max(0.,min(a,b)),min(self.duration,max(a,b)));self.draw()
        if notify:self.on_range(*self.range)

    def reset_view(self):self.view=(0.,max(.001,self.duration));self.draw()

    def zoom(self,factor):
        if not self.duration:return
        a,b=self.view;span=min(self.duration,max(min(1.,self.duration),(b-a)*factor))
        anchor=self.cursor if a<=self.cursor<=b else (a+b)/2
        ratio=(anchor-a)/(b-a);start=max(0.,min(self.duration-span,anchor-span*ratio))
        self.view=(start,start+span);self.draw()

    def pan(self,*args):
        if not self.duration:return
        a,b=self.view;span=b-a
        start=float(args[1])*self.duration if args[0]=='moveto' else a+int(args[1])*span*(.8 if args[2]=='pages' else .1)
        start=max(0.,min(self.duration-span,start));self.view=(start,start+span);self.draw()

    def time_at(self,x):
        width=max(1,self.canvas.winfo_width()-24);a,b=self.view
        return max(0.,min(self.duration,a+(x-12)/width*(b-a)))

    def x_at(self,t):
        a,b=self.view
        return 12+(t-a)/max(.001,b-a)*max(1,self.canvas.winfo_width()-24)

    def press(self,event):
        if not self.duration:return
        t=self.time_at(event.x);a,b=self.range
        if event.state&1:self.drag=('range',t);self.set_range(t,t)
        elif abs(event.x-self.x_at(a))<8:self.drag=('start',b)
        elif abs(event.x-self.x_at(b))<8:self.drag=('end',a)
        else:
            overlapping=[self.canvas.gettags(i) for i in self.canvas.find_overlapping(event.x,event.y,event.x,event.y)]
            ids=[tag.removeprefix('cut-') for tags in overlapping for tag in tags if tag.startswith('cut-')]
            if ids:self.on_select(int(ids[-1]))
            self.drag=('cursor',t);self.set_cursor(t)

    def motion(self,event):
        if not self.drag:return
        t=self.time_at(event.x);kind,anchor=self.drag
        if kind=='cursor':self.set_cursor(t)
        elif kind in ('range','end'):self.set_range(anchor,t)
        else:self.set_range(t,anchor)

    def release(self,event):
        if self.drag:self.motion(event)
        self.drag=None

    def draw(self):
        c=self.canvas;c.delete('all');w=max(24,c.winfo_width());h=max(80,c.winfo_height())
        a,b=self.view;span=max(.001,b-a)
        for i in range(6):
            t=a+span*i/5;x=self.x_at(t)
            c.create_line(x,22,x,h,fill='#162b42')
            c.create_text(x,11,text=timestamp(t).split('.')[0],fill='#94abc8',font=('TkDefaultFont',8),anchor='w' if i==0 else 'e' if i==5 else 'center')
        center=48
        c.create_line(12,center,w-12,center,fill='#29425e')
        if self.waveform:
            peaks=self.waveform['peaks'];wa,wb=self.waveform['start'],self.waveform['end'];step=(wb-wa)/max(1,len(peaks))
            lo=max(0,math.floor((a-wa)/step));hi=min(len(peaks),math.ceil((b-wa)/step))
            stride=max(1,math.ceil((hi-lo)/max(1,w//2)))
            for i in range(lo,hi,stride):
                value=max(peaks[i:min(hi,i+stride)],default=0);x=self.x_at(wa+(i+stride/2)*step)
                c.create_line(x,center-value*19,x,center+value*19,fill='#58c9db')
        else:c.create_text(w/2,48,text='Carregue as ondas do áudio original para esta janela',fill='#7891b2',font=('TkDefaultFont',9))
        for i,cut in enumerate(self.cuts):
            if cut.end<a or cut.start>b:continue
            x1=max(12,self.x_at(cut.start));x2=min(w-12,self.x_at(cut.end));y=73+(i%2)*19
            color='#94702b' if cut.favorite else '#263c55' if cut.review_state=='rejected' else '#16614f' if cut.review_state=='approved' else '#184c7a'
            c.create_rectangle(x1,y,x2,y+16,fill=color,outline='#80bbff' if cut.id==self.selected_id else color,tags=(f'cut-{cut.id}',))
            if x2-x1>30:c.create_text(x1+4,y+8,text=('★ ' if cut.favorite else '')+str(cut.id),anchor='w',fill='white',font=('TkDefaultFont',8),tags=(f'cut-{cut.id}',))
        left,right=self.range
        for t,label,color in ((left,'IN','#5aafff'),(right,'OUT','#f3c476')):
            if a<=t<=b:
                x=self.x_at(t);c.create_line(x,22,x,h,fill=color,width=2)
                c.create_text(x+3,h-5,text=label,anchor='sw',fill=color,font=('TkDefaultFont',8))
        if a<=self.cursor<=b:
            x=self.x_at(self.cursor);c.create_line(x,20,x,h,fill='#ffffff')
        self.scroll.set(a/max(.001,self.duration),min(1.,b/max(.001,self.duration)))
