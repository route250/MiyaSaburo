from typing import Type
import sys
import os
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
import time
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from libs.VoiceAPI import VoiceAPI
from tools.QuietTool import QuietTool
from tools.webSearchTool import WebSearchTool

import openai
from langchain.chains.conversation.memory import ConversationBufferMemory,ConversationBufferWindowMemory
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

# 再生関係
import pygame

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
        self.lang = AppModel.LANG_LIST[0]
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

    def run(self):
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
            threading.Thread(target=process_audio),
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

            time.sleep(0.2)
            i = (i+1) % 3

        print("[Thread]waiting...")
        for thread in threads:
            thread.join(timeout=0.2)
        print("[Thread]stopped")

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
REC_SIZE = int(RATE*0.2)  # 録音時間（秒）
REC_BUFFER_SEC = 10
reduce_sz=2000
x_size = int(RATE*15/reduce_sz)

frame_queue = queue.Queue()
plot_queue = queue.Queue()
llm_queue = queue.Queue()
wave_queue = queue.Queue()
talk_queue = queue.Queue()

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
        print(ex)        
    print("[MIC]end")
    return microphones

def create_sound(Hz1=440,time=0.3):
    #再生時間を指定
    #time=2
    #周波数を指定
    #Hz1=300
    #再生時間を設定
    arr_size = int(44100*time*2)
    x=np.linspace(0,arr_size,arr_size)
    y=np.sin(2*np.pi*Hz1/44100*x)*10000
    y=y.astype(np.int16)
    xtime=x/44100
    sound_arr = y.reshape(int(y.shape[0]/2), 2)
    pygame.mixer.init()
    sound = pygame.sndarray.make_sound(sound_arr)
    return sound

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
        pass

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
                    print(ex)
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
        print(ex)
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
                            raw_text, confidence = recognizer.recognize_google(audio_data, language=Model.lang, with_confidence=True)
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
                        App.rec_info1.config(text=f"fail:{energy}")
                    else:
                        shift_set(recog_hist,audio_energy)
                        recog_min_energy = np.min(recog_hist)
                        App.rec_info2.config(text=f"success:{recog_min_energy}")
                        recog_limit_energy = int((recog_min_energy-AppModel.AUDIO_ENERGY_TRIGGER)*0.6)+AppModel.AUDIO_ENERGY_TRIGGER
                        App.rec_info3.config(text=f"low:{recog_limit_energy}")

                    if raw_text == '':
                        if detect.text == '':
                            # 無音が続いている
                            App.rec_1.delete(1.0,tk.END)
                            detect.d_continue(buffer_len)
                            if detect.count >= accept_count:
                                #3回同じ内容が来た
                                pos = detect.end0
                                detect.d_end(buffer_len)
                                if sended:
                                    print(f"[REC] blank NL {in_talk},{detect.count}/{accept_count}")
                                    llm_queue.put((in_talk,"\n"))
                                    App.detect_text.delete(1.0,tk.END)
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
                            App.rec_1.delete(1.0,tk.END)
                            App.detect_text.insert(tk.END,detect.text)
                            pos = detect.end
                            detect.d_end(buffer_len)
                            print("[REC]___")
                    else:
                        if detect.text == '':
                            # 初の検出
                            llm_queue.put((in_talk," "))
                            detect.d_start(pos,buffer_len,raw_text)
                            App.rec_1.insert(tk.END,raw_text+"\n")
                            if confidence <0.95:
                                print("[REC]start {}".format(raw_text))
                            else:
                                print("[REC] 1st ---> {},{}".format(in_talk,detect.text))
                                llm_queue.put((in_talk,detect.text))
                                sended=True
                                App.rec_1.delete(1.0,tk.END)
                                App.detect_text.insert(tk.END,detect.text)
                                pos = detect.end
                                detect.d_end(buffer_len)
                        else:
                            # 2回目以降の検出
                            if detect.text == raw_text:
                                detect.count += 1
                                if detect.count < accept_count:
                                    print("[REC]{} {}".format(detect.count,raw_text))
                                    detect.d_continue(buffer_len)
                                    App.rec_1.insert(tk.END,raw_text+"\n")
                                else:
                                    #3回同じ内容が来た
                                    print("[REC] eq ===> {} => {},{}".format(detect.count,in_talk,detect.text))
                                    llm_queue.put((in_talk,detect.text))
                                    sended=True
                                    App.rec_1.delete(1.0,tk.END)
                                    App.detect_text.insert(tk.END,detect.text)
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
                                App.rec_1.insert(tk.END,raw_text+"\n")
                            elif pos<=0:
                                # 先頭部分だけ一致した
                                print("[REC] over ===> {},{}".format(in_talk,detect.text))
                                llm_queue.put((in_talk,detect.text))
                                sended=True
                                App.rec_1.delete(1.0,tk.END)
                                App.detect_text.insert(tk.END,detect.text)
                                pos = detect.end0
                                detect.d_end(buffer_len)
                            else:
                                # やりなおし？
                                print("[REC]reset {}".format(raw_text))
                                detect.d_start(pos,buffer_len,raw_text)
                                App.rec_1.insert(tk.END,raw_text+"\n")

                if in_talk != next_talk:
                    if detect.text != '':
                        print("[REC] tk ===> {},{}".format(in_talk,detect.text))
                        llm_queue.put((in_talk,detect.text))
                        sended=True
                    if sended:
                        print("[REC] tk ===> \\nl")
                        llm_queue.put((in_talk,"\n"))
                        App.detect_text.delete(1.0,tk.END)
                        sended=False
                    in_talk = next_talk
                    in_count = 0
                    Model.energy_hist.clear()
                    pos = buffer_len
                    detect.d_end(buffer_len)

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
        remove_word = [
            "何かお手伝いできますか？",
            "どのようにお手伝いできますか？","どのようなお手伝いができますか？",
            "お手伝いできることがありますか？","他に何かお手伝いできることはありますか？",
            "どのようなお話しをしましょうか？"]
        query=""
        # エージェントの準備
        def token_callback(talk_id,text):
            for word in remove_word:
                if text.endswith(word):
                    text = text[:-len(word)]
            if len(text)>0:
                print(f"[LLM]put {text}")
                wave_queue.put( (talk_id,text) )

        def tool_callback(talk_id,text):
            App.chat_hist.insert(tk.END,'\n'+text+"\n")
            App.chat_hist.see('end')
        #openai_model='gpt-3.5-turbo'
        openai_model='gpt-4'

        llm = ChatOpenAI(temperature=0.7, max_tokens=2000, model=openai_model, streaming=True)
        # ツールの準備
        llm_math_chain = LLMMathChain.from_llm(llm=llm,verbose=False)
        web_tool = WebSearchTool()
        tools=[]
        tools += [
            web_tool,
            QuietTool(),
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
            "extra_prompt_messages": [MessagesPlaceholder(variable_name="memory")],
        }
        func_memory = ConversationBufferWindowMemory( k=3, memory_key="memory",return_messages=True)
        #func_memory = ConversationBufferWindowMemory( k=5 )
        #func_memory = ConversationBufferMemory(memory_key="memory", return_messages=True)

        # エージェントの準備
        agent_chain = initialize_agent(
            tools, 
            llm, 
            agent=AgentType.OPENAI_FUNCTIONS,
            verbose=False, 
            memory=func_memory,
            agent_kwargs=agent_kwargs, 
            handle_parsing_errors=_handle_error
        )
        current_location = web_tool.get_weather()
        # run_manager.stop()
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
                system_message.content = system_prompt + ' Use language of '+Model.lang + " ( current time: " + formatted_time + " " + current_location +")"
                callback_hdr = BotCustomCallbackHandler(Model)
                callback_hdr.talk_id = Model.talk_id
                callback_hdr.message_callback = token_callback
                callback_hdr.action_callback = tool_callback
                res_text = agent_chain.run(input=query,callbacks=[callback_hdr])
                print(f"[LLM] GPT text:{res_text}")
            except KeyboardInterrupt as ex:
                print("[LLM] cancel" )
            except openai.error.APIError as ex:
                print(ex)
            except Exception as ex:
                print(ex)
            finally:
                Model.llm_state.set_running(False)
                del callback_hdr
        try:
            last_queue=""
            thread :threading.Thread = None
            talk_id = 0
            while running:
                
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
                    thread = None
                    if Model.interrupt_mode == 'keyword':
                        query = ""
                        App.llm_send_text.delete(1.0,'end')

                if thread is None:
                    if query.endswith("\n"):
                        Model.talk_id = Model.next_id()
                        #start
                        last_queue = query
                        query = ""
                        Model.sound1.play()
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
                        App.llm_send_text.delete(1.0,'end')
                        App.llm_send_text.insert(1.0,query)

                now = int(time.time()*1000)
                time.sleep(0.5)
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
            if talk_id != Model.talk_id or len(text)==0:
                continue

            if Model.wave_state.get_enable():
                if init == 0:
                    init = 1

                try:
                    # テキストを音声に変換
                    Model.wave_state.set_running(True)
                    print(f"[WAVE] create audio {text}")
                    audio_bytes :bytes = Model.voice_api.text_to_audio(text,lang=Model.lang[:2])
                    talk_queue.put( (talk_id,text,audio_bytes) )
                except Exception as e:
                    print(e)
                finally:
                    Model.wave_state.set_running(False)
            else:
                if init != 0:
                    init = 0
                App.chat_hist.insert(tk.END,text)
                App.chat_hist.see('end')

    finally:
        print("[WAVE]exit")
        talk_queue.put(None)

