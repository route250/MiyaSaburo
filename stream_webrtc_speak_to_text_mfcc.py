import os,sys
import asyncio
import traceback
import threading, queue
import streamlit as st
from streamlit_webrtc import WebRtcMode, WebRtcStreamerContext, webrtc_streamer
import av
import pydub
import numpy as np
from scipy.signal import resample
import vosk
from vosk import Model, KaldiRecognizer
import json
import librosa
import pyworld as pw
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
from MiyaSaburo.DxBotUtils import VoiceSeg

vosk.SetLogLevel(-1)

def clear_queue( queue:queue.Queue ):
    try:
        while True:
            queue.get_nowait()
    except:
        pass

class VVVoiceSeg:

    def __init__(self):
        self.f0_cut =0.2
        self.f0_mid = 0.75
        self._buf_sz = 10
        self._buf_count=0
        self._buf_list = [None] * (self._buf_sz+1)
        self._before_level = 0
        self._before_rec:bool = False
    
    def reset(self):
        self._buf_count = 0

    # F0をカウントして有声無声判定
    # https://blog.shinonome.io/voice-recog-random/
    # https://qiita.com/zukky_rikugame/items/dea51c60bfb984d39029
    def _f0_ratio( self, wave_float64, sr ) ->float:
        _f0, t = pw.dio(wave_float64, sr) 
        f0 = pw.stonemask(wave_float64, _f0, t, sr)
        f0_vuv = f0[f0 > 0] # 有声・無声フラグ
        vuv_ratio = len(f0_vuv)/len(f0) # 有声部分の割合
        return vuv_ratio

    def _calc_mfcc(self, wave_float2, frame_rate ):
        mfcc_list = librosa.feature.mfcc(  y=wave_float2, sr=frame_rate, n_mfcc=20, n_fft=512 )
        mfcc_13 = mfcc_list[ 1:14, : ]
        # mfcc = np.average(mfcc_13,axis=1)
        # mfcc = np.mean(mfcc_13,axis=1)
        mfcc = np.max(mfcc_13,axis=1)
        return mfcc

    def put(self, wave:np.ndarray, frame_rate:int, xflg:bool = False ):
        wave_int16:np.ndarray = wave.astype(np.int16)
        wave_float64:np.ndarray = wave.astype(np.float64)
        wave_float64 = wave_float64 / 32767.0
        f0_ratio = self._f0_ratio( wave_float64, frame_rate )
        f0_level = 2 if f0_ratio>self.f0_mid else 1 if f0_ratio>self.f0_cut else 0
        flush:bool = False
        rec:bool = self._before_rec
        if xflg:
            rec = True
        if rec:
            if self._before_level==0 and f0_level==0:
                flush = True
                rec = False
        else:
            if f0_level>=2:
                rec = True
            else:
                if self._buf_count>1:
                    for idx in range(1,self._buf_count):
                        self._buf_list[idx-1] = self._buf_list[idx]
                    self._buf_count -= 1

        if self._before_level != f0_level or self._before_rec != rec:
            print(f"[frame] F0 ratio:{f0_ratio:6.3f} {self._before_level} to {f0_level} rec:{rec}")

        self._buf_list[self._buf_count] = wave_int16
        self._buf_count += 1
        self._before_level = f0_level
        self._before_rec = rec

        if flush or self._buf_count>=self._buf_sz:
            # 有声から無声に変化した、もしくは、バッファがいっぱいなら
            concat_int16 = np.concatenate(self._buf_list[:self._buf_count])
            self._buf_count = 0
            # mfcc計算
            wave_float = concat_int16.astype(np.float64)
            wave_float2 = wave_float / 32767.0
            mfcc = self._calc_mfcc( wave_float2, frame_rate )
            # byteデータへ変換
            #byte_data = concat_int16.astype(np.int16).tobytes()
            # 次のキューへ
            return f0_level, concat_int16, mfcc
        else:
            return f0_level, None, None
        
    def put1(self, wave:np.ndarray, frame_rate:int, xflg:bool = False ):
        wave_int16:np.ndarray = wave.astype(np.int16)
        wave_float64:np.ndarray = wave.astype(np.float64)
        wave_float64 = wave_float64 / 32767.0
        f0_ratio = self._f0_ratio( wave_float64, frame_rate )
        f0_level = 2 if f0_ratio>self.f0_mid else 1 if f0_ratio>self.f0_cut else 0
        if self._before_level != f0_level:
            print(f"[frame] F0 ratio:{f0_ratio:6.3f} {self._before_level} to {f0_level}")
        
        self._buf_list[self._buf_count] = wave_int16
        self._buf_count += 1
        flush:bool = self._buf_count >= self._buf_sz
        if self._before_level >= 2:
            if f0_level >= 2:
                pass
            elif f0_level == 1:
                flush = True
            else:
                flush = True
        elif self._before_level == 1:
            if f0_level >= 2:
                pass
            elif f0_level == 1:
                pass
            else:
                flush = True
        else:
            if f0_level >= 2:
                pass
            else:
                self._buf_list[0] = wave_int16
                self._buf_count = 1
        self._before_level = f0_level
        if flush:
            # 有声から無声に変化した、もしくは、バッファがいっぱいなら
            concat_int16 = np.concatenate(self._buf_list[:self._buf_count])
            self._buf_count = 0
            # mfcc計算
            wave_float = concat_int16.astype(np.float64)
            wave_float2 = wave_float / 32767.0
            mfcc = self._calc_mfcc( wave_float2, frame_rate )
            # byteデータへ変換
            #byte_data = concat_int16.astype(np.int16).tobytes()
            # 次のキューへ
            return f0_level, concat_int16, mfcc
        else:
            return f0_level, None, None
        
