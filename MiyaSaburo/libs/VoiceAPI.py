
import requests
import json
import time
from io import BytesIO
from gtts import gTTS

class VoiceAPI:
    VoiceList = [
        ( "gTTS[ja_JP]", -1, 'ja_JP' ),
        ( "gTTS[en_US]", -1, 'en_US' ),
        ( "gTTS[en_GB]", -1, 'en_GB' ),
        ( "gTTS[fr_FR]", -1, 'fr_FR' ),
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
        ( "VOICEVOX:もち子(cv 明日葉よもぎ)[ノーマル]", 20, 'ja_JP' ),
    ]
    def __init__(self):
        self.speaker = -1

    def _post_audio_query(self, text: str) -> dict:
        params = {'text': text, 'speaker': self.speaker}
        res : requests.Response = requests.post('http://localhost:50021/audio_query', params=params)
        res.content
        return res.json()

    def _post_synthesis(self, audio_query_response: dict) -> bytes:
        params = {'speaker': self.speaker}
        headers = {'content-type': 'application/json'}
        audio_query_response_json = json.dumps(audio_query_response)
        res = requests.post(
            'http://localhost:50021/synthesis',
            data=audio_query_response_json,
            params=params,
            headers=headers
        )
        return res.content

    def _post_audio_query_b(self, text: str) -> bytes:

        params = {'text': text, 'speaker': self.speaker}
        res1 : requests.Response = requests.post('http://localhost:50021/audio_query', params=params)

        params = {'speaker': self.speaker}
        headers = {'content-type': 'application/json'}
        res = requests.post(
            'http://localhost:50021/synthesis',
            data=res1.content,
            params=params,
            headers=headers
        )
        return res.content

    def text_to_audio( self, text: str, lang='ja' ) -> bytes:
        if self.speaker<0:
            tts = gTTS(text=text, lang=lang,lang_check=False )
            with BytesIO() as buffer:
                tts.write_to_fp(buffer)
                mp3 = buffer.getvalue()
                del tts
                return mp3
        else:
            # start1 = int(time.time()*1000)
            # req_param: dict = self._post_audio_query(text)
            # start2 = int(time.time()*1000)
            # wave: bytes = self._post_synthesis( req_param )
            # start3 = int(time.time()*1000)
            # print(f"[VOICEVOX] {start2-start1} {start3-start2}")
            start1 = int(time.time()*1000)
            wave: bytes = self._post_audio_query_b( text )
            start3 = int(time.time()*1000)
            print(f"[VOICEVOX] {start3-start1}")
            return wave