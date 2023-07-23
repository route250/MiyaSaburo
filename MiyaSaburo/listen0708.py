from typing import Type
import sys
import traceback
import os
from datetime import datetime, timezone
from io import BytesIO
import ctypes
import math
import datetime
import tempfile
import threading
import asyncio
import re
from queue import Queue
import queue
from langchain import LLMMathChain
import pyaudio
import speech_recognition as sr

import tkinter as tk
from tkinter import ttk as ttk
from tkinter import scrolledtext
import time
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from libs.VoiceAPI import VoiceAPI
from tools.QuietTool import QuietTool
from tools.webSearchTool import WebSearchTool
from tools.task_tool import TaskCmd, AITask, AITaskRepo, AITaskTool
from libs.StrList import StrList

import openai
from langchain.chains.conversation.memory import ConversationBufferMemory,ConversationBufferWindowMemory,ConversationSummaryBufferMemory
from langchain.memory import ConversationTokenBufferMemory
from langchain.prompts import MessagesPlaceholder
from langchain.chat_models import ChatOpenAI
from langchain.agents.agent_types import AgentType
from langchain.agents import initialize_agent, Tool, load_tools
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.schema import SystemMessage
from langchain.schema import BaseMessage, BaseChatMessageHistory
from libs.CustomChatMessageHistory import CustomChatMessageHistory
# 再生関係
import pygame
import wave

class ModuleState:
    def __init__(self,title):
        self.title = title
        self.__enable = False
        self.__running = False
        self.__error = False
        self.callback=None
    def get_enable(self):
        return self.__enable
    def set_enable(self,state):
        global running
        if state != self.__enable:
            self.__enable = state
            if running and self.callback is not None:
                self.callback(self)
    def get_running(self):
        return self.__running
    def set_running(self,state):
        global running
        if state != self.__running:
            self.__running = state
            if running and self.callback is not None:
                self.callback(self)
    def get_error(self):
        return self.__error
    def set_error(self,state):
        global running
        if state != self.__error:
            self.__error = state
            if running and self.callback is not None:
                self.callback(self)

class AppModel(threading.Thread):
    LANG_LIST =['ja_JP','en_US','en_GB','fr_FR']
    INTERRUPT_LIST = ['any','keyword']
    AUDIO_ENERGY_TRIGGER = 800
    AUDIO_ENERGY_LO = 500
    AUDIO_ENERGY_CUT = 400
    AUDIO_CROSS_TRIGGER = 800
    AUDIO_CROSS_LO = 500
    AUDIO_CORSS_CUT = 400
    SHOT_BLANK = "<SB>"
    LONG_BLANK = "<LB>"

    def __init__(self):
        super().__init__(daemon=True)
        # マイクのリストを取得
        self.microphone_list = find_available_microphones()
        self.microphone_index = self.microphone_list[0][1]
        self.audio_state = ModuleState('AUDIO')
        self.recog_state = ModuleState('RECOG')
        self.llm_state = ModuleState('LLM')
        self.wave_state = ModuleState('WAVE')
        self.talk_state = ModuleState('TALK')
        self.voice_api = VoiceAPI()
        self.lang_in = AppModel.LANG_LIST[0]
        self.lang_out = AppModel.LANG_LIST[0]
        self.interrupt_mode = AppModel.INTERRUPT_LIST[0]
        self.sound1 = create_sound(440,0.3)
        self.sound2 = create_sound(220,0.3)

        self.plot_audio_data = None
        self.plot_energy_data = None
        self.plot_cross_data = None

        # counter
        self.__count = 0
        self.talk_id = 0
        self.play_talk_id = 0

        self.energy_hist = value_hist(5)
        self.cross_hist = value_hist(5)

        self.recog_energy = 0
        self.recog_min_energy = 0
        self.recog_limit_energy = 0
        self.recog_buffer : StrList = StrList()
        self.recog_detect : StrList = StrList()

        self.cross_on_rate = 3
        self.energy_up_rate =3
        self.energy_dn_rate = 0.4

    def run(self):
        try:
            global Model, App
            global running
            global quiet_timer
            quiet_timer = None
            Model.play_talk_id = 0

            default_mic = Model.getMic()
            if default_mic is None:
                return
            print(f"選択されたマイク: {default_mic[0]}, デバイスインデックス: {default_mic[1]}")

            running = True
            threads = [
                threading.Thread(target=recoard_audio),
                threading.Thread(target=process_audio2),
                threading.Thread(target=plot_audio),
                threading.Thread(target=LLM_process),
                threading.Thread(target=wave_process),
                threading.Thread(target=talk_process),
            ]
            for thread in threads:
                thread.setDaemon(True)
                thread.start()
            i=0
            while running and App:
                if i==0:
                    App.set_ydata(self.plot_audio_data,self.plot_energy_data,self.plot_cross_data)
                App.audio_level_1.config(text=f"last:{self.energy_hist.last:4d} / {self.cross_hist.last:4d}")
                App.audio_level_4.config(text=f" min:{self.energy_hist.min:4d} / {self.cross_hist.min:4d}")
                App.audio_level_2.config(text=f"ave.:{self.energy_hist.ave:4d} / {self.cross_hist.ave:4d}")
                App.audio_level_3.config(text=f" max:{self.energy_hist.max:4d} / {self.cross_hist.max:4d}")

                App.recog_fail_energy.config(text=f"fail:{self.recog_energy}")
                App.recog_min_energy.config(text=f"success:{self.recog_min_energy}")
                App.recog_limit_energy.config(text=f"low:{self.recog_limit_energy}")

                if self.recog_buffer.is_update():
                    App.recog_buffer.delete(1.0,tk.END)
                    App.recog_buffer.insert(tk.END,self.recog_buffer.get_all("\n"))
                if self.recog_detect.is_update():
                    App.recog_detect.delete(1.0,tk.END)
                    App.recog_detect.insert(tk.END,self.recog_detect.get_all("\n"))

                time.sleep(0.2)
                i = (i+1) % 3

            print("[Thread]waiting...")
            for thread in threads:
                thread.join(timeout=0.2)
            print("[Thread]stopped")
        except Exception as ex:
            traceback.print_exc()

    def next_id(self):
        i = self.__count
        self.__count += 1
        return i
    
    def set_microphone_index(self,idx):
        self.microphone_index=idx

    def get_microphone_list(self):
        return self.microphone_list
    
    def getMic(self):
        if self.microphone_index is None:
            return None
        for mic in self.microphone_list:
            if mic[1] == self.microphone_index:
                return mic[0]
        return None


CHUNK = 1024  # バッファサイズ
FORMAT = pyaudio.paInt16  # オーディオフォーマット
CHANNELS = 1  # チャンネル数
RATE = 44100 #44100  # サンプルレート
WIDTH = 2
DELTA_TIME=0.1
REC_SIZE = int(RATE*DELTA_TIME)  # 録音時間（秒）
REC_BUFFER_SEC = 10
reduce_sz=2000
x_size = int(RATE*15/reduce_sz)
frame_queue = queue.Queue()
plot_queue = queue.Queue()
llm_queue = queue.Queue()
wave_queue = queue.Queue()
talk_queue = queue.Queue()

