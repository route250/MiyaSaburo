import sys,os,time,traceback,threading,json
from queue import Queue, Empty
from threading import RLock, Thread
import numpy as np
import scipy
import wave
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from sklearn.decomposition import PCA

from vosk import Model, KaldiRecognizer
from DxBotUtils import RecognizerEngine
import sounddevice as sd


# 日本語フォントのパス
#jp_font_path = 'NotoSansJP-Regular.ttf'

# 日本語フォントを設定
#jp_font = FontProperties(fname=jp_font_path)
fontname='Noto Serif CJK JP'


class Recorder:

    def __init__(self):
        self.model_lang=None
        self.model_spk=None

    def play_reset(self):
        pass
    def get_min_max(self):
        min = np.min( np.abs(self.wave_buf) )
        max = np.max( np.abs(self.wave_buf) )
        return min,max

    def load_recording(self,filename):
        if filename:
            with wave.open(filename, 'rb') as wf:
                self.play_reset()
                self.samplerate = int(wf.getframerate())
                self.channels = int(wf.getnchannels())
                frames = wf.readframes(wf.getnframes())
                self.wave_buf = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
                self.wave_buf = self.wave_buf.reshape(-1, self.channels)
                self.data_gain = 1.0
                min,max = self.get_min_max()
                print(f"loaded min:{min} max:{max}")

    plist=['start','end']
    def vosk_words_bugfix(self, obj, frame_offset=0 ) :
        if obj is None:
            return
        result = obj.get('result', obj.get('partial_result') )
        if result is not None:
            time_offset = round( frame_offset / self.samplerate, 6 )
            for word_info in result:
                for pname in ['start','end']:
                    val = word_info.get(pname)
                    if val is not None:
                        word_info[pname] = round( val - time_offset, 6 )

    def resconvert(self, obj, seg_size, frame_offset=0 ) :
        if obj is None:
            return
        result = obj.get('result', obj.get('partial_result') )
        if result is not None:
            time_offset = round( frame_offset / self.samplerate, 6 )
            for w in result:
                st = w.get('start')
                frame_start = int( st * self.samplerate + frame_offset) if st is not None else None
                seg_start = int( frame_start / seg_size ) if frame_start is not None else None
                et = w.get('end')
                frame_end = int( et * self.samplerate + frame_offset) if et is not None else None
                seg_end = int( frame_end / seg_size ) if frame_end is not None else None

                if seg_start is not None:
                    w['seg_start'] = seg_start
                if seg_end is not None:
                    w['seg_end'] = seg_end
                if frame_start is not None:
                    w['frame_start'] = frame_start
                if frame_end is not None:
                    w['frame_end'] = frame_end
                if st is not None:
                    w['time_start'] = round( st + time_offset, 6 )
                if et is not None:
                    w['time_end'] = round( et + time_offset, 6 )

    def create_vosk(self) ->KaldiRecognizer :
        if self.model_lang is None:
            self.model_lang = RecognizerEngine.get_vosk_model(lang="ja")
        if self.model_spk is None:
            self.model_spk = RecognizerEngine.get_vosk_spk_model(self.model_lang)

        vosk: KaldiRecognizer = KaldiRecognizer(self.model_lang, int(self.samplerate/1) )
        if self.model_spk is not None:
            vosk.SetSpkModel( self.model_spk )
        vosk.SetWords(True)
        vosk.SetPartialWords(True)
        return vosk

    def fn_vosk(self, filename):
        try:
            # voskの設定
            wave_mono_float = self.wave_buf[:,0] * 32767.0
            wave_mono_int16 = wave_mono_float.astype(np.int16)
            frame_len = len(wave_mono_int16)
            seg_size = int(self.samplerate * 0.4) # 0.2秒
            audio_sec = frame_len / self.samplerate
            vst = time.time()
            res_list = []
            vosk = self.create_vosk()
            adjust = 0
            for frame_start in range( 0, frame_len, seg_size ):
                frame_end = min( frame_start+(seg_size*2), frame_len )

                seg_time_start = round( frame_start / self.samplerate, 6 )
                seg_time_end = round( frame_end / self.samplerate, 6 )

                seg_start = int( frame_start / seg_size )
                seg_end = int( frame_end / seg_size )

                seg = wave_mono_int16[frame_start:frame_end]
                b = seg.tobytes()
                res = None
                text = ''
                # if self.vosk.AcceptWaveform( b ):
                #     res = json.loads(self.vosk.Result())
                #     text = res.get('text','')
                # elif idx_end <= slen:
                #     res = json.loads(self.vosk.PartialResult())
                #     text = res.get('partial','')
                # else:
                #     res = json.loads(self.vosk.FinalResult())
                #     text = res.get('text','')
                vosk.AcceptWaveform( b )
                res = json.loads(vosk.FinalResult())
                self.vosk_words_bugfix(res,adjust)
                vosk.Reset()
                adjust += (frame_end-frame_start)
                text = res.get('text','')
                # if text != '':
                res['time_start'] = seg_time_start
                res['time_end'] = seg_time_end
                res['seg_start'] = seg_start
                res['seg_end'] = seg_end
                res['frame_start'] = frame_start
                res['frame_end'] = frame_end
                self.resconvert(res,seg_size,frame_start)
                res_list.append( res )
            vet = time.time()
            vosk_sec = (vet-vst)
            with open( filename,'w') as out:
                json.dump( res_list, out, ensure_ascii=False, indent=4 )
            print(f"audio: {audio_sec:.3f}(sec) vosk:{vosk_sec:.3f}(sec)")
        except:
            traceback.print_exc()

