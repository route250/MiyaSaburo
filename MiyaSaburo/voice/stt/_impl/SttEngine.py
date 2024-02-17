import os,sys,traceback,time
from threading import Thread, Condition
import sounddevice as sd
import numpy as np
import wave
import datetime

from .VoiceSplitter import VoiceSplitter
from .Recognizer import RecognizerGoogle
from urllib.error import URLError, HTTPError

import logging
logger = logging.getLogger('voice')

def _mic_priority(x):
    devid = x['index']
    name = x['name']
    if 'default' in name:
        return 10000 + devid
    if 'USB' in name:
        return 20000 + devid
    return 90000 + devid

def get_mic_devices( *, samplerate=None, channels=None, dtype=None ):
    sr:float = float(samplerate) if samplerate else 16000
    channels:int = int(channels) if channels else 1
    dtype = dtype if dtype else np.float32
    # select input devices
    inp_dev_list = [ x for x in sd.query_devices() if x['max_input_channels']>0 ]
    # select avaiable devices
    mic_dev_list = []
    for x in inp_dev_list:
        mid = x['index']
        name = f"[{mid:2d}] {x['name']}"
        try:
            sd.check_input_settings( device=mid, channels=channels, samplerate=sr, dtype=dtype )
            with sd.InputStream( samplerate=sr, device=mid, channels=channels) as audio_in:
                frames,overflow = audio_in.read(1000)
                if max(abs(frames.squeeze()))<1e-9:
                    logger.debug(f"NoSignal {name}")
                    continue
            logger.debug(f"Avairable {name}")
            mic_dev_list.append(x)
        except sd.PortAudioError:
            logger.debug(f"NoSupport {name}")
        except:
            logger.exception()
    mic_dev_list = sorted( mic_dev_list, key=_mic_priority)
    for x in mic_dev_list:
        print(f"[{x['index']:2d}] {x['name']}")
    return mic_dev_list

