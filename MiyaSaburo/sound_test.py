import math
import traceback
from queue import Queue, Empty
import time
import tkinter as tk
from tkinter import filedialog
import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sounddevice as sd
import numpy as np
import threading
import wave
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import pyworld as pw
import librosa
import vosk
from vosk import Model, KaldiRecognizer
from DxBotUtils import RecognizerEngine
import math
import json

vosk.SetLogLevel(-1)

# 録音機能のクラス
class Recorder:
    def __init__(self, samplerate=16000, channels=1, duration=60):
        self.all_dev_list = sd.query_devices()
        self.inp_dev_list = [ device for device in self.all_dev_list if device['max_input_channels']>0 ]
        self.input_device = None
        self.input_device_info = None
        self.samplerate:int = samplerate
        self.channels:int = channels
        self.duratio:int = duration
        self.recording:bool = False
        self.frx:np.ndarray = None
        self.duration:int = 60

        self.wave_buf:np.ndarray = None
        self.wave_pos:int = 0
        self.data_gain:float = 1.0

        self.play_reset()
        self.model_lang = None
        self.model_spk = None
        self.vosk = None

    def play_reset(self):
        self.stop_playback()
        self.play_pos = -1
        self.play_time = -1.0

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
                print(f"loaded rate:{self.samplerate} ch:{self.channels} min:{min} max:{max}")

    def start_recording(self):
        try:
            self.select_input_device()
            self.recording = True
            thread = threading.Thread(target=self._th_record)
            thread.start()
        except Exception as err:
            traceback.print_exc()
            self.recording = False
        finally:
            pass

    def _th_record(self):
        try:
            self.play_reset()
            self.select_input_device()
            if self.input_device_info is None:
                return
            self.samplerate=int(self.input_device_info['default_samplerate'])
            self.channels=1
            rec_max = self.duration * self.samplerate
            self.wave_pos = 0
            self.wave_buf = np.zeros((rec_max, self.channels), dtype=np.float32)
            with sd.InputStream( samplerate=self.samplerate, blocksize=8000, device=self.input_device, channels=self.channels, callback=self._fn_audio_callback ):
                while self.recording:
                    sd.sleep( 1000 )
                    print(f"len:{self.wave_pos}/{len(self.wave_buf)}")
                    np.max( np.abs( self.wave_buf ) )
            self.wave_buf = self.wave_buf[:self.wave_pos]
            min,max = self.get_min_max()
            self.data_gain = 1.0
            if max<0.6:
                self.data_gain = 0.6/max
                self.wave_buf = self.wave_buf * self.data_gain
            print(f"loaded min:{min} max:{max} gain:{self.data_gain}")

        except Exception as err:
            traceback.print_exc()
        finally:
            self.recording = False
            print(f"[record]finally")

    def get_min_max(self):
        min = np.min( np.abs(self.wave_buf) )
        max = np.max( np.abs(self.wave_buf) )
        return min,max

    def calculate_f0(self, frame_period=5.0):
        """ F0（基本周波数）を計算する """
        mono = self.wave_buf[:,0]
        mono_float = mono.astype(np.float64)
        _f0, t = pw.dio(mono_float, self.samplerate, frame_period=frame_period)
        f0 = pw.stonemask(mono_float, _f0, t, self.samplerate)
        return f0, t

    # F0をカウントして有声無声判定
    # https://blog.shinonome.io/voice-recog-random/
    # https://qiita.com/zukky_rikugame/items/dea51c60bfb984d39029
    def _f0_ratio( self, wave_float64, sr ) ->float:
        _f0, t = pw.dio(wave_float64, sr, frame_period=1) 
        f0 = pw.stonemask(wave_float64, _f0, t, sr)
        f0_vuv = f0[f0 > 0] # 有声・無声フラグ
        vuv_ratio = len(f0_vuv)/len(f0) # 有声部分の割合
        return vuv_ratio

    def calculate_f0rate( self ):
        mono = self.wave_buf[:,0].astype(np.float64)
        block_size = 8000
        data_len = len( mono )
        f0_rate_array = np.zeros( data_len )
        for idx in range( 0, data_len, block_size):
            end = idx + block_size
            rate = self._f0_ratio( mono[idx:end], self.samplerate )
            f0_rate_array[ idx:end] = rate
        return f0_rate_array

    def _fn_audio_callback(self, indata, frames, time, status):
        try:
            if self.recording:
                in_length = len(indata)
                next_pos = self.wave_pos + in_length
                if next_pos < len(self.wave_buf):
                    self.wave_buf[self.wave_pos:next_pos] = indata
                    self.wave_pos = next_pos
                else:
                    print(f"[callback]over {in_length} {next_pos} {len(self.wave_buf)}")
                    self.recording=False
        except Exception as err:
            self.recording=False
            print(f"[callback]exception")
            traceback.print_exc()

    def stop_recording(self):
        self.recording = False

    def save_recording(self, filename):
        try:
            if self.wave_buf is not None:
                with wave.open(filename, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)
                    wf.setframerate(self.samplerate)
                    wf.writeframes((self.wave_buf * 32767).astype(np.int16).tobytes())
        except Exception as err:
            traceback.print_exc()
        finally:
            self.playing = False

    def play_recordissng(self):
        try:
            if self.wave_buf is not None and not self.playing and not self.recording:
                self.playing = True
                thread = threading.Thread(target=self._th_play)
                thread.start()
        except Exception as err:
            traceback.print_exc()
        finally:
            self.playing = False

    def set_play_position(self,time):
        pos = int( self.samplerate * time )
        if pos < 0:
            pos = 0
        elif len(self.wave_buf)<=pos:
            pos = len(self.wave_buf)-1
        tm = pos / self.samplerate
        #print(f"set {time:.3f} {pos} {tm:.3f}")
        self.play_pos = pos
        self.play_time = tm

    def play_recording(self):
        try:
            if self.wave_buf is not None and not self.playing:
                self.playing = True
                blksz = self.samplerate // 10
                if self.play_pos<0 or len(self.wave_buf)<=self.play_pos:
                    self.play_pos = 0
                    self.play_time = 0.0
                self.play_stream = sd.OutputStream(samplerate=self.samplerate, channels=self.channels, blocksize=blksz, callback=self._audio_play_callback)
                self.play_stream.start()
        except Exception as err:
            traceback.print_exc()
            self.stop_playback()

    def _audio_play_callback(self, outdata, frames, time, status):
        try:
            if status:
                print(status)
            outdata.fill(0)
            ln = len(self.wave_buf)
            if self.playing and 0<=self.play_pos and self.play_pos<ln:
                sz = len(outdata)
                next_pos = min( ln, self.play_pos + sz)
                fn = next_pos - self.play_pos
                # print( f"buff {sz} fr:{frames} time:{time} {self.play_pos} - {next_pos} / {ln}")
                outdata[:fn] = self.wave_buf[self.play_pos:next_pos]
                self.play_pos = next_pos
                self.play_time = next_pos / self.samplerate
            else:
                print(f"callback stop {self.playing} {self.play_pos} {ln}")
                outdata.fill(0)
                raise sd.CallbackStop
        except sd.CallbackStop as ex:
            self.stop_playback()
            raise ex
        except Exception as ex:
            traceback.print_exc()
            self.stop_playback()
            raise ex

    def stop_playback(self):
        try:
            self.playing = False
            if self.play_stream is not None:
                self.play_stream.close()
        except Exception:
                pass
        finally:
            self.playing = False
            self.play_stream = None

    def aplay_time(self):
        try:
            if self.play_stream is not None:
                t = self.play_stream.time
                return t
        except:
            pass
        return -1.0

    def amplify_audio(self, gain):
        """
        録音データの音量を増幅する
        :param data: NumPy 配列としてのオーディオデータ
        :param gain: 適用するゲイン（増幅係数）
        :return: 音量が増幅されたオーディオデータ
        """
        amplified_data = self.wave_buf * gain
        # クリッピング: 音量を -1.0 から 1.0 の範囲に保つ
        np.clip(amplified_data, -1.0, 1.0, out=amplified_data)
        self.wave_buf = amplified_data

    def fn_vosk01(self):
        try:
            # voskの設定
            if self.model_lang is None:
                self.model_lang = RecognizerEngine.get_vosk_model(lang="ja")
            else:
                self.model_lang = Model(lang=self.model_lang)
            self.vosk: KaldiRecognizer = KaldiRecognizer(self.model_lang, self.samplerate)
           # self.vosk.SetWords(True)
            spkmodel_path = RecognizerEngine.get_vosk_spk_model(self.model_lang)
            if spkmodel_path is not None:
                self.vosk.SetSpkModel( spkmodel_path )
            mono = self.wave_buf[:,0] * 32767.0
            mono16 = mono.astype(np.int16)
            slen = len(mono16)
            seg_size = int(self.samplerate * 0.02) # 0.2秒
            audio_sec = len(mono16) / self.samplerate
            vst = time.time()
            res_list = []
            for idx in range( 0, slen, seg_size ):
                fr=int(idx/seg_size)
                seg = mono16[idx:idx+seg_size]
                b = seg.tobytes()
                if self.vosk.AcceptWaveform( b ):
                    res = json.loads(self.vosk.Result())
                    res['fr'] = fr
                    res['idx'] = idx
                    res_list.append( res )
            res = json.loads(self.vosk.FinalResult())
            res['fr'] = int(slen/seg_size)
            res['idx'] = slen
            res_list.append( res )
            vet = time.time()
            vosk_sec = (vet-vst)
            with open('dbgvosk_output.json','w') as out:
                json.dump( res_list, out, ensure_ascii=False, indent=4 )
            print(f"audio: {audio_sec:.3f}(sec) vosk:{vosk_sec:.3f}(sec)")
        except:
            traceback.print_exc()

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

    def fn_vosk(self):
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
            with open('dbgvosk_output2.json','w') as out:
                json.dump( res_list, out, ensure_ascii=False, indent=4 )
            print(f"audio: {audio_sec:.3f}(sec) vosk:{vosk_sec:.3f}(sec)")
        except:
            traceback.print_exc()