MARK_START="<Start>"
MARK_END="<End>"

## -----------------------------------------------------------------------
## Utils
## -----------------------------------------------------------------------
def formatted_datetime():
    # オペレーティングシステムのタイムゾーンを取得
    system_timezone = time.tzname[0]
    # 現在のローカル時刻を取得
    current_time = time.localtime()
    # 日時を指定されたフォーマットで表示
    formatted = time.strftime(f"%a %b %d %H:%M {system_timezone} %Y", current_time)
    return formatted

def bswap(barray):
    l=len(barray)
    i=0
    while i<l:
        b=barray[i]; barray[i]=barray[i+1]; barray[i+1] = b
        i+=2

def shift_set( array, value ):
    np.copyto( array[:-1], array[1:])
    array[-1] = value

# オーディオデータを10分の1に圧縮
def reduce_audio_data(src,dst):
    dst_len=len(dst)
    src_len=len(src)
    step=int(reduce_sz*2)
    n = int(src_len/step)*2
    np.copyto( dst[:-n], dst[n:])
    j = dst_len-n-2
    for i in range(0, src_len, step):
        chunk = src[i:i+step]
        dst[j] = np.max(chunk); j+=1
        dst[j] = np.min(chunk); j+=1

def find_available_microphones():
    """有効なマイクを取得"""
    print("[MIC]start")
    microphones = []
    try:
        p = pyaudio.PyAudio()
        info = p.get_host_api_info_by_index(0)
        num_devices = info.get('deviceCount')
        for i in range(num_devices):
            device_info = p.get_device_info_by_host_api_device_index(0, i)
            if device_info.get('maxInputChannels') > 0:
                name = device_info.get('name')
                index = device_info.get('index')
                microphones.append((name, index))
        p.terminate()
    except Exception as ex:
        traceback.print_exc()
    print("[MIC]end")
    return microphones

def create_soundxx(Hz1=440,time=0.3):
    arr_size = int(44100*time*2)
    x=np.linspace(0,arr_size,arr_size)
    y=np.sin(2*np.pi*Hz1/44100*x)*10000
    y=y.astype(np.int16)
    xtime=x/44100
    sound_arr = y.reshape(int(y.shape[0]/2), 2)
    pygame.mixer.init()
    sound = pygame.sndarray.make_sound(sound_arr)
    return sound

def create_sound(Hz1=440, time=0.3):
    #再生時間を指定
    #time=2
    #周波数を指定
    #Hz1=300
    #再生時間を設定
    arr_size = int(44100 * time * 2)
    x = np.linspace(0, arr_size, arr_size)
    y = np.sin(2 * np.pi * Hz1 / 44100 * x) * 10000
    y = y.astype(np.int16)
    xtime = x / 44100
    sound_arr = y.reshape(int(y.shape[0] / 2), 2)

    # wavファイルを作成してバイナリ形式で保存する
    wav_io = BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(2)  # ステレオ (左右チャンネル)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(44100)  # サンプリングレート
        wav_file.writeframes(sound_arr.tobytes())
    wav_io.seek(0)  # バッファの先頭にシーク
    return wav_io.read()

def split_string(text):
    # 文字列を改行で分割
    lines = text.split("\n")

    # 句読点で分割するための正規表現パターン
    pattern = r"(?<=[。．！？])"

    # 分割結果を格納するリスト
    result = []

    # 各行を句読点で分割し、結果をリストに追加
    for line in lines:
        sentences = re.split(pattern, line)
        result.extend(sentences)

    # 空の要素を削除して結果を返す
    return list(filter(None, result))

def _handle_error(error) -> str:
    return str(error)[:50]

def force_interrupt(target_thread: threading.Thread) -> bool:
    """
    Terminate thread using exception.

    This function attempts to forcefully terminate a thread by raising a specific exception in the thread's execution context.
    It uses low-level ctypes API to set the asynchronous exception in the target thread.
    If successful, the function waits for the target thread to join, allowing the exception to take effect and terminate the thread.
    If the thread termination is successful, it returns True. Otherwise, it returns False.

    Parameters:
    - target_thread (threading.Thread): The thread to be forcefully terminated.

    Returns:
    - bool: True if the thread was successfully terminated, False otherwise.
    """
    try:
        # Get the identifier of the target thread
        c_ident = ctypes.c_long(target_thread.ident)

        # Define the exception to be raised in the target thread
        c_except = ctypes.py_object(SystemExit)
        c_except = ctypes.py_object(KeyboardInterrupt)

        # Set the asynchronous exception in the target thread
        resu = ctypes.pythonapi.PyThreadState_SetAsyncExc(c_ident, c_except)

        if resu == 1:
            # Wait for the target thread to join, 
            # allowing the exception to take effect and terminate the thread
            target_thread.join()

            # Check if the target thread is no longer alive
            if not target_thread.is_alive():
                return True

        elif resu > 1:
            # Clear the asynchronous exception if setting it failed
            ctypes.pythonapi.PyThreadState_SetAsyncExc(c_ident, 0)
            print('Failure in raising exception')

        elif resu == 0:
            print('Failure in raising exception')

    except Exception as ex:
        traceback.print_exc()

    return False

## -----------------------------------------------------------------------
##  threads
## -----------------------------------------------------------------------
def recoard_audio():
    """録音スレッド"""
    global Model, App
    global running
    try:
        if Model.microphone_index is None:
            raise Exception("device_index is Nothing")
        while running:
            if Model.audio_state.get_enable():
                try:
                    print(f"[REC] start {Model.microphone_index} {FORMAT} {CHANNELS} {RATE} {REC_SIZE}")
                    audio = pyaudio.PyAudio()
                    stream = audio.open(input_device_index=Model.microphone_index,format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=REC_SIZE)
                    Model.audio_state.set_running(True)
                    while running and Model.audio_state.get_enable():
                        frames = stream.read(REC_SIZE)
                        frame_queue.put((Model.play_talk_id,frames))
                except Exception as ex:
                    Model.audio_state.set_error(True)
                    traceback.print_exc()
                finally:
                    if stream.is_active:
                        stream.stop_stream()
                    stream.close()
                    audio.terminate()
                    Model.audio_state.set_running(False)
            else:
                time.sleep(0.5)
    except Exception as ex:
        Model.audio_state.set_error(True)
        traceback.print_exc()
    finally:
        print("[rec_audio]exit")
        frame_queue.put(None)
        frame_queue.put(None)
        plot_queue.put(None)
        plot_queue.put(None)