class VoiceWorker:

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._lock:threading.Lock = threading.Lock()
        self._frame_thread:threading.Thread = None
        self._th_audio:threading.Thread = None
        self._th_detect:threading.Thread = None
        self._th_mfcc:threading.Thread = None
        self._vosk_model = None
        self._sample_rate = 0
        self.recognizer = None
        self.racog   = None
        self._frame_queue = queue.Queue()
        self._audio_queue = queue.Queue()
        self._detect_queue = queue.Queue()
        self._mfcc_queue = queue.Queue()
        self._ui_queue = queue.Queue()
        self._started = False
        self._abort = False

    def start(self):
        with self._lock:
            self._started = True
            pass
            # self._th1 = threading.Thread( target=self._fn_audioframe_thread,daemon=True)
            # self._th2 = threading.Thread( target=self._fn_th2,daemon=True)
            # self._th3 = threading.Thread( target=self._fn_mfcc_thread,daemon=True)
            # self._th1.start()
            # self._th2.start()
            # self._th3.start()

    def stop(self):
        self._abort=True
        with self._lock:
            self._th_audio.join(2)
            self._th_detect.join(2)

    def put_frame(self, frame:av.AudioFrame ):
        """streamlit-webrtcからの受信窓口"""
        try:
            if self._started and not self._abort:
                if self._frame_thread is None:
                    with self._lock:
                        if self._frame_thread is None:
                            self._frame_thread = threading.Thread( target=self._fn_audioframe_thread,daemon=True)
                            self._frame_thread.start()
                self._frame_queue.put_nowait(frame)
        except:
            pass

    def _fn_audioframe_thread(self):
        """av.AudioFrameをバイトデータに変換"""
        try:
            print(f"[frame]start")
            self.is_alive=True
            sample_rate = 0
            buff_sz = 10
            buff_count=0
            buff_list = [None]*buff_sz

            while self._started and not self._abort:
                try:
                    frame:av.AudioFrame = self._frame_queue.get(timeout=0.5)
                    sample_width=frame.format.bytes
                    frame_rate=frame.sample_rate
                    channels=len(frame.layout.channels)
                    audio = np.array(frame.to_ndarray())

                    # ステレオをモノラルに変換（チャンネルの平均を取る）
                    left = audio[0][::2]
                    right = audio[0][1::2]
                    mono = left

                    if frame_rate != sample_rate:
                        sample_rate = frame_rate
                        block_size = len(mono)
                        buff_sz = int( (sample_rate / 10 * 1) / block_size )
                        buff_list = [None] * buff_sz
                        buff_count = 0
                        print(f"[frame]sample_rate:{frame_rate}Hz bz:{block_size} x len:{buff_sz}")

                    buff_list[buff_count] = mono
                    buff_count+=1
                    if buff_count>=buff_sz:
                        # 結合
                        concat_list = np.concatenate(buff_list)
                        buff_count = 0
                        wave_int16 = concat_list.astype(np.int16)
                        # 次のキューへ
                        self._put_detect( wave_int16,sample_rate )

                    self._frame_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as ex:
                    self._frame_queue.task_done()
                    traceback.print_exc()
                    self._abort=True
        except Exception as ex:
            traceback.print_exc()
        finally:
            print(f"[frame]exit")
            self._abort=True
            self.is_alive=False

    def put_audio(self, byte_data, sample_rate ):
        try:
            if self._started and not self._abort:
                if self._th_audio is None:
                    with self._lock:
                        if self._th_audio is None:
                            self._th_audio = threading.Thread( target=self._fn_audio_thread,daemon=True)
                            self._th_audio.start()
                self._audio_queue.put_nowait(byte_data,sample_rate)
        except:
            pass

    def _fn_audio_thread(self):
        try:
            print(f"[AUDIO]start")
            self.is_alive=True
            while self._started and not self._abort:
                try:
                    byte_data, frame_rate = self._audio_queue.get(timeout=0.5)
                    # 変換
                    mono = np.frombuffer( byte_data, dtype=np.int16 )
                    # 次のキューへ
                    self._put_detect( mono,frame_rate )
                    self._audio_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as ex:
                    self._audio_queue.task_done()
                    traceback.print_exc()
                    self._abort=True
        except Exception as ex:
            traceback.print_exc()
        finally:
            print(f"[AUDIO]exit")
            self._abort=True
            self.is_alive=False

    def _put_detect(self, byte_data, sample_rate ):
        try:
            if self._started and not self._abort:
                if self._th_detect is None:
                    with self._lock:
                        if self._th_detect is None:
                            self._th_detect = threading.Thread( target=self._fn_detect_thread,daemon=True)
                            self._th_detect.start()
                self._detect_queue.put_nowait( (byte_data,sample_rate) )
        except:
            pass

    def _fn_reload_vosk(self,rate):
        print(f"[VOSK]reload vosk {rate}Hz")
        if self._vosk_model is None:
            # Voskモデルを読み込む
            self._vosk_model = Model(lang="ja")
        self._sample_rate = rate
        self.recognizer:KaldiRecognizer = KaldiRecognizer(self._vosk_model, self._sample_rate)

    def _fn_detect_thread(self):
        try:
            print(f"[VOSK]start vosk")
            sample_rate = 0
            before_text = ''
            vflag = False
            Splitter: VoiceSeg = VoiceSeg()
            xflg:bool = False
            while self._started and not self._abort:
                try:
                    xwave_int16, frame_rate = self._detect_queue.get(timeout=0.5)
                    if sample_rate != frame_rate:
                        sample_rate = frame_rate
                        print(f"[VOSK]sample_rate:{sample_rate}Hz")
                        self._fn_reload_vosk( sample_rate )
                        Splitter = VoiceSeg()

                    f0_lv, wave_int16, mfcc = Splitter.put( xwave_int16, frame_rate, vflag )
                    if wave_int16 is None:
                        continue

                    wave_data = wave_int16.tobytes()

                    # if not vflag and magnitude<100:
                    #     #print(f"[VOSK] {magnitude}" )
                    #     self._put_mfcc( sample_rate,mfcc,0 )
                    if self.recognizer.AcceptWaveform(wave_data) or f0_lv<0:
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text')
                        if text is not None and len(text)>0:
                            print(f"[VOSK] final:{text}")
                            vflag = False
                            self._put_mfcc( sample_rate,mfcc,4 )
                        else:
                            print(f"[VOSK] final None")
                            self.recognizer.Reset()
                            vflag = False
                            self._put_mfcc( sample_rate,mfcc,1 )
                        before_text = ''
                    else:
                        result = json.loads(self.recognizer.PartialResult())
                        text = result.get('partial')
                        if text is not None and len(text)>0:
                            vflag = True
                            self._put_mfcc( sample_rate,mfcc,3 )
                            if before_text != text:
                                print(f"[VOSK] partial:{text}" )
                                before_text = text
                        else:
                            vflag = False
                            self._put_mfcc( sample_rate,mfcc,2 )
                    self._detect_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as ex:
                    self._detect_queue.task_done()
                    traceback.print_exc()
                    pass
        except Exception as ex:
            traceback.print_exc()
        finally:
            self._abort=True
            self.is_alive=False
            print(f"[VOSK] exit")

    def _put_mfcc(self, sample_rate, mfcc, flag ):
        try:
            if self._started and not self._abort:
                if self._th_mfcc is None:
                    with self._lock:
                        if self._th_mfcc is None:
                            self._th_mfcc = threading.Thread( target=self._fn_mfcc_thread,daemon=True)
                            self._th_mfcc.start()
                self._mfcc_queue.put_nowait( (sample_rate,mfcc,flag) )
        except:
            pass

    def _fn_mfcc_thread(self):
        try:
            print(f"[MFCC]start")

            plot_size = 100
            plot_mfcc:np.ndarray = np.zeros( (plot_size,13),dtype=float)
            plot_flag:np.ndarray = np.zeros( plot_size, dtype=int)

            segment_size = 10
            mfcc_segment:np.ndarray = np.zeros( (segment_size,13),dtype=float)
            flag_segment:np.ndarray = np.zeros( segment_size, dtype=int)
            segment_count = 0

            while not self._abort:
                try:
                    frame_rate,mfcc,flg = self._mfcc_queue.get(timeout=0.5)
                    mfcc_segment[segment_count] = mfcc
                    flag_segment[segment_count] = flg
                    segment_count += 1
                    if segment_count>=segment_size:
                        combined = np.concatenate([plot_mfcc, mfcc_segment], axis=0)
                        plot_mfcc = combined[-plot_size:]
                        combined = np.concatenate([plot_flag, flag_segment], axis=0)
                        plot_flag = combined[-plot_size:]
                        # プロット用にMFCCデータを転置する
                        mfcc_transposed = np.transpose(plot_mfcc)
                        self._ui_queue.put( (mfcc_transposed,plot_flag) )
                        segment_count = 0
                except queue.Empty:
                    continue
        except Exception as ex:
            traceback.print_exc()
        finally:
            self._abort=True
            self.is_alive=False
            print(f"[VOSK] exit")

