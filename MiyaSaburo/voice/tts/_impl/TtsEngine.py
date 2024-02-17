import sys,os,traceback,json,re
from threading import Thread, Condition, ThreadError
from concurrent.futures import ThreadPoolExecutor, Future
from queue import Queue, Empty
import time
import numpy as np
import requests
from requests.adapters import HTTPAdapter
import httpx

import openai
from openai import OpenAI

from gtts import gTTS
from io import BytesIO
import pygame
import wave
import librosa

from ...._impl import utils

import logging
logger = logging.getLogger('voice')

def f32_to_wave( audio_f32, *, sample_rate, channels=1 ):
    y = audio_f32 * 32768
    audio_bytes = y.astype(np.int16).tobytes()
    # wavファイルを作成してバイナリ形式で保存する
    wav_io = BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(channels)  # ステレオ (左右チャンネル)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)  # サンプリングレート
        wav_file.writeframes(audio_bytes)
    wav_io.seek(0)  # バッファの先頭にシーク
    wave_bytes = wav_io.read()
    return wave_bytes

# C4(ド) 261.63, D4(レ) 293.66  E4(ミ) 329.63 F4(ファ) 349.23 G4(ソ) 392.00 A4(ラ) 440.00 B4(シ) 493.88 C5(ド) 523.25
def create_wave(Hz=440, time=0.3, sample_rate=16000):
    data_len = int(sample_rate * time)
    if Hz > 0:
        sound = (np.sin(2 * np.pi * np.arange(data_len) * Hz / sample_rate)).astype(np.float32)
    else:
        sound = np.zeros(data_len, dtype=np.float32)
    return sound

def create_sound(sequence):
    """複数の（周波数、時間）タプルを受け取り、連続する音声データを生成する

    Args:
        sequence (list of tuples): (Hz, time)のタプルのリスト

    Returns:
        bytes: 生成された音声データのバイナリ（WAV形式）
    """
    sample_rate = 16000
    sounds = [create_wave(Hz, time, sample_rate) for Hz, time in sequence]
    combined_sound = np.concatenate(sounds)
    return f32_to_wave(combined_sound, sample_rate=sample_rate)