# GUIのクラス
class RecordingApp:
    def __init__(self, root:tk.Tk):
        self.root:tk.Tk = root
        self.recorder = Recorder()
        self.setup_ui()
        self.play_line = None
        self.play_line_time = -1

        # ウィンドウを閉じた際にPythonを終了する
    def close_window(self):
        self.root.destroy()
        self.root.quit()
    
    def setup_ui(self):

        # ウィンドウを閉じるイベントの設定
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        # タイトル
        self.root.title("Audio Recorder")

        # コントロール用のフレームを作成
        control_frame = ttk.Frame(self.root)
        control_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ボタンの配置
        self.record_button = tk.Button(control_frame, text="Record", command=self.start_recording)
        self.record_button.pack()

        self.stop_button = tk.Button(control_frame, text="Stop", command=self.stop_recording)
        self.stop_button.pack()

        self.play_button = tk.Button(control_frame, text="Play", command=self.play_recording)
        self.play_button.pack()

        self.stop_play_button = tk.Button(control_frame, text="Stop", command=self.stop_playback)
        self.stop_play_button.pack()

        self.save_button = tk.Button(control_frame, text="Save", command=self.save_recording)
        self.save_button.pack()

        self.load_button = tk.Button(control_frame, text="Load", command=self.load_recording)
        self.load_button.pack()

        self.plot_button = tk.Button(control_frame, text="Plot Waveform", command=self.plot_waveform)
        self.plot_button.pack()

        self.plot_button = tk.Button(control_frame, text="vosk", command=self.fn_vosk)
        self.plot_button.pack()

        # グラフ表示用のフレームを作成
        self.pos_frame = ttk.Frame(self.root)
        self.pos_frame.pack(side=tk.TOP, fill=tk.X, expand=True)
        self.pos_start = ttk.Entry(self.pos_frame)
        self.pos_start.pack(side=tk.LEFT)
        self.pos_end = ttk.Entry(self.pos_frame)
        self.pos_end.pack(side=tk.LEFT)
        self.pos_current = ttk.Entry(self.pos_frame)
        self.pos_current.pack(side=tk.LEFT)

        # グラフ表示用のフレームを作成
        self.graph_frame = ttk.Frame(self.root)
        self.graph_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        fig, (axA1,axB) = plt.subplots( 2,1, figsize=(10, 8))
        self.fig = fig
        self.axA1 = axA1
        self.axA2 = self.axA1.twinx()
        self.axA3 = self.axA1.twinx()
        self.axB = axB

        # グラフをTkinterウィンドウに埋め込む
        self.canvas = FigureCanvasTkAgg(fig, master=self.graph_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # マウスイベント
        self.canvas.mpl_connect('button_press_event', self.on_click)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.canvas.mpl_connect('button_release_event', self.on_release)
        self.dragging = False

    def on_click(self, event):
        # 線の近くでマウスがクリックされたかチェック
        on_axes = event.inaxes == self.axA1 or event.inaxes == self.axA2 or event.inaxes == self.axA3
        if on_axes:
            xdata = self.play_line.get_xdata() if self.play_line is not None else None
            if xdata is None or len(xdata)==0:
                self.recorder.set_play_position(event.xdata)
                self.dragging = True
            elif abs(event.xdata-xdata[0])<0.1:
                self.dragging = True

    def on_motion(self, event):
        # ドラッグ中に線を移動
        if self.dragging and event.xdata:
            self.recorder.set_play_position(event.xdata)

    def on_release(self, event):
        # マウスのリリースでドラッグ終了
        if self.dragging:
            self.dragging = False
            # 再生位置の更新
            if event.xdata:
                self.recorder.set_play_position(event.xdata)

    def start_recording(self):
        self.recorder.start_recording()

    def stop_recording(self):
        self.recorder.stop_recording()
        self.plot_waveform(False)

    def play_recording(self):
        thread = threading.Thread(target=self.recorder.play_recording)
        thread.start()

    def stop_playback(self):
        self.recorder.stop_playback()

    def save_recording(self):
        filename = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=[("WAV files", "*.wav")])
        if filename:
            self.recorder.save_recording(filename)

    def load_recording(self):
        filename = filedialog.askopenfilename(filetypes=[("WAV files", "*.wav")])
        if filename:
            self.recorder.load_recording(filename)
            self.plot_waveform(False)

    def fn_init_anim(self):
        # アニメーションの初期化に必要な処理
        self.play_line.set_data([], [])
        return self.play_line,

    def fn_animate(self, i):
        # アニメーションの各フレームでの更新処理
        current_time = self.recorder.play_time
        if self.play_line_time != current_time:
            self.pos_start.delete(0,tk.END)
            self.pos_end.delete(0,tk.END)

            if current_time>=0:
                self.play_line.set_data([current_time, current_time], [self.axA1.get_ylim()])
                self.pos_start.insert(0,f"{current_time:.3f}")
                self.pos_end.insert(0,str(self.recorder.play_pos))
            else:
                self.play_line.set_data([], [])
        return self.play_line,

    def plot_waveform(self, full=True):
        """ 録音されたデータの波形とF0をプロットする """

        self.axA1.clear()
        self.axA2.clear()
        self.axA3.clear()
        self.axB.clear()

        self.axA1.set_xlabel('Time (s)')
        self.axA1.set_ylabel('Amplitude', color='b')
        self.axA1.tick_params('y', colors='b')
        self.axA1.set_ylim(-1,1)

        self.axA2.set_ylabel('Frequency (Hz)', color='r')
        self.axA2.tick_params('y', colors='r')

        self.axA3.spines['right'].set_position(('outward', 40))  # Y軸の位置を調整
        self.axA3.set_ylabel('Coefficients', color='g')
        self.axA3.tick_params('y', colors='g')
        self.axA3.set_ylim(0,1)

        if self.recorder.wave_buf is not None and len(self.recorder.wave_buf) > 0:
            # 波形をプロット
            waveform = self.recorder.wave_buf[:, 0] if self.recorder.channels > 1 else self.recorder.wave_buf
            times = np.arange(len(waveform)) / float(self.recorder.samplerate)
            self.axA1.plot(times, waveform, label='Waveform', color='b')

            # 再生位置を示す線の初期化
            self.play_line, = self.axA1.plot([], [], 'r', linewidth=2)  # 初期化（空の線）
            # FuncAnimationの設定
            self.anim = FuncAnimation(self.fig, self.fn_animate, init_func=self.fn_init_anim, blit=True, cache_frame_data=False )

            if full:
                # F0を計算し、プロット（別のY軸を使用）
                f0, t = self.recorder.calculate_f0()
                self.axA2.plot(t, f0, label='F0', color='r')

                # 係数をプロット（さらに別のY軸を使用）
                f0r = self.recorder.calculate_f0rate()
                # ここに係数のデータをプロットするコードを追加
                self.axA3.plot(times, f0r, label='Coefficients', color='g')

                # MFCCを計算し、プロット
                # この部分は実際のMFCCデータに合わせて調整してください
                # 例: mfccs = librosa.feature.mfcc(waveform, sr=self.recorder.samplerate)
                hop_length = 512
                ff = self.recorder.wave_buf[:,0].astype(np.float64)
                mfccs = librosa.feature.mfcc(y=ff, sr=self.recorder.samplerate, hop_length=hop_length)
                # MFCCの各フレームの時間を計算
                mfcc_times = librosa.frames_to_time(np.arange(mfccs.shape[1]), sr=self.recorder.samplerate, hop_length=hop_length)
                img = self.axB.imshow(mfccs, aspect='auto', origin='lower', extent=[mfcc_times.min(), mfcc_times.max(), 0, mfccs.shape[0]])
                self.axB.set_ylabel('MFCC')
                self.axB.set_xlabel('Time (s)')
                #self.fig.colorbar(img,ax=self.axB)
        else:
            print("No data to plot.")
        self.canvas.draw()
    
    def fn_vosk(self):
        self.recorder.fn_vosk()

# メインアプリケーションの実行
def main():
    root = tk.Tk()
    app = RecordingApp(root)
    root.mainloop()
    print(f"[main]exit")
# アプリケーションを実行
main()

# はい、すいません
# どちらまで
# あのー、なんばグランド花月まで
# なんばグランド花月？　あーそうですか、千日前の？
# はい？
# 千日前の？
# 千日前、はい
# そうですよね