def plot_audio():
    """波形プロット"""
    global Model, App
    global running
    try:
        audio_buffer = np.zeros(x_size)
        energy_buffer = np.zeros(x_size)
        corss_buffer = np.zeros(x_size)
        Model.plot_audio_data = audio_buffer
        plot_time = 0
        now = int(time.time()*1000)
        while running:
            if plot_queue.qsize()>0:
                item = plot_queue.get()
                if item is None:
                    break
                data, energy, cross = item
                audio_src = np.frombuffer(data, dtype=np.int16)
                del data, item
                src_len=len(audio_src)
                step=int(reduce_sz*2)
                n = int(src_len/step)*2
                np.copyto( audio_buffer[:-n], audio_buffer[n:])
                np.copyto( energy_buffer[:-n], energy_buffer[n:])
                np.copyto( corss_buffer[:-n], corss_buffer[n:])
                bs = x_size-n-2
                p=bs
                ss=0
                while ss<src_len:
                    se = ss+step
                    chunk = audio_src[ss:se]
                    audio_buffer[p] = np.max(chunk); p+=1
                    audio_buffer[p] = np.min(chunk); p+=1
                    ss = se
                energy_buffer[bs:p] = energy
                corss_buffer[bs:p] = cross
                #print(f"{len(data)} {len(audio_data)} {len(audio_data2)} {len(audio_buffer)}")
                Model.plot_audio_data = audio_buffer
                Model.plot_energy_data = energy_buffer
                Model.plot_cross_data = corss_buffer
            else:
                time.sleep(0.5)
    finally:
        print("[plot_audio]exit")
class Detect:
    def __init__(self):
        self.begin = 0
        self.end = 0
        self.end0 = 0
        self.text = ''
        self.count = 0
    def reset(self):
        self.begin = 0
        self.end = 0
        self.end0 = 0
        self.text = ''
        self.count = 0
    def shift(self,n):
        self.begin -= n
        self.end -= n
        self.end0 -= n
    def d_start(self,begin,end,text):
        self.begin = begin
        self.end0 = end
        self.end = end
        self.text = text
        self.count = 1
    def d_continue(self,end):
        self.end = end
        self.count += 1
    def d_end(self,buffer_len):
        self.begin = self.end0
        self.end = buffer_len
        self.end0 = buffer_len
        self.text = ''
        self.count = 0

class value_hist:
    def __init__(self,num):
        self.size = num
        self.clear()
    def clear(self) -> None:
        self.hist = np.zeros(self.size)
        self.last : int = 0
        self.ave : int = 0
        self.min : int = 0
        self.max : int = 0
    def add(self, value : int ):
        shift_set(self.hist,value)
        self.last = int( value )
        self.ave = int(np.mean(self.hist))
        self.max = int(np.max(self.hist))
        self.min = int(np.min(self.hist))
    def get(self,idx:int) -> int:
        return self.hist[idx]
    def argmin(self,start):
        return np.argmin(self.hist[start:])+start

def process_audio():
    """"""
    global Model, App
    global running
    try:
        try:
            recognizer = sr.Recognizer()
            buffer_len = RATE*WIDTH * REC_BUFFER_SEC
            buffer = bytearray( buffer_len )
            recognize_time = 0
            now = int(time.time()*1000)
            detect = Detect()
            pos = 0
            in_talk = 0
            next_talk = 0
            accept_count=2
            sended=False
            low_energy = 0
            item = None
            recog_hist = np.zeros(5)
            recog_limit_energy = AppModel.AUDIO_ENERGY_LO
            recog_limit_cross = AppModel.AUDIO_CROSS_LO
            in_count = 0
            while running:
                if item is None and frame_queue.qsize()>0:
                    item = frame_queue.get()
                    if item is None:
                        break
                if item is None:
                    time.sleep(0.1)
                    continue
                next_talk,data = item
                if in_talk == next_talk:
                    item = None
                    in_count += 1
                    barray = bytearray(data)
                    data_len=len(barray)
                    buffer[:-data_len] = buffer[data_len:]
                    buffer[-data_len:] = barray
                    pos -= data_len
                    detect.shift(data_len)
                    energy = sr.audioop.rms(barray, WIDTH)
                    Model.energy_hist.add(energy)
                    cross = sr.audioop.cross(barray, WIDTH)
                    Model.cross_hist.add(cross)
                    plot_queue.put( (data,energy,cross) )

                now = int(time.time()*1000)
                if in_talk == next_talk and (now-recognize_time)<500:
                    continue

                if True:
                    recognize_time = now
                    audio_energy = sr.audioop.rms(buffer[pos:], WIDTH) 
                    audio_corss = sr.audioop.cross(buffer[pos:], WIDTH )
                    limit1 = audio_energy> recog_limit_energy and audio_corss>recog_limit_cross
                    limit2 = audio_energy>AppModel.AUDIO_ENERGY_TRIGGER or audio_corss >AppModel.AUDIO_CROSS_TRIGGER
                    try:
                        if limit1 and limit2:
                            Model.recog_state.set_running(True)
                            audio_data = sr.AudioData( buffer[pos:], RATE, WIDTH)
                            raw_text, confidence = recognizer.recognize_google(audio_data, language=Model.lang_in, with_confidence=True)
                            #print(f"[REC] confidence {confidence}")
                            #actual_result = recognizer.recognize_google(audio_data, language="ja-JP", show_all=True)
                            #if not isinstance(actual_result, dict) or len(actual_result.get("alternative", [])) == 0:
                            #    raw_text = ''
                            #lse:
                            #    print(f"[REC] show_all {actual_result}")
                        else:
                            raw_text = ''
                            confidence = 0.0
                    except sr.UnknownValueError as ex:
                        raw_text = ''
                        confidence = 0.0
                    finally:
                        end_time = int(time.time()*1000)
                        t = end_time - now
                        Model.recog_state.set_running(False)

                    if raw_text == '':
                        Model.recog_energy = energy
                    else:
                        shift_set(recog_hist,audio_energy)
                        recog_min_energy = np.min(recog_hist)
                        Model.recog_min_energy = recog_min_energy
                        recog_limit_energy = int((recog_min_energy-AppModel.AUDIO_ENERGY_TRIGGER)*0.6)+AppModel.AUDIO_ENERGY_TRIGGER
                        Model.recog_limit_energy = recog_limit_energy

                    if raw_text == '':
                        if detect.text == '':
                            # 無音が続いている
                            Model.recog_buffer.clear()
                            detect.d_continue(buffer_len)
                            if detect.count >= accept_count:
                                #3回同じ内容が来た
                                pos = detect.end0
                                detect.d_end(buffer_len)
                                if sended:
                                    print(f"[REC] blank NL {in_talk},{detect.count}/{accept_count}")
                                    llm_queue.put((in_talk,"\n"))
                                    Model.recog_detect.clear()
                                    sended=False
                            #     else:
                            #         print(f"[REC] blank {detect.count}/{accept_count}")
                            # else:
                            #     print(f"[REC] blank {detect.count}/{accept_count}")
                        else:
                            # 無音区間が来た？
                            print("[REC] bl ---> {},{}".format(in_talk,detect.text))
                            llm_queue.put((in_talk,detect.text))
                            sended=True
                            Model.recog_buffer.clear()
                            Model.recog_detect.append(detect.text)
                            pos = detect.end
                            detect.d_end(buffer_len)
                            print("[REC]___")
                    else:
                        if detect.text == '':
                            # 初の検出
                            llm_queue.put((in_talk," "))
                            detect.d_start(pos,buffer_len,raw_text)
                            Model.recog_buffer.append(raw_text)
                            if confidence <0.95:
                                print("[REC]start {}".format(raw_text))
                            else:
                                print("[REC] 1st ---> {},{}".format(in_talk,detect.text))
                                llm_queue.put((in_talk,detect.text))
                                sended=True
                                Model.recog_buffer.clear()
                                Model.recog_detect.append(detect.text)
                                pos = detect.end
                                detect.d_end(buffer_len)
                        else:
                            # 2回目以降の検出
                            if detect.text == raw_text:
                                detect.count += 1
                                if detect.count < accept_count:
                                    print("[REC]{} {}".format(detect.count,raw_text))
                                    detect.d_continue(buffer_len)
                                    Model.recog_buffer.append(raw_text)
                                else:
                                    #3回同じ内容が来た
                                    print("[REC] eq ===> {} => {},{}".format(detect.count,in_talk,detect.text))
                                    llm_queue.put((in_talk,detect.text))
                                    sended=True
                                    Model.recog_buffer.clear()
                                    Model.recog_detect.append(detect.text)
                                    pos = detect.end0
                                    detect.d_end(buffer_len)
                            elif raw_text.startswith(detect.text):
                                # 先頭部分だけ一致した
                                print("[REC] st ===> {},{}".format(in_talk,detect.text))
                                llm_queue.put((in_talk,detect.text))
                                sended=True
                                raw_text = raw_text[len(detect.text):]
                                pos = detect.end0
                                detect.d_start(pos,buffer_len,raw_text)
                                print("[REC]split {}".format(raw_text))
                                Model.recog_buffer.append(raw_text)
                            elif pos<=0:
                                # 先頭部分だけ一致した
                                print("[REC] over ===> {},{}".format(in_talk,detect.text))
                                llm_queue.put((in_talk,detect.text))
                                sended=True
                                Model.recog_buffer.clear()
                                Model.recog_detect.append(detect.text)
                                pos = detect.end0
                                detect.d_end(buffer_len)
                            else:
                                # やりなおし？
                                print("[REC]reset {}".format(raw_text))
                                detect.d_start(pos,buffer_len,raw_text)
                                Model.recog_buffer.append(raw_text)

                if in_talk != next_talk:
                    if detect.text != '':
                        print("[REC] tk ===> {},{}".format(in_talk,detect.text))
                        llm_queue.put((in_talk,detect.text))
                        sended=True
                    if sended:
                        print("[REC] tk ===> \\nl")
                        llm_queue.put((in_talk,"\n"))
                        Model.recog_detect.clear()
                        sended=False
                    in_talk = next_talk
                    in_count = 0
                    Model.energy_hist.clear()
                    pos = buffer_len
                    detect.d_end(buffer_len)
        except Exception as ex:
            traceback.print_exc()
        finally:
            pass
    finally:
        print("[process_audio]exit")
        plot_queue.put(None)