def talk_process():
    """音声再生"""
    global running
    global Model
    try:
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
                        # 音声を再生
                        Model.talk_state.set_running(True)
                        App.talk_text.insert(tk.END,text)
                        App.chat_hist.insert(tk.END,text)
                        App.chat_hist.see('end')
                        Model.play_talk_id = talk_id
                        print(f"[TALK] start talk_id:{Model.play_talk_id}")
                        pygame.mixer.music.play()
                        c = 0
                        while talk_id == Model.talk_id and pygame.mixer.music.get_busy():
                            c = (c+1) %2
                            if c == 0:
                                Model.talk_state.set_running(True)
                            else:
                                Model.talk_state.set_running(False)
                            time.sleep(0.5)
                        del mp3_buffer
                    finally:
                        end_time = int(time.time()*1000)
                        pygame.mixer.music.pause()
                        pygame.mixer.music.unload()
                        App.talk_text.delete(1.0,tk.END)
                        Model.talk_state.set_running(False)
                else:
                    if Model.play_talk_id != 0 and (now-end_time)>200:
                        print(f"[TALK] end talk_id:{Model.play_talk_id}")
                        Model.play_talk_id = 0
                        Model.sound2.play()
                    if not Model.talk_state.get_enable() and init != 0:
                        init = 0
                    time.sleep(0.2)
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
        self.geometry("800x600")

        # ボタンを配置するフレームの作成
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

        # plot area
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

        # ボタンを配置するフレームの作成
        detect_frame = tk.Frame(self,relief=tk.SOLID)
        detect_frame.pack(side=tk.BOTTOM, fill=tk.X)
        detect_frame2 = self.create_indicator_frame(detect_frame,Model.audio_state,Model.recog_state)
        detect_frame2.pack(side=tk.RIGHT, fill=tk.Y)

        detect_frame3 = tk.Frame(detect_frame,relief=tk.SOLID,borderwidth=1)
        detect_frame3.pack(side=tk.RIGHT, fill=tk.Y)
        # Labelの作成
        self.rec_info1 = tk.Label(detect_frame3, width=12, height=1)
        self.rec_info1.pack(side=tk.TOP)
        self.rec_info2 = tk.Label(detect_frame3, width=12, height=1)
        self.rec_info2.pack(side=tk.TOP)
        self.rec_info3 = tk.Label(detect_frame3, width=12, height=1)
        self.rec_info3.pack(side=tk.TOP)

        # テキストボックスの作成
        self.rec_1 = tk.Text(detect_frame, height=5,width=40)
        self.rec_1.pack(side=tk.LEFT)
        # テキストボックスの作成
        self.detect_text = tk.Text(detect_frame, height=5,width=40)
        self.detect_text.pack(side=tk.LEFT)

        # ボタンを配置するフレームの作成
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

        # ボタンを配置するフレームの作成
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
        def on_lang_selection(event):
            selected_item = voice_dropdown.get()
            selected_index = [voice[0] for voice in VoiceAPI.VoiceList].index(selected_item)
            selected_number = VoiceAPI.VoiceList[selected_index][1]
            Model.voice_api.speaker = selected_number
        voice_dropdown.bind("<<ComboboxSelected>>", on_lang_selection)
        voice_dropdown.current(0)
        # テキストボックスの作成
        self.talk_text = tk.Text(talk_frame, height=2)
        self.talk_text.pack(fill=tk.BOTH,expand=True)

        # ボタンを配置するフレームの作成
        hist_frame_1 = tk.Frame(self,borderwidth=1,relief=tk.SOLID)
        hist_frame_1.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)
        hist_frame_2 = tk.Frame(hist_frame_1,borderwidth=1,relief=tk.SOLID)
        hist_frame_2.pack(side=tk.RIGHT, fill=tk.Y)
        # ドロップダウンリストの作成
        lang_dropdown = ttk.Combobox(hist_frame_2, values=AppModel.LANG_LIST, state="readonly", width=10)
        lang_dropdown.pack(side=tk.TOP)
        # ドロップダウンリストの選択が変更されたときのイベントハンドラを設定
        def on_lang_selection(event):
            Model.lang = lang_dropdown.get()
        lang_dropdown.bind("<<ComboboxSelected>>", on_lang_selection)
        lang_dropdown.current(0)
        # ドロップダウンリストの作成
        inter_dropdown = ttk.Combobox(hist_frame_2, values=AppModel.INTERRUPT_LIST, state="readonly", width=10)
        inter_dropdown.pack(side=tk.TOP)
        # ドロップダウンリストの選択が変更されたときのイベントハンドラを設定
        def on_inter_selection(event):
            Model.interrupt_mode = inter_dropdown.get()
        inter_dropdown.bind("<<ComboboxSelected>>", on_inter_selection)
        inter_dropdown.current(0)

        # テキストボックスの作成
        self.chat_hist = tk.Text(hist_frame_1, height=10, width=80)
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

def main():
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