def cosine_similarity1(vec1, vec2):
    """
    2つのベクトルのコサイン類似度を計算する。

    :param vec1: ベクトル1 (numpy array)
    :param vec2: ベクトル2 (numpy array)
    :return: コサイン類似度
    """
    dot_product = np.dot(vec1, vec2)
    norm_vec1 = np.linalg.norm(vec1)
    norm_vec2 = np.linalg.norm(vec2)
    similarity = dot_product / (norm_vec1 * norm_vec2)
    
    return similarity

def play_segment( wave_buf, samplerate ):
    if wave_buf is not None:
        sd.play(wave_buf, samplerate, blocksize=8000 )
        sd.wait()  # 再生が完了するまで待機

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
        # デバッグ用ログ出力
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
        self.pip1_sw:int = 0
        self.pip1:list[Queue] = [Queue(),Queue()]
        self.pip1_threads:list[Thread] = [None,None]
        # セグメント結合処理
        self.pip2_sw = 0
        self.pip2_before_idx=-1
        self.pip2_q:list[Queue] = [Queue(),Queue()]
        self.pip2_thread:Thread = None
        self.xxxx:VoskSegList = None

    def add_to_buffer(self, array):
        if not isinstance(array, np.ndarray) or array.dtype != np.float32:
            raise TypeError("引数はNumPyのfloat32配列でなければなりません")
        with self.buffer_lock:
            self.buffer = np.concatenate((self.buffer, array))
            ll:int = len(self.buffer)
            while (ll-self.detect_idx)>(self.seg_frames*3):
                self.pip1[self.pip1_sw].put( self.detect_idx + self.buffer_offset )
                self.detect_idx += self.seg_frames * 2
                self.pip1_sw = (self.pip1_sw+1) % len(self.pip1_threads)
        with self.thread_lock:
            for i in range(0,len(self.pip1_threads)):
                if self.pip1_threads[i] is None:
                    t:Thread = Thread( name=f"vosk{i}", target=self._th_vosk, args=(i,) )
                    self.pip1_threads[i] = t
                    t.start()

    def create_vosk(self) ->KaldiRecognizer :
        if self.model_lang is None:
            self.model_lang = RecognizerEngine.get_vosk_model(lang="ja")
        if self.model_spk is None:
            self.model_spk = RecognizerEngine.get_vosk_spk_model(self.model_lang)

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
            print(f"[vosk{no}]start")
            vosk = self.create_vosk()
            bugfix_frames = 0
            q_in = self.pip1[no]
            q_out = self.pip2_q[no]
            while True:
                index_start = q_in.get( block=True, timeout=1.0 )
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
                wave_mono_float = buf * 32767.0
                wave_mono_int16 = wave_mono_float.astype(np.int16)
                b = wave_mono_int16.tobytes()
                vosk.AcceptWaveform( b )
                res = json.loads(vosk.FinalResult())
                self._vosk_words_bugfix(res,index_start,bugfix_frames)
                res['index'] = index_start
                vosk.Reset()
                bugfix_frames += len(wave_mono_int16)
                q_out.put( res )
                with self.thread_lock:
                    if self.pip2_thread is None:
                        t = Thread( name='pip2', target=self._th_pip2 )
                        self.pip2_thread = t
                        t.start()
        except Empty:
            pass
        except:
            traceback.print_exc()
        finally:
            with self.thread_lock:
                self.pip1_threads[no] = None
            print(f"[vosk{no}]exit")

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

    def _th_pip2(self):
        try:
            margin_frames = int( self.samplerate * 0.4 )
            print(f"[voskX]start")
            vosk_seg_list:VoskSegList = self.xxxx
            if vosk_seg_list is None:
                vosk_seg_list = VoskSegList()
                self.xxxx = vosk_seg_list
            while True:
                try:
                    res = self.pip2_q[self.pip2_sw].get( block=True, timeout=1.0 )
                except Empty:
                    with self.thread_lock:
                        if self.pip1_threads[0] is None:
                            break
                self._append_json_log(res)
                index_start = res.get('index',0)
                idx = int( index_start / (self.seg_frames*2) )
                if self.pip2_before_idx>=0 and self.pip2_before_idx+1 != idx:
                    raise Exception(f"[voskX]invalid index {self.pip2_before_idx} {idx} frame:{index_start}")
                self.pip2_before_idx = idx
                time_start = round( index_start / self.samplerate, 6 )
                print( f"[voskX]get q:{self.pip2_sw} idx:{idx} frame:{index_start} time {time_start}")
                self.pip2_sw = (self.pip2_sw+1)%len(self.pip2_q)
                seglist:list[VoskSegment] = vosk_seg_list.get_segment( time_start )
                for seg in seglist:
                    print(f"voice seg {seg.start} {seg.end}")
                    seg.sort()
                    seg.test()
                    for vw in seg.wordlist:
                        print( f"    {vw.start:.3f} - {vw.end:.3f}  {vw.frame_start}-{vw.frame_end} {vw.word}")
                    with self.buffer_lock:
                        a = (seg.frame_start-margin_frames) - self.buffer_offset
                        b = (seg.frame_end+margin_frames) - self.buffer_offset
                        set_buf = self.buffer[a:b]
                    self._callback( seg.frame_start, seg.frame_end, set_buf, self.samplerate, )
                vosk_seg_list.add_result( res, index=idx )
        except Empty:
            print(f"[voskX]empty")
            pass
        except:
            traceback.print_exc()
        finally:
            with self.thread_lock:
                self.pip2_thread = None
            self._flush_json_log()
            print(f"[voskX]exit")

    plist=['start','end']