class TtsEngine:
    EOT:str = "<|EOT|>"
    VoiceList = [
        ( "VOICEVOX:四国めたん [あまあま]", 0, 'ja_JP' ),
        ( "VOICEVOX:四国めたん [ノーマル]", 2, 'ja_JP' ),
        ( "VOICEVOX:四国めたん [セクシー]", 4, 'ja_JP' ),
        ( "VOICEVOX:四国めたん [ツンツン]", 6, 'ja_JP' ),
        ( "VOICEVOX:ずんだもん [あまあま]", 1, 'ja_JP' ),
        ( "VOICEVOX:ずんだもん [ノーマル]", 3, 'ja_JP' ),
        ( "VOICEVOX:ずんだもん [セクシー]", 5, 'ja_JP' ),
        ( "VOICEVOX:ずんだもん [ツンツン]", 7, 'ja_JP' ),
        ( "VOICEVOX:春日部つむぎ [ノーマル]",8, 'ja_JP' ),
        ( "VOICEVOX:波音リツ [ノーマル]", 9, 'ja_JP' ),
        ( "VOICEVOX:雨晴はう [ノーマル]", 10, 'ja_JP' ),
        ( "VOICEVOX:玄野武宏 [ノーマル]", 11, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [ふつう]", 11, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [わーい]", 32, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [びくびく]", 33, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [おこ]", 34, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [びえーん]", 36, 'ja_JP' ),
        ( "VOICEVOX:冥鳴ひまり [ノーマル]", 14, 'ja_JP' ),
        ( "VOICEVOX:もち子(cv 明日葉よもぎ)[ノーマル]", 20, 'ja_JP' ),
        ( "VOICEVOX:小夜/SAYO [ノーマル]", 46, 'ja_JP' ),
        ( "OpenAI:alloy", 1001, 'ja_JP' ),
        ( "OpenAI:echo", 1002, 'ja_JP' ),
        ( "OpenAI:fable", 1003, 'ja_JP' ),
        ( "OpenAI:onyx", 1004, 'ja_JP' ), # 男性っぽい
        ( "OpenAI:nova", 1005, 'ja_JP' ), # 女性っぽい
        ( "OpenAI:shimmer", 1006, 'ja_JP' ), # 女性ぽい
        ( "gTTS:[ja_JP]", 2000, 'ja_JP' ),
        ( "gTTS:[en_US]", 2001, 'en_US' ),
        ( "gTTS:[en_GB]", 2002, 'en_GB' ),
        ( "gTTS:[fr_FR]", 2003, 'fr_FR' ),
    ]

    @staticmethod
    def id_to_model( idx:int ) -> str:
        return next((voice for voice in TtsEngine.VoiceList if voice[1] == idx), None )

    @staticmethod
    def id_to_name( idx:int ) -> str:
        voice = TtsEngine.id_to_model( idx )
        name = voice[0]
        return name if name else '???'

    @staticmethod
    def id_to_lang( idx:int ) -> str:
        voice = TtsEngine.id_to_model( idx )
        lang = voice[2]
        return lang if lang else 'ja_JP'

    def __init__(self, *, speaker=-1, submit_task = None, talk_callback = None ):
        # 並列処理用
        self.lock:Condition = Condition()
        self._running_future:Future = None
        self._running_future2:Future = None
        self.wave_queue:Queue = Queue()
        self.play_queue:Queue = Queue()
        # 発声中のセリフのID
        self._talk_id: int = 0
        # 音声エンジン選択
        self.speaker = speaker
        # コールバック
        self.executor = None
        self.submit_call = submit_task # スレッドプールへの投入
        self.start_call = talk_callback # 発声開始と完了を通知する
        # pygame初期化済みフラグ
        self.pygame_init:bool = False
        # beep
        self.beep_ch:pygame.mixer.Channel  = None
        # 音声エンジン無効時間
        self._disable_gtts: float = 0.0
        self._disable_openai: float = 0.0
        self._disable_voicevox: float = 0.0
        # VOICEVOXサーバURL
        self._voicevox_url = None
        self._voicevox_port = os.getenv('VOICEVOX_PORT','50021')
        self._voicevox_list = list(set([os.getenv('VOICEVOX_HOST','127.0.0.1'),'127.0.0.1','192.168.0.104','chickennanban.ddns.net']))

        self.sound1 = create_sound( [(440,0.3)] )
        self.sound2 = create_sound( [(329,0.3)] )
        self.sound3 = create_sound( [(329,1.0),(10,0.5),(349,0.5)] )

    def submit_task(self, func ) -> Future:
        if self.submit_call is not None:
            return self.submit_call(func)
        if self.executor is None:
            self.executor:ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4)
        return self.executor.submit( func )

    def cancel(self):
        self._talk_id += 1

    def _get_voicevox_url( self ) ->str:
        if self._voicevox_url is None:
            self._voicevox_url = utils.find_first_responsive_host(self._voicevox_list,self._voicevox_port)
        return self._voicevox_url

    @staticmethod
    def remove_code_blocksRE(markdown_text):
        # 正規表現を使用してコードブロックを検出し、それらを改行に置き換えます
        # ```（コードブロックの開始と終了）に囲まれた部分を検出します
        # 正規表現のパターンは、```で始まり、任意の文字（改行を含む）にマッチし、最後に```で終わるものです
        # re.DOTALLは、`.`が改行にもマッチするようにするフラグです
        pattern = r'```.*?```'
        return re.sub(pattern, '\n', markdown_text, flags=re.DOTALL)

    @staticmethod
    def split_talk_text( text):
        sz = len(text)
        st = 0
        lines = []
        while st<sz:
            block_start = text.find("```",st)
            newline_pos = text.find('\n',st)
            if block_start>=0 and ( newline_pos<0 or block_start<newline_pos ):
                if st<block_start:
                    lines.append( text[st:block_start] )
                block_end = text.find( "```", block_start+3)
                if (block_start+3)<block_end:
                    block_end += 3
                else:
                    block_end = sz
                lines.append( text[block_start:block_end])
                st = block_end
            else:
                if newline_pos<0:
                    newline_pos = sz
                if st<newline_pos:
                    lines.append( text[st:newline_pos] )
                st = newline_pos+1
        return lines

    def add_talk(self, full_text:str, emotion:int = 0 ) -> None:
        talk_id:int = self._talk_id
        for text in TtsEngine.split_talk_text(full_text):
            self.wave_queue.put( (talk_id, text, emotion ) )
        with self.lock:
            if self._running_future is None:
                self._running_future = self.submit_task(self.run_text_to_audio)
    
    def run_text_to_audio(self)->None:
        """ボイススレッド
        テキストキューからテキストを取得して音声に変換して発声キューへ送る
        """
        while True:
            talk_id:int = -1
            text:str = None
            emotion:int = -1
            with self.lock:
                try:
                    talk_id, text, emotion = self.wave_queue.get_nowait()
                except Exception as ex:
                    if not isinstance( ex, Empty ):
                        logger.exception(ex)
                    talk_id=-1
                    text = None
                if text is None:
                    self._running_future = None
                    return
            try:
                if talk_id == self._talk_id:
                    # textから音声へ
                    audio_bytes, tts_model = self._text_to_audio( text, emotion )
                    self._add_audio( talk_id,text,emotion,audio_bytes,tts_model )
            except Exception as ex:
                logger.exception(ex)

    def _add_audio( self, talk_id:int, text:str, emotion:int, audio_bytes: bytes, tts_model:str=None ) -> None:
        self.play_queue.put( (talk_id,text,emotion,audio_bytes,tts_model) )
        with self.lock:
            if self._running_future2 is None:
                self._running_future2 = self.submit_task(self.run_talk)

    @staticmethod
    def __penpenpen( text, default=" " ) ->str:
        if text is None or text.startswith("```"):
            return default # VOICEVOX,OpenAI,gTTSで、エラーにならない無音文字列
        else:
            return text
        
    def _text_to_audio_by_voicevox(self, text: str, emotion:int = 0, lang='ja') -> bytes:
        if self._disable_voicevox>0 and (time.time()-self._disable_voicevox)<180.0:
            return None,None
        sv_url: str = self._get_voicevox_url()
        if sv_url is None:
            self._disable_voicevox = time.time()
            return None,None
        try:
            self._disable_voicevox = 0
            timeout = (5.0,180.0)
            params = {'text': TtsEngine.__penpenpen(text, ' '), 'speaker': self.speaker, 'timeout': timeout }
            s:requests.Session = requests.Session()
            s.mount(f'{sv_url}/audio_query', HTTPAdapter(max_retries=1))
            res1 : requests.Response = requests.post( f'{sv_url}/audio_query', params=params)

            params = {'speaker': self.speaker, 'timeout': timeout }
            headers = {'content-type': 'application/json'}
            res = requests.post(
                f'{sv_url}/synthesis',
                data=res1.content,
                params=params,
                headers=headers
            )
            model:str = TtsEngine.id_to_name(self.speaker)
            # wave形式 デフォルトは24kHz
            return res.content, model
        except requests.exceptions.ConnectTimeout as ex:
            logger.error( f"[VOICEVOX] {type(ex)} {ex}")
        except requests.exceptions.ConnectionError as ex:
            logger.error( f"[VOICEVOX] {type(ex)} {ex}")
        except Exception as ex:
            logger.error( f"[VOICEVOX] {type(ex)} {ex}")
            logger.exception('')
        self._disable_voicevox = time.time()
        return None,None

    def _text_to_audio_by_gtts(self, text: str, emotion:int = 0) -> bytes:
        if self._disable_gtts>0 and (time.time()-self._disable_gtts)<180.0:
            return None,None
        voice = TtsEngine.id_to_model( self.speaker )
        lang = voice[2] if voice else 'ja_JP'
        lang = lang[:2]
        try:
            self._disable_gtts = 0
            tts = gTTS(text=TtsEngine.__penpenpen(text,'!!'), lang=lang,lang_check=False )
            with BytesIO() as buffer:
                tts.write_to_fp(buffer)
                buffer.seek(0)
                # gTTSはmp3で返ってくるので変換
                y, sr = librosa.load(buffer, sr=None)
                # 話速を2倍にする（時間伸縮）
                y_fast = librosa.effects.time_stretch(y, rate=1.5)
                # ピッチを下げる（ここでは半音下げる例）
                n_steps = -1  # ピッチを半音下げる
                y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=n_steps)
                # 音声データをノーマライズする
                rate = 1.0 / np.max(np.abs(y_shifted))
                y_normalized = y_shifted * rate
                wave:bytes = f32_to_wave(y_normalized, sample_rate=sr )
                #wave:bytes = buffer.getvalue()
                del tts
                return wave,f"gTTS[{lang}]"
        except AssertionError as ex:
            if "No text to send" in str(ex):
                return None,f"gTTS[{lang}]"
            logger.error( f"[gTTS] {ex}")
            logger.exception('')
        except requests.exceptions.ConnectTimeout as ex:
            logger.error( f"[gTTS] timeout")
        except Exception as ex:
            logger.error( f"[gTTS] {ex}")
            logger.exception('')
        self._disable_gtts = time.time()
        return None,None

    def get_client(self):
        return OpenAI()

    def _text_to_audio_by_openai(self, text: str, emotion:int = 0) -> bytes:
        if self._disable_openai>0 and (time.time()-self._disable_openai)<180.0:
            return None,None
        try:
            vc:str = "alloy"
            if self.speaker==1001:
                vc = "alloy"
            elif self.speaker==1002:
                vc = "echo"
            elif self.speaker==1003:
                vc = "fable"
            elif self.speaker==1004:
                vc = "onyx"
            elif self.speaker==1005:
                vc = "nova"
            elif self.speaker==1006:
                vc = "shimmer"
            self._disable_openai = 0
            client:OpenAI = self.get_client()
            response:openai._base_client.HttpxBinaryResponseContent = client.audio.speech.create(
                model="tts-1",
                voice=vc,
                response_format="mp3",
                input=TtsEngine.__penpenpen(text,' ')
            )
            # openaiはmp3で返ってくる
            return response.content,f"OpenAI:{vc}"
        except requests.exceptions.ConnectTimeout as ex:
            logger.error( f"[gTTS] timeout")
        except Exception as ex:
            logger.error( f"[gTTS] {ex}")
            logger.exception('')
        self._disable_openai = time.time()
        return None,None

    def _text_to_audio( self, text: str, emotion:int = 0 ) -> bytes:
        if TtsEngine.EOT==text:
            return self.sound2,''
        wave: bytes = None
        model:str = None
        if 0<=self.speaker and self.speaker<1000:
            wave, model = self._text_to_audio_by_voicevox( text, emotion )
        if 1000<=self.speaker and self.speaker<2000:
            wave, model = self._text_to_audio_by_openai( text, emotion )
        if wave is None:
            wave, model = self._text_to_audio_by_gtts( text, emotion )
        return wave,model
        
    def run_talk(self)->None:
        start:bool = False
        while True:
            talk_id:int = -1
            text:str = None
            emotion: int = 0
            audio:bytes = None
            tts_model:str = None
            with self.lock:
                try:
                    talk_id, text, emotion, audio, tts_model = self.play_queue.get_nowait()
                except Exception as ex:
                    if not isinstance( ex, Empty ):
                        logger.exception('')
                    talk_id=-1
                    text = None
                    audio = None
                if text is None:
                    self._running_future2 = None
                    return
            try:
                if talk_id == self._talk_id:
                    # 再生開始通知
                    if self.start_call is not None:
                        self.start_call( text, emotion, tts_model )
                    # 再生処理
                    if audio is not None:
                        if not self.pygame_init:
                            pygame.mixer.pre_init(16000,-16,1,10240)
                            pygame.mixer.quit()
                            pygame.mixer.init()
                            self.pygame_init = True
                        mp3_buffer = BytesIO(audio)
                        pygame.mixer.music.load(mp3_buffer)
                        pygame.mixer.music.play(1,0.0) # 再生回数１回、フェードイン時間ゼロ
                        while not pygame.mixer.music.get_busy():
                            time.sleep(0.1)
                    # 再生終了待ち
                    if audio is not None:
                        if pygame.mixer.music.get_busy():
                            while pygame.mixer.music.get_busy():
                                if talk_id != self._talk_id:
                                    pygame.mixer.music.stop()
                                    break
                                time.sleep(0.2)
                            time.sleep(0.5)
                    # 再生終了通知
                    if self.start_call is not None:
                        self.start_call( None, emotion, tts_model )
                    
            except Exception as ex:
                logger.exception('')

    def play_beep1(self):
        self._play_beep( self.sound1 )

    def play_beep2(self):
        self._play_beep( self.sound2 )

    def play_beep3(self):
        self._play_beep( self.sound3 )

    def _play_beep(self, snd ):
        try:
            if not self.pygame_init:
                pygame.init()
                pygame.mixer.pre_init(16000,-16,1,10240)
                pygame.mixer.quit()
                pygame.mixer.init()
                self.pygame_init = True
            if self.beep_ch is not None:
                self.beep_ch.stop()
            sound = pygame.mixer.Sound( file=BytesIO(snd))
            self.beep_ch:pygame.mixer.Channel = sound.play(fade_ms=1)
            #pygame.time.delay( int(duratin_sec * 1000) )
        except:
            logger.exception('')