import sys,os,traceback,json
from threading import RLock, Condition, Thread
from queue import Queue, Empty
import numpy as np
import scipy
import heapq
from vosk import Model, KaldiRecognizer
from .VoskUtil import get_vosk_model, get_vosk_spk_model, sound_float_to_int16

import vosk
vosk.SetLogLevel(-1)

dbg_level=1
def dbg_print(lv:int,txt:str):
    if lv<=dbg_level:
        print( txt )

ee=0.05

class VoskWord:
    """Voskで認識した単語"""
    def __init__(self, result, index:int=0, subindex:int=0 ):
        self.index: int = index
        self.subindex: int = subindex
        self.start:float = result.get('time_start',0.0)
        self.end:float = result.get('time_end',self.start)
        self.frame_start:int = result.get('frame_start',0)
        self.frame_end:int = result.get('frame_end',self.frame_start)
        self.word:str = result.get('word','')
        self.conf:float = result.get('conf',0.0)

class VoskSegment:
    def __init__(self):
        self.start: float = 0
        self.end: float = 0
        self.frame_start:int = 0
        self.frame_end:int = 0
        self.wordlist: list[VoskWord]=[]

    def get_length(self):
        return self.end-self.start

    def is_overlap(self, start, end ) -> bool:
        if (self.end+ee)<start:
            return 1
        if end<self.start:
            return -1
        return 0

    def add_word(self,word:VoskWord):
        if len(self.wordlist)==0:
            self.start = word.start
            self.end = word.end
            self.frame_start = word.frame_start
            self.frame_end = word.frame_end
        else:
            self.start = min(self.start,word.start)
            self.end = max(self.end,word.end)
            self.frame_start = min(self.frame_start,word.frame_start)
            self.frame_end = max(self.frame_end,word.frame_end)
        self.wordlist.append(word)
        self.test()

    def join(self, obj ) ->bool:
        other: VoskSegment = obj
        self.start = min( self.start, other.start )
        self.end = max( self.end, other.end )
        self.frame_start = min( self.frame_start, other.frame_start )
        self.frame_end = max( self.frame_end, other.frame_end )
        self.wordlist.extend( other.wordlist )
        self.sort()
        self.test()
        other.start=0
        other.end=0
        other.wordlist=[]
        return True

    def test(self):
        if self.start>self.end:
            raise Exception("invalid seg start end")
        if self.frame_start>self.frame_end:
            raise Exception("invalid seg start end")
        for w in self.wordlist:
            if w.start>w.end:
                raise Exception("invalid word start end")
            if self.start>w.start:
                raise Exception("invalid word start end")
            if self.end<w.end:
                raise Exception("invalid word start end")
            if w.frame_start>w.frame_end:
                raise Exception("invalid word start end")
            if self.frame_start>w.frame_start or self.frame_end<w.frame_end:
                raise Exception("invalid word start end")
            
    def sort(self):
        self.wordlist.sort( key=lambda x: x.index*100+x.subindex )

class VoskSegList:

    def __init__(self):
        self.seglist: list[VoskSegment] = []

    def reset(self):
        self.seglist = []

    def add_result(self, entry, index=0):
        for subidx,result in enumerate(entry.get('result',[])):
            if 'word' in result:
                tw = VoskWord( result, index, subidx )
                self.add_word( tw )

    def add_word(self,word:VoskWord):
        p=len(self.seglist)
        while p>0:
            seg:VoskSegment = self.seglist[p-1]
            d = seg.is_overlap( word.start, word.end )
            if d>0:
                break
            elif d==0:
                seg.add_word( word )
                while p<len(self.seglist) and (seg.end+ee)>self.seglist[p].start:
                    seg.join( self.seglist[p] )
                    self.seglist.pop(p)
                while 1<p and (self.seglist[p-2].end+ee)>seg.start:
                    self.seglist[p-2].join(seg)
                    self.seglist.pop(p-1)
                    p-=1
                    seg = self.seglist[p-1]
                return
            p-=1
        seg:VoskSegment = VoskSegment()
        seg.add_word(word)
        self.seglist.insert(p,seg)

    def sort(self):
        self.seglist.sort( key=lambda x: x.start )
        for seg in self.seglist:
            seg.sort()

    def self_check( data:list[VoskSegment] ):
        t=-1
        for seg in data:
            if t>=seg.start:
                raise Exception("not sorted")
            if seg.start>seg.end:
                raise Exception("not sorted")
            t=seg.end

    def get_segment(self,atime, gap=0.6) ->list[VoskSegment]:
        btime = atime - gap
        # timeを超えない最終位置
        idx = len(self.seglist)-1
        while idx>=0 and btime<=self.seglist[idx].end:
            idx-=1
        if idx<0:
            return []
        if self.seglist[idx].get_length()<gap:
            before = self.seglist[idx].start - self.seglist[idx-1].end if idx>0 else gap*4
            after = btime - self.seglist[idx].end
            if before>after:
                return []
        result:list[VoskSegment]=[ x for x in self.seglist[:idx+1] ]
        after = [ x for x in self.seglist[idx+1:]]
        self.seglist = after
        ll = len(result)
        # 短いセグメントを前後に結合する
        p=0
        while ll>1 and p<ll-1:
            u=result[p].get_length()<gap
            if u:
                while ll>1 and u:
                    before = (result[p].start-result[p-1].end) if p>0 else 99999
                    after = (result[p+1].start-result[p].end) if (p+1)<ll else 99999
                    if before<after:
                        u = result[p-1].get_length()<gap
                        p=p-1
                    else:
                        u = result[p+1].get_length()<gap
                    result[p].join( result.pop(p+1) )
                    ll = len(result)
            else:
                p+=1
        # 短いgapで結合する
        p=0
        while ll>1 and p<ll-1:
            a:VoskSegment=result[p]
            b:VoskSegment=result[p+1]
            if abs(a.end-b.start)<gap:
                a.join(b)
                result.pop(p+1)
                ll = len(result)
            else:
                p+=1
        return result