def process_audio2():
    """"""
    global Model, App
    global running
    try:
        try:
            recognizer = sr.Recognizer()
            recognizer.operation_timeout=1.0
            buffer_len = RATE*WIDTH * REC_BUFFER_SEC
            array_size = REC_SIZE*WIDTH
            hist_len = int(buffer_len/array_size)+1
            buffer = bytearray( buffer_len )
            item = None
            xpos_start = hist_len+1
            xpos_end = xpos_start
            in_talk = 0
            energy_hist = value_hist(hist_len)
            cross_hist = value_hist(hist_len)
            lim_sec = 0
            aaaaa=0
            silent_count=0
            recog_text=''
            energy_lo_ave = 30000
            energy_lo_th = 30000
            energy_hi_ave = 60000
            energy_hi_th = 60000
            cross_on = 350
            cross_off = 350
            fail_count = 0
            network_error = 0
            while running:
                data = None
                try:
                    item = frame_queue.get(block=True,timeout=0.5)
                    if item is None:
                        break
                    next_talk, data = item
                except:
                    continue
                barray = bytearray(data)
                # 音量計算
                energy = sr.audioop.rms(barray, WIDTH)
                if energy>10:
                    cross = sr.audioop.cross(barray, WIDTH)
                else:
                    cross = 0
                # Plotに送る
                plot_queue.put( (data,energy,cross) )
                # バッファに追加
                data_len=len(barray)
                buffer[:-data_len] = buffer[data_len:]
                buffer[-data_len:] = barray
                del barray
                energy_hist.add(energy)
                # ゼロ交錯数は常に平均をとって判定に使う
                cross_hist.add(cross)
                cross_on = cross_hist.ave*Model.cross_on_rate
                cross_off = cross_on
                Model.energy_hist.add(energy)
                Model.cross_hist.add(cross)
                # ポインタをシフト
                if xpos_start <= hist_len:
                    xpos_start -= 1
                if network_error>0:
                    network_error-=1
                    continue
                # トリガー
                rec_mode = 0
                if xpos_start>=hist_len:
                    # 休止中
                    if energy_lo_th<energy or cross_on<cross:
                        print(f"[REC]UP {energy}/{energy_lo_th} {cross}/{cross_on}")
                        energy_hi_ave = energy*2
                        in_talk = next_talk
                        xpos_start = hist_len-3
                        #Model.recog_detect.append("<st>")
                        lim_sec = 1.8
                        silent_count=0
                        fail_count=0
                    else:
                        silent_count+=1
                        energy_lo_ave += int( (energy-energy_lo_ave)*0.1 )
                        energy_lo_th = int(energy_lo_ave * Model.energy_up_rate)
                        if aaaaa>0 and silent_count>7:
                            llm_queue.put((in_talk,recog_text+"\n"))
                            recog_text = ''
                            Model.recog_detect.clear()
                            aaaaa=0
                else:
                    energy_hi_ave += int( (energy-energy_hi_ave)*0.2 )
                    energy_hi_th = int(energy_hi_ave * Model.energy_dn_rate)
                    buf_sec = (hist_len-xpos_start)*DELTA_TIME
                    # バッファ中
                    if energy<energy_hi_th and ( cross<cross_off or buf_sec>lim_sec ):
                        xcount += 1
                    else:
                        xcount = 0
                    if xcount>3:
                        print(f"[REC]DN {energy}/{energy_hi_th} {cross}/{cross_off}")
                        xpos_end = hist_len+1
                        rec_mode=1
                    elif buf_sec>lim_sec:
                        # 分割位置を探す
                        low_idx = energy_hist.argmin( int((xpos_start+hist_len)*0.5) )-1
                        print(f"[REC] split energy {low_idx}")
                        while low_idx<hist_len and cross_hist.get(low_idx)>cross_off:
                            low_idx+=1
                        print(f"[REC] split cross {low_idx}")
                        xpos_end = low_idx
                        rec_mode=2

                if rec_mode>0:                    
                    rec_start_time = int(time.time()*1000)
                    try:
                        Model.recog_state.set_running(True)
                        st = buffer_len - (hist_len-xpos_start)*array_size
                        ed = buffer_len - (hist_len-xpos_end+1)*array_size
                        audio_data = sr.AudioData( buffer[st:ed], RATE, WIDTH)
                        raw_text, confidence = recognizer.recognize_google(audio_data, language=Model.lang_in, with_confidence=True)
                        del audio_data
                    except (sr.exceptions.RequestError,TimeoutError) as ex:
                        print(f"[REC]{str(ex)}")
                        network_error = int(5/DELTA_TIME)
                        Model.recog_state.set_error('netError')
                        xpos_start = hist_len+1
                        continue
                    except sr.UnknownValueError as ex:
                        raw_text = ''
                        confidence = 0.0
                    finally:
                        Model.recog_state.set_running(False)
                    rec_time = int(time.time()*1000)-rec_start_time
                    if len(raw_text)>0:
                        print("[REC] {} {}(ms) ok {}:{} {},{}".format(rec_mode,rec_time,xpos_start,xpos_end,in_talk,raw_text))
                        Model.recog_detect.append(raw_text)
                        recog_text += raw_text
                        aaaaa=1
                        if rec_mode == 1:
                            xpos_start = hist_len+1
                        else:
                            xpos_start = xpos_end-1
                            Model.recog_detect.append("<|>")
                    else:
                        if rec_mode == 1:
                            print("[REC] {} {}(ms) fail {}:{}".format(rec_mode,rec_time,xpos_start,xpos_end))
                            xpos_start = hist_len+1
                        elif lim_sec < 3.0:
                            print("[REC] {} {}(ms) <-> {}:{}".format(rec_mode,rec_time,xpos_start,xpos_end))
                            fail_count+=1
                            if fail_count>=3:
                                energy_lo_ave = energy_hi_ave
                                energy_hi_ave = energy_hi_ave * 1000
                            else:
                                energy_hi_ave = energy_hi_ave * 1.2
                                energy_lo_ave = energy_hi_ave * 1.2
                            xpos_start = xpos_end-2
                        else:
                            print("[REC] {} {}(ms) <X> {}:{}".format(rec_mode,rec_time,xpos_start,xpos_end))
                            #Model.recog_detect.append("<X>")
                            xpos_start = hist_len + 1
                            xpos_end = xpos_start
        except Exception as ex:
            traceback.print_exc()
            print("[process_audio]"+ex.__class__.__name__+" "+ex)
        finally:
            pass
    finally:
        print("[process_audio]exit")
        plot_queue.put(None)