# 録音機能のクラス
class SttEngine:
    E1 = '音声認識の結果が不明瞭'
    def __init__(self, *, callback=None, samplerate=16000, channels=1):
        self._callback = callback
        self.inp_dev_list = get_mic_devices(samplerate=samplerate, channels=channels, dtype=np.float32)
        self.input_device = None
        self.input_device_info = None
        self.samplerate:int = samplerate
        self.channels:int = channels
        self.recording:bool = False

        self.audioinput:sd.InputStream = None
        self.splitter:VoiceSplitter=None
        self.recognizer: RecognizerGoogle = None
        self.text_list:list[str]=[]
        self.text_confidence:float = 1.0
        self.networkerror:bool=False
        self._lock:Condition = Condition()
        self._pause:bool = False
        # 保存用
        self._save_buffer:np.ndarray = None
        self._save_pos:int = 0

    def set_pause(self,b:bool) ->bool:
        with self._lock:
            try:
                if self.audioinput is not None:
                    if b:
                        self.audioinput.stop()
                    else:
                        self.audioinput.start()
            except:
                pass
            if self.splitter is None or self.splitter.set_pause(b):
                self._pause = b
                # print( f"[VoiceRecognizer] success to set pause {b}")
            else:
                logger.debug( f"[VoiceRecognizer] failled to set pause {b}")

    def select_input_device(self):
        try:
            if self.input_device is None:
                self.input_device = next((x['index'] for x in self.inp_dev_list if "default" in x['name'].lower()), self.inp_dev_list[0]['index'])
            if self.input_device is not None:
                self.input_device_info = sd.query_devices( self.input_device, 'input' )
            else:
                self.input_device_info = None
        except Exception as err:
            logger.exception('')

    def start_recording(self):
        try:
            self.select_input_device()
            self.recording = True
            thread = Thread(target=self._th_record)
            thread.start()
            for x in range(0,60):
                if not self.recording:
                    break
                if self.splitter is not None and self.splitter.model_lang is not None:
                    break
                time.sleep(1.0)
        except Exception as err:
            logger.exception('')
            self.recording = False
        finally:
            pass

    def _th_record(self):
        try:
            self.select_input_device()
            if self.input_device_info is None:
                return
            self.samplerate=int(self.input_device_info['default_samplerate'])
            self.samplerate=16000
            self.channels=1
            self.splitter:VoiceSplitter = VoiceSplitter( samplerate=self.samplerate, callback=self._fn_voice_callback )
            self.recognizer = RecognizerGoogle( self.samplerate )
            bs = 8000
            bs = int( self.samplerate*0.2 )
            self.audioinput = sd.InputStream( samplerate=self.samplerate, blocksize=bs, device=self.input_device, channels=self.channels, callback=self._fn_audio_callback )
            self.audioinput.start()

        except Exception as err:
            self.recording = False
            logger.exception('')

    def stop_recording(self):
        self.recording = False
        try:
            try:
                if self.audioinput is not None:
                    self.audioinput.stop()
            except:
                pass
            try:
                if self.splitter is not None:
                    self.splitter.stop()
            except:
                pass
            try:
                if self.recognizer is not None:
                    self.recognizer.stop()
            except:
                pass
        except:
            pass
        finally:
            self.audioinput = None
            self.splitter = None
            self.recognizer=None

    def _fn_audio_callback(self, indata, frames, time, status):
        self._add_save_buffer( indata )
        if self._pause or self.splitter is None:
            return
        try:
            if self.recording and self.splitter is not None:
                # 配列から長さ1の次元を削除
                arr_squeezed = indata.squeeze()
                self.splitter.add_to_buffer(arr_squeezed)
        except Exception as err:
            self.recording=False
            logger.error(f"[callback]exception")
            logger.exception('')

    def _fn_voice_callback(self, start_frame,end_frame, buf, samplerate):
        if self._pause or self.recognizer is None or buf is None:
            return
        try:
            start_sec=round(start_frame/samplerate,6)
            end_sec=round(end_frame/samplerate,6)
            texts=[]
            confs:float = 1.0
            stat=0
            if len(buf)==1 and buf[0]==1.0:
                #print( f"[google] fr[{start_frame}:{end_frame}] {ts:.3f} - {te:.3f} (sec) START")
                if not self.text_list:
                    texts=[]
                    stat=1
            elif len(buf)>1:
                #print( f"[google] fr[{start_frame}:{end_frame}] {ts:.3f} - {te:.3f} (sec)")
                timeout=2.0
                retry = 3
                try:
                    txt,confidence = self.recognizer.recognizef( buf, timeout=timeout, retry=retry, sample_rate=samplerate )
                    self.networkerror = False
                    if txt is None or confidence is None:
                        txt = SttEngine.E1
                        confidence = 0.0
                    stat=2
                except (URLError,HTTPError) as ex:
                    txt = f'通信エラーにより音声認識に失敗しました {type(ex).__name__}:{str(ex)}'
                    confidence = 0.0
                    if self.networkerror:
                        stat = -1
                    else:
                        self.networkerror = True
                        stat=2
                except Exception as ex:
                    txt = f'例外により音声認識に失敗しました。 {type(ex).__name__}:{ex}'
                    confidence = 0.0
                    if self.networkerror:
                        stat = -1
                    else:
                        self.networkerror = True
                        stat=2
                #print(f"[google] {self.textbuffer}")
                if stat==2:
                        self.text_list.append(txt)
                        self.text_confidence = min( self.text_confidence, confidence)
                texts = self.text_list
                confs = self.text_confidence
            else:
                #print( f"[google] fr[{start_frame}:{end_frame}] {ts:.3f} - {te:.3f} (sec) EOT")
                #print(f"[google] {self.textbuffer}")
                texts=self.text_list
                if all(t == SttEngine.E1 for t in texts):
                    texts = []
                confs = self.text_confidence
                stat=3
                self.text_list = []
                self.text_confidence = 1.0
            if stat>0 and self._callback is not None:
                self._callback( start_sec, end_sec, stat, texts, confs )

        except Exception as err:
            self.recording=False
            logger.error(f"[callback]exception")
            logger.exception('')

    def _add_save_buffer(self,audio_data:np.ndarray ):
            if not isinstance(audio_data,np.ndarray) or audio_data.dtype != np.float32:
                return
            audio_data = audio_data.squeeze()
            sec = 3*60
            bufsize = int(self.samplerate*sec)
            e = self._save_pos + len(audio_data)
            if self._save_buffer is None or e>bufsize:
                if self._save_buffer is not None and self._save_pos>0:
                    t = Thread( target=self._save_th, args=(self._save_buffer,self._save_pos))
                    t.start()
                self._save_buffer = np.zeros(bufsize)
                self._save_pos = 0
                e = self._save_pos + len(audio_data)
            self._save_buffer[self._save_pos:e] = audio_data
            self._save_pos = e

    def _save_th(self, audio_data:np.ndarray, len:int ):
        # waveファイルに保存する処理
        try:
            audio_data = audio_data[0:len] * 32768
            audio_bytes=audio_data.astype(np.int16).tobytes()
            dt=datetime.datetime.now()
            wave_filename = dt.strftime('sound_%Y%m%d_%H%M%S.wav')
            wave_path = os.path.join( 'logs', 'wave', wave_filename )
            logger.debug( f'save buffer to {wave_path}')
            os.makedirs( os.path.dirname(wave_path), exist_ok=True )
            with wave.open(wave_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.samplerate)
                wf.writeframes(audio_bytes)
        except:
            logger.exception('can not save wave file')