import os,sys,traceback
from threading import Thread, Condition
import sounddevice as sd

from .VoiceSplitter import VoiceSplitter
from .Recognizer import RecognizerGoogle
from urllib.error import URLError, HTTPError

# 録音機能のクラス
class SttEngine:
    def __init__(self, *, callback=None, samplerate=16000, channels=1):
        self._callback = callback
        self.all_dev_list = sd.query_devices()
        self.inp_dev_list = [ device for device in self.all_dev_list if device['max_input_channels']>0 ]
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
                print( f"[VoiceRecognizer] success to set pause {b}")
            else:
                print( f"[VoiceRecognizer] failled to set pause {b}")

    def select_input_device(self):
        try:
            if self.input_device is None:
                self.input_device = next((x['index'] for x in self.inp_dev_list if "default" in x['name'].lower()), self.inp_dev_list[0]['index'])
            if self.input_device is not None:
                self.input_device_info = sd.query_devices( self.input_device, 'input' )
            else:
                self.input_device_info = None
        except Exception as err:
            traceback.print_exc()

    def start_recording(self):
        try:
            self.select_input_device()
            self.recording = True
            thread = Thread(target=self._th_record)
            thread.start()
        except Exception as err:
            traceback.print_exc()
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
            traceback.print_exc()

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
        if self._pause or self.splitter is None:
            return
        try:
            if self.recording and self.splitter is not None:
                # 配列から長さ1の次元を削除
                arr_squeezed = indata.squeeze()
                self.splitter.add_to_buffer(arr_squeezed)
        except Exception as err:
            self.recording=False
            print(f"[callback]exception")
            traceback.print_exc()

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
                timeout=1.0
                retry = 3
                try:
                    txt,confidence = self.recognizer.recognizef( buf, timeout=timeout, retry=retry, sample_rate=samplerate )
                    self.networkerror = False
                    if txt is None or confidence is None:
                        txt = '音声認識の結果が不明瞭'
                        confidence = 0.0
                    stat=2
                except (URLError,HTTPError) as ex:
                    txt = f'通信エラーにより音声認識に失敗しました {type(ex).__name__}:{ex.reason}'
                    confidence = 0.0
                    if self.networkerror:
                        stat = -1
                    else:
                        self.networkerror = True
                        stat=2
                except Exception as ex:
                    txt = f'例外により音声認識に失敗しました。 {type(ex).__name__}:{ex.reason}'
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
                confs = self.text_confidence
                stat=3
                self.text_list = []
                self.text_confidence = 1.0
            if stat>0 and self._callback is not None:
                self._callback( start_sec, end_sec, stat, texts, confs )

        except Exception as err:
            self.recording=False
            print(f"[callback]exception")
            traceback.print_exc()
