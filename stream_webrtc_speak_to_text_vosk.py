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

vosk.SetLogLevel(-1)

ui_queue = queue.Queue()

def clear_queue( queue:queue.Queue ):
    try:
        while True:
            queue.get_nowait()
    except:
        pass

class VoiceWorker:

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._lock:threading.Lock = threading.Lock()
        self._th1:threading.Thread = None
        self._th2:threading.Thread = None
        self._vosk_model = None
        self._sample_rate = 0
        self.recognizer = None
        self.racog   = None
        self._frame_queue = queue.Queue()
        self._wave_queue = queue.Queue()
        self.is_alive = False
        self._abort = False

    def put_frame(self, frame ):
        try:
            if self.is_alive:
                self._frame_queue.put_nowait(frame)
        except:
            pass

    def start(self):
        with self._lock:
            self._th1 = threading.Thread( target=self._fn_th11,daemon=True)
            self._th2 = threading.Thread( target=self._fn_th2,daemon=True)
            self._th1.start()
            self._th2.start()

    def stop(self):
        self._abort=True
        with self._lock:
            self._th1.join(2)
            self._th2.join(2)

    def _fn_th11(self):
        try:
            print(f"[AUDIO]start")
            self.is_alive=True
            buff_sz = 10
            buff_count=0
            buff_list = [None]*buff_sz
            while not self._abort:
                try:
                    frame:av.AudioFrame = self._frame_queue.get(timeout=0.5)
                    sample_width=frame.format.bytes
                    frame_rate=frame.sample_rate
                    channels=len(frame.layout.channels)
                    # sound = pydub.AudioSegment(
                    #     data=frame.to_ndarray().tobytes(),
                    #     sample_width=sample_width,
                    #     frame_rate=frame_rate,
                    #     channels=channels,
                    # )
                    # フレームをnumpy配列に変換
                    audio = np.array(frame.to_ndarray())
                    # ステレオをモノラルに変換（チャンネルの平均を取る）
                    left = audio[0][::2]
                    right = audio[0][1::2]
                    mono = left
                    # サンプリングレートによるVOSK再起動
                    if frame_rate != self._sample_rate:
                        block_size = len(mono)
                        buffer_sz = int( (frame_rate / 10 * 2) / block_size )
                        buff_list = [None] * buffer_sz
                        buff_count = 0
                        print(f"[STT]sample_rate:{frame_rate}Hz bz:{block_size} x len:{buffer_sz}")
                        clear_queue( self._wave_queue )
                        self._fn_reload_vosk( frame_rate )

                    buff_list[buff_count] = mono
                    buff_count+=1
                    if buff_count>=buff_sz:
                        xxx = np.concatenate(buff_list)
                        buff_count = 0
                        wave_float = xxx.astype(np.float32)
                        mfcc = librosa.feature.mfcc(  y=wave_float, sr=frame_rate)
                        byte_data = xxx.astype(np.int16).tobytes()
                        self._wave_queue.put( (byte_data,mfcc) )
                except queue.Empty:
                    continue
                except Exception as ex:
                    self._abort=True
        except Exception as ex:
            traceback.print_exc()
        finally:
            print(f"[AUDIO]exit")
            self._abort=True
            self.is_alive=False

    def _fn_reload_vosk(self,rate):
        print(f"[VOSK]reload vosk {rate}Hz")
        if self._vosk_model is None:
            # Voskモデルを読み込む
            self._vosk_model = Model(lang="ja")
        self._sample_rate = rate
        self.recognizer:KaldiRecognizer = KaldiRecognizer(self._vosk_model, self._sample_rate)

    def _fn_th2(self):
        try:
            print(f"[VOSK]start vosk")
            # Voskモデルを読み込む
            #vosk_model = Model(lang="ja")
            #self.recognizer:KaldiRecognizer = KaldiRecognizer(vosk_model, 48000)
            before_text = ''
            mfcc_sz = 10
            mfcc_list = [None] * mfcc_sz
            mfcc_count = 0
            while not self._abort:
                try:
                    wave_data, mfcc = self._wave_queue.get(timeout=0.5)
                    mfcc_list[mfcc_count] = mfcc
                    if mfcc_count>=mfcc_sz:
                        ui_queue.put(mfcc_list)
                        mfcc_list = [None] * mfcc_sz
                        mfcc_count = 0
                    if self.recognizer.AcceptWaveform(wave_data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text')
                        if text is not None and len(text)>0:
                            print(f"[VOSK] final:{text}")
                        else:
                            print(f"[VOSK] final None")
                        before_text = ''
                    else:
                        result = json.loads(self.recognizer.PartialResult())
                        text = result.get('partial')
                        if text is not None and len(text)>0:
                            if before_text != text:
                                print(f"[VOSK] partial:{text}")
                                before_text = text
                except queue.Empty:
                    continue
                except Exception as ex:
                    pass
        except Exception as ex:
            traceback.print_exc()
        finally:
            self._abort=True
            self.is_alive=False
            print(f"[VOSK] exit")

def main():
    # recognizerをセッション状態で管理する
    if 'worker' in st.session_state:
        wk:VoiceWorker = st.session_state.worker
    else:
        st.session_state.worker = VoiceWorker()
        wk = st.session_state.worker
        wk.start()

    def fn_audio_frame_callback(audio_frame):
        try:
            wk.put_frame(audio_frame)
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
    while ww.state.playing:
        try:
            mfcc_list = ui_queue.get( timeout=0.5)
            print( f"[GUI] get! " )
        except queue.Empty:
            continue

    print( f"[WWW]playing..." )

if __name__ == "__main__":
    main()