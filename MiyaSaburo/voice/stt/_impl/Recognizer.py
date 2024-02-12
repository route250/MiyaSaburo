import sys,os,traceback,time,json
import numpy as np
import speech_recognition as sr
from .VoskUtil import sound_float_to_int16, NetworkError

dbg_level=1
def dbg_print(lv:int,txt:str):
    if lv>=dbg_level:
        print( txt )

memo= """
    Performs speech recognition on ``audio_data`` (an ``AudioData`` instance), using the Google Speech Recognition API.
    ``audio_data``（``AudioData``インスタンス）に対して音声認識を行い、Google音声認識APIを使用します。

    The Google Speech Recognition API key is specified by ``key``. If not specified, it uses a generic key that works out of the box.
    This should generally be used for personal or testing purposes only, as it **may be revoked by Google at any time**.
    To obtain your own API key, simply following the steps on the `API Keys <http://www.chromium.org/developers/how-tos/api-keys>`__ page
    at the Chromium Developers site. In the Google Developers Console, Google Speech Recognition is listed as "Speech API".
    
    Google音声認識APIキーは、``key``によって指定されます。指定されていない場合、箱から出してすぐに機能する一般的なキーを使用します。
    これは一般的に個人的な目的やテスト目的でのみ使用すべきであり、**いつでもGoogleによって取り消される可能性があります**。
    独自のAPIキーを取得するには、Chromium Developersサイトの`APIキー<http://www.chromium.org/developers/how-tos/api-keys>`__ ページの
    手順に従ってください。Google Developers Consoleでは、Google音声認識は「Speech API」としてリストされています。

    The recognition language is determined by ``language``, an RFC5646 language tag like ``"en-US"`` (US English) or ``"fr-FR"`` (International French),
    defaulting to US English. A list of supported language tags can be found in this `StackOverflow answer <http://stackoverflow.com/a/14302134>`__.
    認識言語は、``"en-US"``（アメリカ英語）や``"fr-FR"``（フランス語国際）など、RFC5646言語タグによって``language``で決定され、デフォルトはアメリカ英語です。
    対応する言語タグのリストは、この`StackOverflowの回答<http://stackoverflow.com/a/14302134>`__ で見つかります。

    不適切な言葉のフィルターレベルは、``pfilter``で調整できます：0 - フィルターなし、1 - 最初の文字のみを表示して残りをアスタリスクで置き換えます。
    デフォルトはレベル0です。

    Returns the most likely transcription if ``show_all`` is false (the default). Otherwise, returns the raw API response as a JSON dictionary.
    ``show_all``がfalseの場合（デフォルト）、最も可能性の高い転写を返します。そうでない場合は、生のAPIレスポンスをJSON辞書として返します。

    Raises a ``speech_recognition.UnknownValueError`` exception if the speech is unintelligible. Raises a ``speech_recognition.RequestError`` exception
    if the speech recognition operation failed, if the key isn't valid, or if there is no internet connection.
    音声が聞き取れない場合は、``speech_recognition.UnknownValueError``例外を発生させます。
    音声認識操作に失敗した場合、キーが無効である場合、またはインターネット接続がない場合は、``speech_recognition.RequestError``例外を発生させます。

    """
