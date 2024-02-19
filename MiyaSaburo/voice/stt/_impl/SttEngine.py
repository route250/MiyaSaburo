import os,sys,traceback,time
from threading import Thread, Condition
import sounddevice as sd
import numpy as np
import wave
import datetime
from urllib.error import URLError, HTTPError

from .VoiceSplitter import VoiceSplitter
from .Recognizer import RecognizerGoogle
from ..._impl.voice_utils import audio_to_wave

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
    """マイクとして使えるデバイスをリストとして返す"""
    # 条件
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
            # check parameters
            sd.check_input_settings( device=mid, channels=channels, samplerate=sr, dtype=dtype )
            # read audio data
            with sd.InputStream( samplerate=sr, device=mid, channels=channels,) as audio_in:
                frames,overflow = audio_in.read(1000)
                audio_in.abort(ignore_errors=True)
                audio_in.stop(ignore_errors=True)
                audio_in.close(ignore_errors=True)
                if max(abs(frames.squeeze()))<1e-9:
                    logger.debug(f"NoSignal {name}")
                    continue
            logger.debug(f"Avairable {name}")
            mic_dev_list.append(x)
        except sd.PortAudioError:
            logger.debug(f"NoSupport {name}")
        except:
            logger.exception()
    # sort
    mic_dev_list = sorted( mic_dev_list, key=_mic_priority)
    # for x in mic_dev_list:
    #     print(f"[{x['index']:2d}] {x['name']}")
    return mic_dev_list

# 録音機能のクラス
class SttEngine:
    E1 = '音声認識の結果が不明瞭'
    S1:int = 1
    S2:int = 2
    S3:int = 3
    S91:int = 91

    def __init__(self, *, device=None, callback=None, samplerate=16000, channels=1):
        self._callback = callback
        self.input_device = device
        self._selected_device_id = None
        self._selected_device_info = None
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
        # 監視用
        self._last_audio_sec:float = -1
        self._audio_start_sec:float = 0
        self._audio_sec:float = 0
        self._audio_status:sd.CallbackFlags = sd.CallbackFlags()
        self._last_tick_time1:float = 0
        self._last_tick_time3:float = 0

    def set_pause(self,b:bool) ->bool:
        with self._lock:
            # try:
            #     if self.audioinput is not None:
            #         if b:
            #             self.audioinput.stop()
            #         else:
            #             self.audioinput.start()
            # except:
            #     pass
            if self.splitter is None or self.splitter.set_pause(b):
                self._pause = b
                # print( f"[VoiceRecognizer] success to set pause {b}")
            else:
                logger.debug( f"[VoiceRecognizer] failled to set pause {b}")

    def select_input_device(self):
        try:
            if self.input_device is None:
                # 指定がなければ自動選択
                inp_dev_list = get_mic_devices(samplerate=self.samplerate, channels=self.channels, dtype=np.float32)
                self._selected_device_id = inp_dev_list[0]['index'] if inp_dev_list and len(inp_dev_list)>0 else None
            else:
                # 指定があれば、それを使う
                self._selected_device_id = self.input_device
            if self._selected_device_id is not None:
                self._selected_device_info = sd.query_devices( self._selected_device_id, 'input' )
            else:
                self._selected_device_info = None
        except Exception as err:
            logger.exception('')

    def start_recording(self):
        try:
            self.select_input_device()
            self.recording = True
            thread = Thread(target=self._th_record,name='audio_start')
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
            if self._selected_device_info is None:
                return
            self.samplerate=int(self._selected_device_info['default_samplerate'])
            self.splitter:VoiceSplitter = VoiceSplitter( samplerate=self.samplerate, callback=self._fn_voice_callback )
            self.recognizer = RecognizerGoogle( self.samplerate )
            bs = 8000
            bs = int( self.samplerate*0.2 )
            self.audioinput = sd.InputStream( samplerate=self.samplerate, blocksize=bs, device=self._selected_device_id, channels=self.channels, callback=self._fn_audio_callback )
            self._audio_start_sec = time.time()
            self._audio_sec = 0
            self._last_audio_sec = -1
            self.audioinput.start()

        except Exception as err:
            self.recording = False
            logger.exception('')

    def stop_recording(self):
        self.recording = False
        try:
            try:
                if self.audioinput is not None:
                    self.audioinput.abort(ignore_errors=True)
                    self.audioinput.stop(ignore_errors=True)
                    self.audioinput.close(ignore_errors=True)
                    self.audioinput = None
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

    def tick_time(self, time_sec:float ):
        try:
            if not self.recording or (time_sec-self._last_tick_time1)<10:
                return
            self._last_tick_time1 = time_sec
            qsize = self.splitter.qsize() if self.splitter is not None else 0
            overflow = self._audio_status.input_overflow
            underflow = self._audio_status.input_underflow
            self._audio_status.input_overflow=False
            self._audio_status.input_underflow=False
            current_sec = self._audio_sec
            last_sec = self._last_audio_sec
            self._last_audio_sec = current_sec
            t1=int( current_sec-self._audio_start_sec)
            t2=int( last_sec-self._audio_start_sec )
            logger.debug( f"[STT]status frame:{t1}/{t2} qsize:{qsize} overflow:{overflow} underflow:{underflow}")
            if (time_sec-self._last_tick_time3)<30:
                return
            self._last_tick_time3 = time_sec
            if last_sec>=0 and current_sec==last_sec:
                logger.error( f"mic audio stopped??")
                if self._callback is not None:
                    self._callback( current_sec, current_sec, SttEngine.S91, '', 0 )
                self.stop_recording()
                logger.error( f"try restart")
                self.start_recording()
        except:
            logger.exception('error')

    def _fn_audio_callback(self, indata:np.ndarray, frames:int, atime, status:sd.CallbackFlags):
        #print( f"time {atime} {atime.inputBufferAdcTime} {atime.outputBufferDacTime} {atime.currentTime}")
        self._audio_sec += frames/self.samplerate
        if status.input_underflow:
            self._audio_status.input_underflow = True
        if status.input_overflow:
            self._audio_status.input_overflow = True
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
                    stat=SttEngine.S1
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
                    stat=SttEngine.S2
                except (URLError,HTTPError) as ex:
                    txt = f'通信エラーにより音声認識に失敗しました {type(ex).__name__}:{str(ex)}'
                    confidence = 0.0
                    if self.networkerror:
                        stat = -1
                    else:
                        self.networkerror = True
                        stat=SttEngine.S2
                except Exception as ex:
                    txt = f'例外により音声認識に失敗しました。 {type(ex).__name__}:{ex}'
                    confidence = 0.0
                    if self.networkerror:
                        stat = -1
                    else:
                        self.networkerror = True
                        stat=SttEngine.S2
                #print(f"[google] {self.textbuffer}")
                if stat==SttEngine.S2:
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
                stat=SttEngine.S3
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
                    t = Thread( target=self._save_th, args=(self._save_buffer,self._save_pos),name='wave_save')
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
            dt=datetime.datetime.now()
            wave_filename = dt.strftime('sound_%Y%m%d_%H%M%S.wav')
            wave_path = os.path.join( 'logs', 'wave', wave_filename )
            logger.debug( f'save buffer to {wave_path}')
            os.makedirs( os.path.dirname(wave_path), exist_ok=True )
            audio_to_wave( wave_path, audio_data, samplerate=self.samplerate )
        except:
            logger.exception('can not save wave file')