CANCEL_WARDS = ("きゃんせる","キャンセル","ちょっと待っ","停止","違う違う","stop","abort","cancel")
def is_cancel(text):
    for w in CANCEL_WARDS:
        if w in text:
            return True
    return False

import langchain.tools.python
def LLM_process():
    """LLM"""
    from libs.BotCustomCallbackHandler import BotCustomCallbackHandler
    global Model 
    global running
    global quiet_timer
    try:
        ai_id="x001"
        remove_word = [
            "何かお手伝いできますか？",
            "どのようにお手伝いできますか？","どのようなお手伝いができますか？",
            "お手伝いできることがありますか？","他に何かお手伝いできることはありますか？",
            "どのようなお話しをしましょうか？"]
        query=""
        openai_model='gpt-3.5-turbo'
        #openai_model='gpt-4'

        match_llm = ChatOpenAI(temperature=0, max_tokens=2000, model=openai_model)
        # ツールの準備
        llm_math_chain = LLMMathChain.from_llm(llm=match_llm,verbose=False)
        web_tool = WebSearchTool()

        task_repo = AITaskRepo()
        task_tool = AITaskTool()
        task_tool.bot_id = ai_id
        task_tool.task_repo = task_repo

        tools=[]
        tools += [
            web_tool,
            task_tool,
            #langchain.tools.PythonAstREPLTool(),
            Tool(
                name="Calculator",
                func=llm_math_chain.run,
                description="useful for when you need to answer questions about math"
            )
        ]
        # systemメッセージプロンプトテンプレートの準備
        system_prompt = """
            You are an AI chatbot with speech recognition and text-to-speech.
            Response to user in short sentences. Your sentence must be 50 characters or less.
            """
        system_prompt = "You are a chatbot that provides users with fun conversations. It infers user interests from conversations and provides relevant information."
        system_message = SystemMessage(
            content=system_prompt
        )
        # メモリの準備
        agent_kwargs = {
            "system_message": system_message,
            "extra_prompt_messages": [MessagesPlaceholder(variable_name="memory_hanaya")],
        }
        #func_memory = ConversationBufferWindowMemory( k=3, memory_key="memory",return_messages=True)
        mem_llm = ChatOpenAI(temperature=0, max_tokens=2000, model=openai_model)
        func_memory = ConversationSummaryBufferMemory(llm=mem_llm, max_token_limit=600, memory_key="memory_hanaya", return_messages=True)
        mx : CustomChatMessageHistory = CustomChatMessageHistory()
        func_memory.chat_memory : BaseChatMessageHistory=mx #Field(default_factory=ChatMessageHistory)

        current_location = web_tool.get_weather()
        # エージェントの準備
        def token_callback(talk_id,text):
            text = mx.convert(text)
            if len(text)>0:
                print(f"[LLM]put {text}")
                wave_queue.put( (talk_id,text) )

        def tool_callback(talk_id,text):
            App.chat_hist.insert(tk.END,'\n'+text+"\n")
            App.chat_hist.see('end')
        def llm_run(query):
            global Model
            if not Model.llm_state.get_enable():
                print(f"[LLM] ignore:{query}")
                res_list = split_string(query)
                for t in res_list:
                    print(f"[LLM]put {t}")
                    wave_queue.put((Model.talk_id,t))
                del res_list
                return
            try:
                print(f"[LLM] you text:{query}")
                Model.llm_state.set_running(True)
                # 現在の時刻を取得
                formatted_time = formatted_datetime()
                system_message.content = system_prompt + ' Talk casually in '+Model.lang_out + " ( current time: " + formatted_time + " " + current_location +")"
                callback_hdr = BotCustomCallbackHandler(Model)
                callback_hdr.talk_id = Model.talk_id
                callback_hdr.message_callback = token_callback
                callback_hdr.action_callback = tool_callback
                req_timeout = (10.0, 30.0)
                req_retries=0
                agent_llm = ChatOpenAI(temperature=0.7, max_tokens=2000, model=openai_model, streaming=True,request_timeout=req_timeout,max_retries=req_retries)
                # エージェントの準備
                agent_chain = initialize_agent(
                    tools, 
                    agent_llm, 
                    agent=AgentType.OPENAI_FUNCTIONS,
                    verbose=False, 
                    memory=func_memory,
                    agent_kwargs=agent_kwargs, 
                    handle_parsing_errors=_handle_error
                )
                x=0
                while x<3:
                    try:
                        res_text = agent_chain.run(input=query,callbacks=[callback_hdr])
                        break
                    except openai.error.APIError as ex:
                        if not "You can retry your request" in str(ex):
                            raise ex
                        print(ex)
                    x+=1
                print(f"[LLM] GPT text:{res_text}")
            except KeyboardInterrupt as ex:
                print("[LLM] cancel" )
            except openai.error.APIError as ex:
                traceback.print_exc()
            except Exception as ex:
                traceback.print_exc()
            finally:
                Model.llm_state.set_running(False)
                wave_queue.put( (callback_hdr.talk_id,MARK_END) )
                del callback_hdr
                del agent_chain
                del agent_llm
        try:
            last_queue=""
            thread :threading.Thread = None
            talk_id = 0
            in_talk = 0
            while running:
                
                if not ( thread and thread.is_alive() ) and llm_queue.qsize()==0:
                    task : AITask = task_repo.get_task(ai_id)
                    if task:
                        q = "It's the reserved time, so you do \"" + task.action + "\" in now for \"" + task.purpose +"\"."+AppModel.LONG_BLANK
                        llm_queue.put((in_talk,q))

                if llm_queue.qsize()==0:
                    time.sleep(0.5)
                    continue

                while llm_queue.qsize()>0:
                    item = llm_queue.get()
                    if item is None:
                        break
                    in_talk, text = item
                    query = query.strip() + " " + text
                    App.llm_send_text.delete(1.0,'end')
                    App.llm_send_text.insert(1.0,query)

                if thread is not None and not thread.is_alive():
                    del thread
                    thread = None
                    if Model.interrupt_mode == 'keyword':
                        query = ""
                        App.llm_send_text.delete(1.0,'end')

                if thread is None:
                    if query.endswith("\n") or query.endswith(AppModel.LONG_BLANK):
                        Model.talk_id = Model.next_id()
                        #start
                        last_queue = query
                        query = ""
                        wave_queue.put( (Model.talk_id,MARK_START) )
                        App.llm_send_text.delete(1.0,tk.END)
                        App.chat_hist.insert(tk.END,"\n\n[YOU]"+last_queue+"\n")
                        App.chat_hist.see('end')
                        thread = threading.Thread(target=llm_run,args=(last_queue,),daemon=True)
                        thread.start()
                else:
                    do_cancel = False
                    if Model.interrupt_mode == 'keyword':
                        do_cancel = is_cancel(query)
                    else:
                        do_cancel = True
                    if do_cancel:
                        cancel_id = Model.talk_id
                        Model.talk_id = Model.next_id()
                        if force_interrupt(thread):
                            print(f"[LLM] success to cancel talk_id:{cancel_id}")
                        else:
                            print(f"[LLM] failled to cancel talk_id:{cancel_id}")
                        thread.join()
                        del thread
                        thread = None
                        if Model.interrupt_mode == 'keyword':
                            query = ""
                        else:
                            query = last_queue + " " + query
                        wave_queue.put( (cancel_id,MARK_END) )
                        App.llm_send_text.delete(1.0,'end')
                        App.llm_send_text.insert(1.0,query)
                now = int(time.time()*1000)
        except Exception as ex:
            traceback.print_exc()
        finally:
            pass
    finally:
        print("[LLM]exit")
        wave_queue.put(None)