class VoiceSplitter:

    def __init__(self,samplerate:int, *, callback=None, json_log:str=None):
        self.samplerate:int = samplerate
        self._callback = callback
        self._last_call = 0
        # デバッグ用ログ出力
        self.debug_log:int = 0
        self._logfile_json = json_log
        self._hist_json = []
        # 音声処理の処理単位
        self.seg_time:float = 0.2
        self.seg_frames:int = int( self.samplerate * self.seg_time)
        # 音声バッファ
        self.time_start:float = 0
        self.buffer_lock:RLock = RLock()
        self.buffer_offset:int = 0
        self.buffer = np.array([], dtype=np.float32)
        self.detect_idx = 0
        # VOSKモデル
        self.model_lang = None
        self.model_spk = None
        self.vosk_samplerate:int = self.samplerate

        self.thread_lock:RLock = RLock()
        # VSOK処理キューx2
        self.pass1_q:Queue = Queue()
        self.pass1_threads:list[Thread] = [None,None]
        # セグメント結合処理
        self.pass2_lock:Condition = Condition()
        self.pass2_heap = []
        self.pass2_next_idx = 0
        self.pass2_thread:Thread = None
        self.pass2_data:VoskSegList = None
        self._pause:bool = False

    def set_pause(self,b:bool) ->bool:
        with self.pass2_lock:
            if self.pass2_data is not None:
                self.pass2_data.reset()
            self._pause = b
            print( f"[VoiceSplitter] success to set pause {b}")
            return True

    def add_to_buffer(self, array):
        if self._pause:
            return
        if not isinstance(array, np.ndarray) or array.dtype != np.float32:
            raise TypeError("引数はNumPyのfloat32配列でなければなりません")
        with self.buffer_lock:
            self.buffer = np.concatenate((self.buffer, array))
            ll:int = len(self.buffer)
            while (ll-self.detect_idx)>(self.seg_frames*3):
                self.pass1_q.put( self.detect_idx + self.buffer_offset )
                self.detect_idx += self.seg_frames * 2
        with self.thread_lock:
            for i in range(0,len(self.pass1_threads)):
                if self.pass1_threads[i] is None:
                    t:Thread = Thread( name=f"vosk{i}", target=self._th_vosk, args=(i,) )
                    self.pass1_threads[i] = t
                    t.start()

    def create_vosk(self) ->KaldiRecognizer :
        if self.model_lang is None:
            self.model_lang = get_vosk_model(lang="ja")
        if self.model_spk is None:
            self.model_spk = get_vosk_spk_model(self.model_lang)

        vosk: KaldiRecognizer = KaldiRecognizer(self.model_lang, int(self.vosk_samplerate) )
        if self.model_spk is not None:
            vosk.SetSpkModel( self.model_spk )
        vosk.SetWords(True)
        vosk.SetPartialWords(True)
        return vosk

    def _vosk_words_bugfix(self, obj, offset_frame=0, bugfix_frames=0 ) :
        """voskのバグを補正する
            start_frame: AcceptWaveformに渡したデータがbufferのどの位置か？
            bugfix_frames: voskがresetしてもword位置をリセットしてくれないので累積値を引く必要がある
        """
        if obj is None:
            return
        result = obj.get('result', obj.get('partial_result') )
        if result is not None:
            bugfix_time = bugfix_frames / self.samplerate
            for word_info in result:
                for pname in ['start','end']:
                    bug_value = word_info.get(pname)
                    if bug_value is not None:
                        fixed_time = round( bug_value - bugfix_time, 6 )
                        frame = offset_frame + int( self.samplerate * fixed_time )
                        word_info[pname] = fixed_time
                        word_info[f"frame_{pname}"] = frame
                        word_info[f"time_{pname}"] = round( frame / self.samplerate, 6 )

    def _th_vosk(self,no):
        try:
            dbg_print(1,f"[vosk{no}]start")
            vosk = self.create_vosk()
            bugfix_frames = 0
            while True:
                index_start = self.pass1_q.get( block=True, timeout=1.0 )
                with self.buffer_lock:
                    s = index_start - self.buffer_offset
                    e = s + self.seg_frames*3
                    buf0 = self.buffer[s:e]
                if self.samplerate > self.vosk_samplerate:
                    # ダウンサンプリング後のデータの長さを計算
                    new_length = int(len(buf0) * self.vosk_samplerate / self.samplerate)
                    # リサンプリング
                    buf = scipy.signal.resample(buf0, new_length)
                elif self.samplerate < self.vosk_samplerate:
                    buf = buf0
                else:
                    buf = buf0
                # wave_mono_float = buf * 32767.0
                # wave_mono_int16 = wave_mono_float.astype(np.int16)
                wave_mono_int16 = sound_float_to_int16( buf, scale=0.8, lowcut=0.0 )
                b = wave_mono_int16.tobytes()
                vosk.AcceptWaveform( b )
                res = json.loads(vosk.FinalResult())
                self._vosk_words_bugfix(res,index_start,bugfix_frames)
                res['index'] = index_start
                vosk.Reset()
                bugfix_frames += len(wave_mono_int16)
                self._pass2_put( res )
                with self.thread_lock:
                    if self.pass2_thread is None:
                        t = Thread( name='pass2', target=self._th_pass2 )
                        self.pass2_thread = t
                        t.start()
        except Empty:
            pass
        except:
            traceback.print_exc()
        finally:
            with self.thread_lock:
                self.pass1_threads[no] = None
            dbg_print(1,f"[vosk{no}]exit")

    def _append_json_log(self,res):
        self._hist_json.append(res)
        if len(self._hist_json)>100:
            self._flush_json_log()

    def _flush_json_log(self):
        try:
            if len(self._hist_json)>0 and self._logfile_json is not None:
                with open(self._logfile_json,'a') as out:
                    for j in self._hist_json:
                        line=json.dumps( j, indent=4, ensure_ascii=False )
                        out.write( line );out.write('\n')
        except:
            traceback.print_exc()
        self._hist_json=[]

    def _pass2_put(self, data ):
        index=data.get('index')
        if index >=0:
            idx = index // (self.seg_frames*2)
            with self.pass2_lock:
                heapq.heappush(self.pass2_heap, (idx,data) )
                self.pass2_lock.notify()
    
    def _exists_pass1(self):
        if isinstance(self.pass1_threads,list):
            for x in self.pass1_threads:
                if isinstance(x,Thread) and x.is_alive():
                    return True
        return False
        
    def _pass2_get(self):
        with self.pass2_lock:
            while len(self.pass2_heap)==0 or self.pass2_heap[0][0] != self.pass2_next_idx:
                self.pass2_lock.wait( timeout=1.0 )
                if not self._exists_pass1():
                    raise Empty("end?")
            idx,data = heapq.heappop( self.pass2_heap )
            self.pass2_next_idx =idx+1
            return data

    def _th_pass2(self):
        try:
            margin_frames = int( self.samplerate * 0.4 )
            dbg_print(1,f"[voskX]start")
            vosk_seg_list:VoskSegList = self.pass2_data
            if vosk_seg_list is None:
                vosk_seg_list = VoskSegList()
                self.pass2_data = vosk_seg_list
            while True:
                try:
                    res = self._pass2_get()
                except Empty:
                    with self.thread_lock:
                        if self._exists_pass1():
                            continue
                        else:
                            break
                index_start = res.get('index',0)
                idx = int( index_start / (self.seg_frames*2) )
                self._append_json_log(res)
                time_start = round( index_start / self.samplerate, 6 )
                dbg_print(3, f"[voskX]get idx:{idx} frame:{index_start} time {time_start}")
                seglist:list[VoskSegment] = vosk_seg_list.get_segment( time_start )
                for seg in seglist:
                    dbg_print(2,f"voice seg {seg.start} {seg.end}")
                    seg.sort()
                    seg.test()
                    for vw in seg.wordlist:
                        dbg_print(2, f"    {vw.start:.3f} - {vw.end:.3f}  {vw.frame_start}-{vw.frame_end} {vw.word}")
                    with self.buffer_lock:
                        a = (seg.frame_start-margin_frames) - self.buffer_offset
                        b = (seg.frame_end+margin_frames) - self.buffer_offset
                        set_buf = self.buffer[a:b]
                    if not self._pause and self._callback is not None:
                        self._callback( seg.frame_start, seg.frame_end, set_buf, self.samplerate, )
                    self._last_call = seg.frame_end
                vosk_seg_list.add_result( res, index=idx )
                if self._last_call>1:
                    if len(vosk_seg_list.seglist)==0:
                        silent_time = (index_start-self._last_call)/self.samplerate
                        if silent_time>1.0:
                            if not self._pause and self._callback is not None:
                                self._callback( self._last_call, index_start, [], self.samplerate, )
                            self._last_call = 0
                elif self._last_call==0:
                    if len(vosk_seg_list.seglist)>0:
                        if not self._pause and self._callback is not None:
                            self._callback( index_start, index_start, [1.0], self.samplerate, )
                        self._last_call = 1

        except Empty:
            dbg_print(1,f"[voskX]empty")
            pass
        except:
            traceback.print_exc()
        finally:
            with self.thread_lock:
                self.pass2_thread = None
            self._flush_json_log()
            dbg_print(1,f"[voskX]exit")

    plist=['start','end']