class SpkVect:

    def __init__(self,spk):
        self.vect=spk
        self.norm = np.linalg.norm(spk)
        self.grp=0

    def dist(self,other):
        return cosine_similarity( self.vect, other.vect )

def cosine_similarity(vec1:SpkVect, vec2:SpkVect):
    dot_product = np.dot(vec1.vect, vec2.vect)
    similarity = dot_product / (vec1.norm * vec2.norm)
    return similarity

class SpkList:
    def __init__(self):
        self.spklist:list[SpkVect] = []
    def add(self,spk) ->SpkVect:
        new_vect = SpkVect(spk)
        max=0
        grp_idx=-1
        for vect in self.spklist:
            d = cosine_similarity(new_vect,vect)
            if d>max:
                max=d
                grp_idx=vect.grp
        if max>0.4:
            new_vect.grp=grp_idx
        else:
            new_vect.grp=len(self.spklist)
        self.spklist.append(new_vect)
        return new_vect
   
class WordPlot:

    def load_recording(self,filename):
        try:
            with wave.open(filename, 'rb') as wf:
                samplerate = int(wf.getframerate())
                channels = int(wf.getnchannels())
                frames = wf.getnframes()
                buf_bytes = wf.readframes(frames)
                print(f"loaded rate:{samplerate} frames:{frames}")
                wave_buf = np.frombuffer(buf_bytes, dtype=np.int16).astype(np.float32) / 32767.0
                wave_buf = wave_buf.reshape(-1, channels)
                return wave_buf,samplerate,channels
        except:
            traceback.print_exc()
        return None,None,None

    def play_segment(self, wave_buf, samplerate, start_time=0, end_time=None):
        if wave_buf is not None:
            start_sample = int(start_time * samplerate)
            if end_time is not None:
                end_sample = int(end_time * samplerate)
                wave_buf = wave_buf[start_sample:end_sample]
            else:
                wave_buf = wave_buf[start_sample:]

            sd.play(wave_buf, samplerate, blocksize=8000 )
            sd.wait()  # 再生が完了するまで待機
            pass

    def play(self,json_file_path, wave_file):
        # JSONファイルを読み込む
        with open(json_file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        # a
        wave_buf, samplerate, channels = self.load_recording( wave_file )

        vosk_seg_list:VoskSegList = VoskSegList()

        self.sample_rate = 44100
        seg_size = int(self.sample_rate * 0.4) # 0.2秒
        frame_len=len(data)
        for idx, entry in enumerate(data):
            frame_start = idx * seg_size
            time_start = round( frame_start / self.sample_rate, 6 )
            print( f"t {time_start} {entry['time_start']}")
            if time_start>3.8:
                print("*")
            seglist:list[VoskSegment] = vosk_seg_list.get_segment( time_start )
            for seg in seglist:
                print(f"voice seg {seg.start} {seg.end}")
                p_start = int( samplerate * seg.start )
                p_end = int( samplerate * seg.end )
                print( f" {seg.start} {seg.end} ")
                seg.sort()
                for vw in seg.wordlist:
                    print( f"    {vw.start} - {vw.end} {vw.word}")
                self.play_segment( wave_buf, samplerate, seg.start-0.4, seg.end+0.4 )
                time.sleep(1.0)
            vosk_seg_list.add_result( entry, index=idx )
        
        vosk_seg_list.sort()

    def seg_plot(self,json_file_path ):
        # JSONファイルを読み込む
        with open(json_file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        vosk_seg_list:VoskSegList = VoskSegList()
        plotlist:list[VoskSegment] = []
        self.sample_rate = 44100
        seg_size = int(self.sample_rate * 0.4) # 0.2秒

        for idx, entry in enumerate(data):
            frame_start = idx * seg_size
            time_start = round( frame_start / self.sample_rate, 6 )
            seglist2:list[VoskSegment] = vosk_seg_list.get_segment( time_start )
            for seg in seglist2:
                plotlist.append(seg)
            vosk_seg_list.add_result( entry, index=idx )
        
        mk='o'
        color_list = ['red', 'green', 'blue', 'orange', 'purple', 'brown', 'olive', 'cyan']

        for seg_index,time_seg in enumerate(plotlist):
            for word_index,time_word in enumerate(time_seg.wordlist):
                time_start = time_word.start
                time_end = time_word.end
                word = time_word.word
                i = time_word.index
                j = time_word.subindex
                #
                current_offset = word_index
                # 横線を描き、単語を表示
                color = color_list[ seg_index % len(color_list)]
                plt.plot([time_start, time_end], [current_offset, current_offset], marker=mk, markersize=6, color=color )
                label = f"{i}-{j}:{word}"
                plt.text((time_start + time_end) / 2, current_offset, label, ha='center', va='bottom', fontname =fontname, color=color)
                
        plt.title('word plot')
        plt.xlabel('time(Sec)')
        plt.ylabel('index')
        plt.grid(True)
        plt.tight_layout()

        plt.show()

    def spk_plot(self,json_file_path):
        # JSONファイルを読み込む
        with open(json_file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        spkvec = []
        for idx, entry in enumerate(data):
            spk = entry.get('spk')
            if spk is not None:
                spkvec.append( spk )

        # PCAオブジェクトの作成、n_components=2で2次元に設定
        pca = PCA(n_components=2)

        # spkvecにPCAを適用
        transformed_data = pca.fit_transform(spkvec)

        # プロットの作成
        plt.scatter(transformed_data[:, 0], transformed_data[:, 1])
        plt.xlabel('PC1')
        plt.ylabel('PC2')
        plt.title('2D PCA of spkvec')
        plt.show()

def VS_callback(s,e,buf,samplerate):
    print( f"    PLAY {s}-{e}")
    play_segment( buf, samplerate )
    time.sleep(1.0)

def main():
    wave_file = 'nakagawke01.wav'
    wave_file = 'test2.wav'
    json_log_file = os.path.splitext(wave_file)[0]+'_log.json'
    if os.path.exists( json_log_file ):
        os.remove( json_log_file)
    try:
        with wave.open(wave_file, 'rb') as wf:
            samplerate = int(wf.getframerate())
            channels = int(wf.getnchannels())
            frames = wf.getnframes()
            buf_bytes = wf.readframes(frames)
            print(f"loaded rate:{samplerate} frames:{frames}")
            wave_buf = np.frombuffer(buf_bytes, dtype=np.int16).astype(np.float32) / 32767.0
            if channels>1:
                wave_f32 = wave_buf.reshape(-1, channels)
                # 左右のチャンネルを平均してモノラルに変換
                wave_buf = np.mean(wave_f32, axis=1)
                wave_f32 = None

        VS = VoiceSplitter(samplerate, callback=VS_callback, json_log=json_log_file)
        seg_size = int(samplerate * 0.1)
        for idx in range(0,frames,seg_size):
            seg = wave_buf[idx:idx+seg_size]
            VS.add_to_buffer( seg )
        zeros=np.zeros( seg_size, dtype=np.float32)
        for idx in range(0,10):
            VS.add_to_buffer( zeros )

    except:
        traceback.print_exc()
    return None,None,None

def main2():
    Rec = Recorder()

    wave_file = 'test.wav'
    wave_file = 'nakagawke01.wav'
    json_file = os.path.splitext(wave_file)[0]+'_vosk.json'
    # Rec.load_recording( wave_file )
    # Rec.fn_vosk( json_file )
    wpl = WordPlot()
    wpl.seg_plot(json_file)
    wpl.play(json_file,wave_file)

if __name__ == '__main__':
    main()
    #test()