class RecognizerGoogle:

    def __init__(self, timeout=None, sample_rate:int=16000, width=2, lang='ja_JP'):
        self.sr:sr.Recognizer = sr.Recognizer()
        if timeout is not None:
            self.sr.operation_timeout = timeout
        self.sample_rate:int = sample_rate
        self.sample_width = width
        self.lang = lang

    def recognizef(self, float_list:list[float], *,timeout=None, retry=None, sample_rate:int=None, lang:str=None  ):
        """音声認識 float配列バージョン"""
        floats = np.array(float_list, dtype=np.float32)
        #intdata = np.int16( floats * 32767 )
        intdata = sound_float_to_int16( floats, scale=0.8, lowcut=0 )
        bytes_data = intdata.tobytes()
        if sample_rate is None:
            sample_rate = self.sample_rate
        audio_data = sr.AudioData( bytes_data, sample_rate, 2 )
        return self._recognize_audiodata( audio_data, timeout=timeout, lang=lang )

    def recognizeb(self, buf:bytes, *, timeout=None, retry=None, sample_rate:int=None, sample_width:int = None, lang:str=None ):
        if sample_rate is None:
            sample_rate = self.sample_rate
        if sample_width is None:
            sample_width = self.sample_width
        lang = self.lang
        audio_data = sr.AudioData( buf, sample_rate, sample_width)
        return self._recognize_audiodata( audio_data, lang=lang )
        
    def _recognize_audiodata(self, audio_data:sr.AudioData, *, timeout=None, retry=None, lang:str=None ):
        if lang is None:
            lang = self.lang
        if retry is None:
            retry = 3
        try:
            for trycount in range(0, retry+1):
                before_timeout = self.sr.operation_timeout
                try:
                    if timeout is not None:
                        self.sr.operation_timeout=timeout
                    actual_result = self.sr.recognize_google(audio_data, language=lang, show_all=True )
                    if not isinstance(actual_result,dict) or len(actual_result.get('alternative',[]))<1 or not actual_result.get('final',False):
                        print(f"ERROR:actual_result:{json.dumps(actual_result,ensure_ascii=False)}")
                        raise sr.exceptions.UnknownValueError('invalid result data')
                except sr.exceptions.UnknownValueError as ex:
                    if trycount>0:
                        return ''
                    dbg_print(0,f"[RECG] try{trycount} error response {ex}")
                    continue
                except sr.exceptions.RequestError as ex:
                    if trycount==retry:
                        raise ex
                    dbg_print(0,f"[RECG] try{trycount} error response {ex}")
                    continue
                finally:
                    self.sr.operation_timeout = before_timeout
                break
            if not actual_result:
                dbg_print(0,f"[RECG] abort or no result")
                return None
            data=json.dumps( actual_result, indent=2, ensure_ascii=False )

            if isinstance(actual_result,list) and len(actual_result)==0:
                dbg_print(0,f"[RECG] abort or no result")
                return None
            elif isinstance(actual_result, dict) and len(actual_result.get("alternative", []))>0:
                if "confidence" in actual_result["alternative"]:
                    # return alternative with highest confidence score
                    best_hypothesis = max(actual_result["alternative"], key=lambda alternative: alternative["confidence"])
                else:
                    # when there is no confidence available, we arbitrarily choose the first hypothesis.
                    best_hypothesis = actual_result["alternative"][0]
                if "transcript" in best_hypothesis:
                    # https://cloud.google.com/speech-to-text/docs/basics#confidence-values
                    # "Your code should not require the confidence field as it is not guaranteed to be accurate, or even set, in any of the results."
                    confidence = best_hypothesis.get("confidence", 0.5)
                    final_text = best_hypothesis["transcript"]
                    final_len = len(final_text)
                    if final_len<3 or confidence < 0.6:
                        # ほぼノイズでしょう
                        dbg_print(0, f"[RECG] noize {final_text} {confidence}")
                        return ''
                    else:
                        if final_len<5:
                            dbg_print(0, f"[RECG] USER/NOIZE {final_text} {confidence}")
                            return ''
                        else:
                            dbg_print(0, f"[RECG] USER {final_text} {confidence}")
                            return final_text

            else:
                dbg_print(0,f"[RECG] error response {actual_result}")

        except sr.exceptions.RequestError as ex:
            dbg_print(0,f"[RECG] error response {ex}")
            raise NetworkError(ex)
        except sr.exceptions.UnknownValueError as ex:
            dbg_print(0,f"[RECG] error response {ex}")
            raise NetworkError(ex)
        except Exception as ex:
            traceback.print_exc()
            raise ex
        return None

