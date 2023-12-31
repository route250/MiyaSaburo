import traceback
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
import pyworld as pw
import librosa

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
        self.playing:bool = False
        self.data:np.ndarray = None
        self.frx:np.ndarray = None
        self.duration:int = 60
        self.data_pos:int = 0
        self.data_gain:float = 1.0

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
            thread = threading.Thread(target=self._th_record)
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
            self.channels=1
            rec_max = self.duration * self.samplerate
            self.data_pos = 0
            self.data = np.zeros((rec_max, self.channels), dtype=np.float32)
            with sd.InputStream( samplerate=self.samplerate, blocksize=8000, device=self.input_device, channels=self.channels, callback=self._fn_audio_callback ):
                while self.recording:
                    sd.sleep( 1000 )
                    print(f"len:{self.data_pos}/{len(self.data)}")
                    np.max( np.abs( self.data ) )
            self.data = self.data[:self.data_pos]
            min,max = self.get_min_max()
            self.data_gain = 1.0
            if max<0.6:
                self.data_gain = 0.6/max
                self.data = self.data * self.data_gain
            print(f"loaded min:{min} max:{max} gain:{self.data_gain}")

        except Exception as err:
            traceback.print_exc()
        finally:
            self.recording = False
            print(f"[record]finally")

    def get_min_max(self):
        min = np.min( np.abs(self.data) )
        max = np.max( np.abs(self.data) )
        return min,max

    def calculate_f0(self, frame_period=5.0):
        """ F0（基本周波数）を計算する """
        mono = self.data[:,0]
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
        mono = self.data[:,0].astype(np.float64)
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
                next_pos = self.data_pos + in_length
                if next_pos < len(self.data):
                    self.data[self.data_pos:next_pos] = indata
                    self.data_pos = next_pos
                else:
                    print(f"[callback]over {in_length} {next_pos} {len(self.data)}")
                    self.recording=False
        except Exception as err:
            self.recording=False
            print(f"[callback]exception")
            traceback.print_exc()

    def stop_recording(self):
        self.recording = False

    def save_recording(self, filename):
        try:
            if self.data is not None:
                with wave.open(filename, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)
                    wf.setframerate(self.samplerate)
                    wf.writeframes((self.data * 32767).astype(np.int16).tobytes())
        except Exception as err:
            traceback.print_exc()
        finally:
            self.playing = False

    def play_recording(self):
        try:
            if self.data is not None and not self.playing and not self.recording:
                self.playing = True
                thread = threading.Thread(target=self._th_play)
                thread.start()
        except Exception as err:
            traceback.print_exc()
        finally:
            self.playing = False

    def _th_play(self):
        try:
            if self.data is not None:
                self.playing = True
                sd.play(self.data, self.samplerate)
                sd.wait(ignore_errors=False)
        except Exception as err:
            traceback.print_exc()
        finally:
            print(f"[_th_play]finally")
            self.playing = False

    def stop_playback(self):
        try:
            if self.playing:
                sd.stop(ignore_errors=False)
        except Exception as err:
            traceback.print_exc()

    def amplify_audio(self, gain):
        """
        録音データの音量を増幅する
        :param data: NumPy 配列としてのオーディオデータ
        :param gain: 適用するゲイン（増幅係数）
        :return: 音量が増幅されたオーディオデータ
        """
        amplified_data = self.data * gain
        # クリッピング: 音量を -1.0 から 1.0 の範囲に保つ
        np.clip(amplified_data, -1.0, 1.0, out=amplified_data)
        self.data = amplified_data

# GUIのクラス
class RecordingApp:
    def __init__(self, root):
        self.root = root
        self.recorder = Recorder()
        self.setup_ui()

    def setup_ui(self):
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

        # グラフ表示用のフレームを作成
        self.graph_frame = ttk.Frame(self.root)
        self.graph_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        fig, (ax1,axB) = plt.subplots( 2,1, figsize=(10, 8))
        self.fig = fig
        self.ax1 = ax1
        self.ax2 = self.ax1.twinx()
        self.ax3 = self.ax1.twinx()
        self.axB = axB

        # グラフをTkinterウィンドウに埋め込む
        self.canvas = FigureCanvasTkAgg(fig, master=self.graph_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)


    def start_recording(self):
        self.recorder.start_recording()

    def stop_recording(self):
        self.recorder.stop_recording()

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
            with wave.open(filename, 'rb') as wf:
                self.recorder.samplerate = int(wf.getframerate())
                self.recorder.channels = int(wf.getnchannels())
                frames = wf.readframes(wf.getnframes())
                self.recorder.data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767
                self.recorder.data = self.recorder.data.reshape(-1, self.recorder.channels)
                self.recorder.data_gain = 1.0
                min,max = self.recorder.get_min_max()
                print(f"loaded min:{min} max:{max}")

    def plot_waveform(self):
        """ 録音されたデータの波形とF0をプロットする """

        self.ax1.clear()
        self.ax2.clear()
        self.ax3.clear()

        self.ax1.set_xlabel('Time (s)')
        self.ax1.set_ylabel('Amplitude', color='b')
        self.ax1.tick_params('y', colors='b')
        self.ax1.set_ylim(-1,1)

        self.ax2.set_ylabel('Frequency (Hz)', color='r')
        self.ax2.tick_params('y', colors='r')

        self.ax3.spines['right'].set_position(('outward', 40))  # Y軸の位置を調整
        self.ax3.set_ylabel('Coefficients', color='g')
        self.ax3.tick_params('y', colors='g')
        self.ax3.set_ylim(0,1)

        if self.recorder.data is not None and len(self.recorder.data) > 0:
            # 波形をプロット
            waveform = self.recorder.data[:, 0] if self.recorder.channels > 1 else self.recorder.data
            times = np.arange(len(waveform)) / float(self.recorder.samplerate)
            self.ax1.plot(times, waveform, label='Waveform', color='b')

            # F0を計算し、プロット（別のY軸を使用）
            f0, t = self.recorder.calculate_f0()
            self.ax2.plot(t, f0, label='F0', color='r')

            # 係数をプロット（さらに別のY軸を使用）
            f0r = self.recorder.calculate_f0rate()
            # ここに係数のデータをプロットするコードを追加
            self.ax3.plot(times, f0r, label='Coefficients', color='g')

            # MFCCを計算し、プロット
            # この部分は実際のMFCCデータに合わせて調整してください
            # 例: mfccs = librosa.feature.mfcc(waveform, sr=self.recorder.samplerate)
            hop_length = 512
            ff = self.recorder.data[:,0].astype(np.float64)
            mfccs = librosa.feature.mfcc(y=ff, sr=self.recorder.samplerate, hop_length=hop_length)
            # MFCCの各フレームの時間を計算
            mfcc_times = librosa.frames_to_time(np.arange(mfccs.shape[1]), sr=self.recorder.samplerate, hop_length=hop_length)
            img = self.axB.imshow(mfccs, aspect='auto', origin='lower', extent=[mfcc_times.min(), mfcc_times.max(), 0, mfccs.shape[0]])
            self.axB.set_ylabel('MFCC')
            self.axB.set_xlabel('Time (s)')
            #self.fig.colorbar(img,ax=self.axB)

            # グラフをTkinterウィンドウに埋め込む
            #canvas = FigureCanvasTkAgg(fig, master=self.graph_frame)
            self.canvas.draw()
            #canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        else:
            print("No data to plot.")


# メインアプリケーションの実行
def main():
    root = tk.Tk()
    app = RecordingApp(root)
    root.mainloop()
    print(f"[main]exit")
# アプリケーションを実行
main()