def wave_process():
    """テキストから音声へ変換"""
    global running
    global Model, App
    try:
        now = int(time.time()*1000)
        init = 0
        while running:
            if wave_queue.qsize()==0:
                time.sleep(0.5)
                continue
            item = wave_queue.get()
            if item is None:
                break
            talk_id, text = item
            if text == MARK_START:
                talk_queue.put( (talk_id,text,Model.sound1) )
                continue
            if text == MARK_END:
                talk_queue.put( (talk_id,text,Model.sound2) )
                continue
            if talk_id != Model.talk_id or len(text)==0:
                continue

            if Model.wave_state.get_enable():
                if init == 0:
                    init = 1

                try:
                    # テキストを音声に変換
                    Model.wave_state.set_running(True)
                    print(f"[WAVE] create audio {text}")
                    audio_bytes :bytes = Model.voice_api.text_to_audio(text,lang=Model.lang_out[:2])
                    talk_queue.put( (talk_id,text,audio_bytes) )
                except Exception as e:
                    traceback.print_exc()
                finally:
                    Model.wave_state.set_running(False)
            else:
                if init != 0:
                    init = 0
                App.chat_hist.insert(tk.END,text)
                App.chat_hist.see('end')
    except Exception as ex:
        traceback.print_exc()
    finally:
        print("[WAVE]exit")
        talk_queue.put(None)

def talk_process():
    """音声再生"""
    global running
    global Model
    try:
        pygame.mixer.pre_init(16000,-16,1,10240)
        pygame.mixer.quit()
        pygame.mixer.init()
        try:
            init = 0
            end_time = 0
            while running:
                now = int(time.time()*1000)
                if talk_queue.qsize()>0:
                    item = talk_queue.get()
                    if item is None:
                        break
                    
                    if not Model.talk_state.get_enable():
                        continue

                    talk_id, text, audio = item
                    if talk_id != Model.talk_id:
                        continue

                    if init == 0:
                        init = 1

                    try:
                        mp3_buffer = BytesIO(audio)
                        pygame.mixer.music.load(mp3_buffer)
                        del mp3_buffer
                        # 音声を再生
                        Model.talk_state.set_running(True)
                        App.talk_text.insert(tk.END,text)
                        if text != MARK_START and text != MARK_END:
                            App.chat_hist.insert(tk.END,text)
                            App.chat_hist.see('end')
                            del audio
                        Model.play_talk_id = talk_id
                        print(f"[TALK] start talk_id:{Model.play_talk_id}")
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            if talk_id != Model.talk_id:
                                pygame.mixer.music.pause()
                                break
                            time.sleep(0.2)
                    finally:
                        end_time = int(time.time()*1000)
                        pygame.mixer.music.unload()
                        App.talk_text.delete(1.0,tk.END)
                        Model.talk_state.set_running(False)
                else:
                    if Model.play_talk_id != 0 and (now-end_time)>200:
                        print(f"[TALK] end talk_id:{Model.play_talk_id}")
                        Model.play_talk_id = 0
                    if not Model.talk_state.get_enable() and init != 0:
                        init = 0
                    time.sleep(0.2)
        except Exception as ex:
            traceback.print_exc()
        finally:
            print("[TALK]quit")
            pygame.mixer.quit()
    finally:
        print("[TALK]exit")

def llm_send_text():
    global Model,App
    text = App.llm_send_text.get(1.0,tk.END)
    App.llm_send_text.delete(1.0,tk.END)
    llm_queue.put( (0, text) )
    llm_queue.put( (0, "\n") )