# グローバル変数として描画オブジェクトを初期化
global fig, ax1, ax2, heatmap, lineplot

fig, (ax1,ax2) = plt.subplots( 2, 1, sharex=True, figsize=(10, 8))
heatmap = None
lineplot = None

# ヒートマップをプロットする関数
def plot_mfcc_heatmap(parent,mfcc_list, flag_list):
    global fig, ax1, ax2, heatmap, lineplot

    # ヒートマップがすでに存在する場合は更新する
    if heatmap is None:
        # 初めてヒートマップを描画する場合
        heatmap = ax1.imshow(mfcc_list, cmap='hot', interpolation='nearest', vmin=0, vmax=100)
        ax1.set_title('MFCC')
        ax1.set_ylabel('MFCC Coefficients')
        ax1.set_xlabel('Frames')
        #fig.colorbar(heatmap, ax=ax1)
        # カラーバーをヒートマップの右側に追加
        # divider = make_axes_locatable(ax1)
        # cax = divider.append_axes("right", size="5%", pad=0.05)
        # fig.colorbar(heatmap, cax=cax)
    else:
        heatmap.set_data(mfcc_list)
    
    if lineplot is None:
        lineplot, = ax2.plot( flag_list )
        ax2.set_title('Flag')
        ax2.set_ylabel('Flag')
        ax2.set_xlabel('Frames')
        ax2.set_ylim([0,4])
    else:
        lineplot.set_ydata( flag_list )

    # Streamlitに図を表示
    parent.pyplot(fig)