# GUIの作成
class AppWindow(tk.Tk):
    global Model
    def __init__(self):
        super().__init__()
        self.title("試験用)音声認識チャットボット")
        # ウインドウのサイズ設定
        self.geometry("900x600")

        #-----------------------------------------------------
        # 録音フレームの作成
        #-----------------------------------------------------
        record_frame = tk.Frame(self,relief=tk.SOLID,height=200)
        record_frame.pack(side=tk.BOTTOM, fill=tk.X)
        record_frame2 = tk.Frame(record_frame,relief=tk.SOLID)
        record_frame2.pack(side=tk.RIGHT, fill=tk.Y)
        # ドロップダウンリストの作成
        mic_name_array = [microphone[0] for microphone in Model.get_microphone_list()]
        mic_idx_array =  [microphone[1] for microphone in Model.get_microphone_list()]
        mic_dropdown = ttk.Combobox(record_frame2, values=mic_name_array, state="readonly")
        mic_dropdown.pack(side=tk.TOP)
        def on_mic_selection(event):
            selected_item = mic_dropdown.get()
            num = mic_name_array.index(selected_item)
            selected_index = mic_idx_array[num]
            Model.microphone_index = selected_index
        mic_dropdown.bind("<<ComboboxSelected>>", on_mic_selection)
        mic_dropdown.current(mic_idx_array.index(Model.microphone_index))
        # ラベルの作成
        self.audio_level_1 = tk.Label(record_frame2, width=12, height=1)
        self.audio_level_1.pack(side=tk.TOP)
        self.audio_level_4 = tk.Label(record_frame2, width=12, height=1)
        self.audio_level_4.pack(side=tk.TOP)
        self.audio_level_2 = tk.Label(record_frame2, width=12, height=1)
        self.audio_level_2.pack(side=tk.TOP)
        self.audio_level_3 = tk.Label(record_frame2, width=12, height=1)
        self.audio_level_3.pack(side=tk.TOP)
        #-----------------------------------------------------
        # プロットフレーム
        #-----------------------------------------------------
        fig = Figure(figsize=(1, 1), dpi=70)
        self.ax1 = fig.add_subplot(111)
        x_axis = np.arange(0, x_size, 1)
        self.line1, = self.ax1.plot(x_axis, np.zeros((x_size,)),'-',color='Gray')
        self.ax1.set_xlim(0, x_size)
        self.ax1.set_ylim(-32768, 32768)
        self.ax1.tick_params(axis='both', which='both', bottom=False, top=False, left=False, right=False, labelbottom=False, labelleft=False)

        self.ax2 = self.ax1.twinx()
        # x = np.arange(0, x_size, 1)
        self.line2, = self.ax2.plot(x_axis, np.zeros((x_size,)), linestyle='dotted', color='red')
        self.ax2.set_xlim(0, x_size)
        self.ax2.set_ylim(0, 5000)
        #self.ax2.tick_params(axis='both', which='both', bottom=False, top=False, left=False, right=False, labelbottom=False, labelleft=False)

        # self.ax3 = fig.add_subplot(111)
        # x = np.arange(0, x_size, 1)
        self.line3, = self.ax2.plot(x_axis, np.zeros((x_size,)), linestyle='dotted', color='blue')
        # self.ax3.set_xlim(0, x_size)
        # self.ax3.set_ylim(0, 32768)
        # self.ax3.tick_params(axis='both', which='both', bottom=False, top=False, left=False, right=False, labelbottom=False, labelleft=False)

        self.canvas = FigureCanvasTkAgg(fig, master=record_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        #-----------------------------------------------------
        # 音声認識フレームの作成
        #-----------------------------------------------------
        detect_frame = tk.Frame(self,relief=tk.SOLID)
        detect_frame.pack(side=tk.BOTTOM, fill=tk.X)
        detect_frame2 = self.create_indicator_frame(detect_frame,Model.audio_state,Model.recog_state)
        detect_frame2.pack(side=tk.RIGHT, fill=tk.Y)

        detect_frame3 = tk.Frame(detect_frame,relief=tk.SOLID,borderwidth=1)
        detect_frame3.pack(side=tk.RIGHT, fill=tk.Y)
        # ドロップダウンリストの作成
        lang_in_dropdown = ttk.Combobox(detect_frame3, values=AppModel.LANG_LIST, state="readonly", width=10)
        lang_in_dropdown.pack(side=tk.TOP)
        # ドロップダウンリストの選択が変更されたときのイベントハンドラを設定
        def on_lang_in_selection(event):
            Model.lang_in = lang_in_dropdown.get()
        lang_in_dropdown.bind("<<ComboboxSelected>>", on_lang_in_selection)
        lang_in_dropdown.current(0)
        # Labelの作成
        self.recog_fail_energy = tk.Label(detect_frame3, width=12, height=1)
        self.recog_fail_energy.pack(side=tk.TOP)
        self.recog_min_energy = tk.Label(detect_frame3, width=12, height=1)
        self.recog_min_energy.pack(side=tk.TOP)
        self.recog_limit_energy = tk.Label(detect_frame3, width=12, height=1)
        self.recog_limit_energy.pack(side=tk.TOP)
        # Entry
        detect_frame4 = tk.Frame(detect_frame,relief=tk.SOLID,borderwidth=1)
        detect_frame4.pack(side=tk.RIGHT, fill=tk.Y)
        def on_entry_a(value:float):
            Model.cross_on_rate = value
        self.create_float_entry( detect_frame4, 'cross_on_rate', Model.cross_on_rate, on_entry_a )
        def on_entry_b(value:float):
            Model.energy_up_rate = value
        self.create_float_entry( detect_frame4, 'energy_up_rate', Model.energy_up_rate, on_entry_b )
        def on_entry_c(value:float):
            Model.energy_dn_rate = value
        self.create_float_entry( detect_frame4, 'energy_dn_rate', Model.energy_dn_rate, on_entry_c )

        # テキストボックスの作成
        self.recog_buffer = tk.Text(detect_frame, height=5,width=40)
        self.recog_buffer.pack(side=tk.LEFT)
        # テキストボックスの作成
        self.recog_detect = tk.Text(detect_frame, height=5,width=40)
        self.recog_detect.pack(side=tk.LEFT)

        #-----------------------------------------------------
        # LLMフレームの作成
        #-----------------------------------------------------
        llm_frame = tk.Frame(self,relief=tk.SOLID)
        llm_frame.pack(side=tk.BOTTOM, fill=tk.X)
        llm_frame2 = self.create_indicator_frame(llm_frame,Model.llm_state,None)
        llm_frame2.pack(side=tk.RIGHT, fill=tk.Y)
        # ストップボタンの作成
        send_button = tk.Button(llm_frame2, text="Send", command=llm_send_text)
        send_button.pack(side=tk.BOTTOM)
        # テキストボックスの作成
        self.llm_send_text = tk.Text(llm_frame, height=5)
        self.llm_send_text.pack(fill=tk.X)

        #-----------------------------------------------------
        # 発声フレームの作成
        #-----------------------------------------------------
        talk_frame = tk.Frame(self,relief=tk.SOLID)
        talk_frame.pack(side=tk.BOTTOM, fill=tk.X)
        talk_frame2 = self.create_indicator_frame(talk_frame,Model.wave_state,Model.talk_state)
        talk_frame2.pack(side=tk.RIGHT, fill=tk.Y)
        # voice list
        talk_frame3 = tk.Frame(talk_frame,relief=tk.SOLID)
        talk_frame3.pack(side=tk.RIGHT, fill=tk.Y)
        # ドロップダウンリストの作成
        voice_dropdown = ttk.Combobox(talk_frame3, values=[voice[0] for voice in VoiceAPI.VoiceList], state="readonly", width=40)
        voice_dropdown.pack(side=tk.TOP)
        # ドロップダウンリストの選択が変更されたときのイベントハンドラを設定
        def on_lang_out_selection(event):
            selected_item = voice_dropdown.get()
            selected_index = [voice[0] for voice in VoiceAPI.VoiceList].index(selected_item)
            selected_number = VoiceAPI.VoiceList[selected_index][1]
            Model.lang_out = VoiceAPI.VoiceList[selected_index][2]
            Model.voice_api.speaker = selected_number
        voice_dropdown.bind("<<ComboboxSelected>>", on_lang_out_selection)
        voice_dropdown.current(0)
        # テキストボックスの作成
        self.talk_text = tk.Text(talk_frame, height=2)
        self.talk_text.pack(fill=tk.BOTH,expand=True)

        #-----------------------------------------------------
        # 会話履歴フレームの作成
        #-----------------------------------------------------
        hist_frame_1 = tk.Frame(self,borderwidth=1,relief=tk.SOLID)
        hist_frame_1.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)
        hist_frame_2 = tk.Frame(hist_frame_1,borderwidth=1,relief=tk.SOLID)
        hist_frame_2.pack(side=tk.RIGHT, fill=tk.Y)
        # ドロップダウンリストの作成
        inter_dropdown = ttk.Combobox(hist_frame_2, values=AppModel.INTERRUPT_LIST, state="readonly", width=10)
        inter_dropdown.pack(side=tk.TOP)
        # ドロップダウンリストの選択が変更されたときのイベントハンドラを設定
        def on_inter_selection(event):
            Model.interrupt_mode = inter_dropdown.get()
        inter_dropdown.bind("<<ComboboxSelected>>", on_inter_selection)
        inter_dropdown.current(0)

        # テキストボックスの作成
        self.chat_hist = scrolledtext.ScrolledText(hist_frame_1, height=10, width=80)
        self.chat_hist.pack(fill=tk.BOTH,expand=True)

        # ウィンドウを閉じるときに呼ばれる関数を設定
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        print("[APP]closing")
        global Model, running
        running = False
        Model.join(timeout=3.0)
        self.destroy()

    def set_ydata(self,audio_buffer, ene, crosss):
        if audio_buffer is not None:
            self.line1.set_ydata(audio_buffer)
            self.ax1.relim()
            self.ax1.autoscale_view()
        if ene is not None:
            self.line2.set_ydata(ene)
        if crosss is not None:
            self.line3.set_ydata(crosss)
        if ene is not None or crosss is not None:
            self.ax2.relim()
            self.ax2.autoscale_view()
        self.canvas.draw()
        #canvas.flush_events()

    def create_indicator_frame(self,parent_frame,model_state_1,model_state_2):
        sub_frame = tk.Frame(parent_frame,relief=tk.SOLID,borderwidth=1)
        sub_frame.pack(side=tk.RIGHT, fill=tk.Y)
        # インジケータの作成
        indicator = tk.Label(sub_frame, width=5, height=1, bg="gray", text=model_state_1.title)
        indicator.pack(side=tk.TOP,padx=2,pady=2)

        # ストップボタンの作成
        enable_button = tk.Button(sub_frame, text="Off" )
        enable_button.pack(side=tk.BOTTOM,padx=2,pady=2)

        def update_indicator_status(state):
            color='gray'
            if state.get_error():
                color='red'
            elif state.get_running():
                color='blue'
            elif state.get_enable():
                color='green'
            indicator.config( bg=color)
            if state.get_enable():
                enable_button.config( text="On" )
            else:
                enable_button.config( text="Off" )
        model_state_1.callback = update_indicator_status

        if model_state_2 is not None:
            indicator2 = tk.Label(sub_frame, width=5, height=1, bg="gray", text=model_state_2.title)
            indicator2.pack(side=tk.TOP,padx=2,pady=2)
            def update_indicator_status2(state):
                color='gray'
                if state.get_running():
                    color='blue'
                elif state.get_enable():
                    color='green'
                indicator2.config( bg=color)
            model_state_2.callback = update_indicator_status2

        def set_enable_indicator():
            enable = (enable_button['text'] == "On")
            model_state_1.set_enable( not enable)
            if model_state_2 is not None:
                model_state_2.set_enable( not enable)
        enable_button.config( command=set_enable_indicator )
        return sub_frame
    
    def create_float_entry(self, frame, title:str, value:float, callback=None ):
        def on_entry(event):
            try:
                value: float = float( event.widget.get() )
                callback(value)
            except:
                pass
        sub_frame = tk.Frame(frame,borderwidth=0)
        sub_frame.pack(side=tk.TOP, fill=tk.X,padx=0,pady=0)
        lbl = tk.Label(sub_frame,text=title)
        lbl.pack(side=tk.LEFT)
        ent : tk.Entry = tk.Entry(sub_frame, width=12)
        ent.pack(side=tk.TOP,fill=tk.BOTH)
        ent.insert(0,str(value))
        if callback:
            ent.bind("<Return>", on_entry)

def main():
    try:
        os.makedirs("logs",exist_ok=True)
        import logging
        logger = logging.getLogger("openai")
        logger.setLevel( logging.DEBUG )
        fh = logging.FileHandler("logs/openai.log")
        logger.addHandler(fh)
        global Model,App
        if not os.environ.get("OPENAI_API_KEY"):
            for subdir in ('..', '../..'):
                try:
                    with open(subdir + '/openai_api_key.txt','r') as cfg:
                        k = cfg.readline()
                        if k is not None and len(k)>0:
                            os.environ["OPENAI_API_KEY"] = k
                            break
                except:
                    pass
        if not os.environ.get("OPENAI_API_KEY"):
            print("ERROR: OPENAI_API_KEY is blank")
            return
        Model=AppModel()
        App = AppWindow()
        Model.start()
        # アプリケーションの実行
        App.mainloop()
    except Exception as ex:
        traceback.print_exc()
    finally:
        running = False

def test():
    current_time = datetime.datetime.now()
    print(f"current_time:{current_time}")
    formatted_time = formatted_datetime()
    print(f"current_time:{formatted_time}")
    def test_run():
        i = 0
        while True:
            time.sleep(1.0)
            print(f"xx {i} ", end='')
            i += 1
    
    thr = threading.Thread(target=test_run)
    thr.start()
    time.sleep(3.0)
    force_interrupt(thr)

if __name__ == '__main__':
    main()
    #test()

__all__ = ['AppModel']