def main():
    # recognizerをセッション状態で管理する
    if 'worker' in st.session_state:
        z_worker:VoiceWorker = st.session_state.worker
    else:
        st.session_state.worker = VoiceWorker()
        z_worker = st.session_state.worker
        z_worker.start()

    def fn_audio_frame_callback(audio_frame):
        try:
            z_worker.put_frame(audio_frame)
        except Exception as ex:
            print(f"error {ex}")
            #st.write( f"ERROR:{ex}" )

    st.title("My first Streamlit app")
    st.write("Hello, world")

    ww:WebRtcStreamerContext = webrtc_streamer(
        key="example",
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=40960,
        media_stream_constraints={"video": False, "audio": True},
        audio_frame_callback=fn_audio_frame_callback
    )

    st.write(f" state: {ww.state}")
    plot_area = st.empty()
    #plot_area.write("plot...")
    if ww.state.playing:
        try:
            print( f"[GUI]playing start " )
            empty= False
            while True:
                try:
                    mfcc_list, flag_list = z_worker._ui_queue.get( timeout=0.5)
                    #print( f"[GUI] get! " )
                    plot_mfcc_heatmap(plot_area, mfcc_list, flag_list)
                except queue.Empty:
                    if ww.state.playing:
                        continue
                    else:
                        break
        finally:
            print( f"[GUI]playing end" )
    else:
        print( f"[GUI]stop" )
    

if __name__ == "__main__":
    main()