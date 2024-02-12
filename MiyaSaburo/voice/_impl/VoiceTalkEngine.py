import sys,os,traceback

from ..stt import RecognizerGoogle, VoiceSplitter, SttEngine
from ..tts import TtsEngine

class VoiceTalkEngine:
    """
    音声会話のためのエンジン。マイクから音声認識と、音声合成を行う
    """
    ST_STOPPED:int = 0
    ST_TALK:int = 10
    ST_TALK_END:int = 11
    ST_LISTEN:int = 20
    ST_LISTEN_END: int = 21
    def __init__(self, *, speaker:int=46, record_samplerate:int=1600 ):
        self._status = VoiceTalkEngine.ST_STOPPED
        self._callback = None
        self.text_buf=[]
        self.text_stat=0
        self.stt:SttEngine = SttEngine( callback=self._stt_callback)
        self.tts:TtsEngine = TtsEngine( speaker=speaker, talk_callback=self._tts_callback)

    def _fn_callback(self, stat:int, *, listen_text=None, talk_text=None, talk_emotion=None, talk_model=None ):
        if stat == VoiceTalkEngine.ST_LISTEN:
            self.tts.play_beep1()
        elif stat == VoiceTalkEngine.ST_LISTEN_END:
            self.tts.play_beep2()
        if self._callback is not None:
            try:
                self._callback( stat, listen_text=listen_text, talk_text=talk_text, talk_emotion=talk_emotion, talk_model=talk_model )
            except:
                traceback.print_exc()
        else:
            if stat == VoiceTalkEngine.ST_LISTEN:
                print( f"[VoiceTalkEngine] listen {listen_text}" )
            elif stat == VoiceTalkEngine.ST_LISTEN_END:
                print( f"[VoiceTalkEngine] listen {listen_text} __EOT__" )
            elif stat == VoiceTalkEngine.ST_TALK:
                print( f"[VoiceTalkEngine] talk {talk_text}" )
            elif stat == VoiceTalkEngine.ST_TALK_END:
                print( f"[VoiceTalkEngine] talk END" )

    def start(self):
        self._status = VoiceTalkEngine.ST_LISTEN
        self.stt.start_recording()

    def stop(self):
        self._status = VoiceTalkEngine.ST_STOPPED
        self.stt.stop_recording()

    def get_recognized_text(self):
        if self.text_stat==3 and len(self.text_buf)>0:
            text = ' '.join(self.text_buf)
            self.text_stat = 0
            return text
        return None

    def _stt_callback(self, start_sec, end_sec, stat, texts ):
        copy_texts = []
        s = -1
        if stat==1:
            print( f"[STT] {start_sec:.3f} - {end_sec:.3f} {stat} START")
            s = VoiceTalkEngine.ST_LISTEN
            copy_texts = self.text_buf = []
        elif stat==2:
            print( f"[STT] {start_sec:.3f} - {end_sec:.3f} {stat} {texts}")
            s = VoiceTalkEngine.ST_LISTEN
            copy_texts = self.text_buf = [t for t in texts]
        elif stat==3:
            print( f"[STT] {start_sec:.3f} - {end_sec:.3f} {stat} {texts} EOT")
            self.text_stat = 3
            s = VoiceTalkEngine.ST_LISTEN_END
            copy_texts = self.text_buf = [t for t in texts]
        self._fn_callback( s, listen_text=copy_texts )

    def _tts_callback(self, text:str, emotion:int, model:str):
        """音声合成からの通知により、再生中は音声認識を止める"""
        if text:
            print( f"[TTS] {text}")
            self._status = VoiceTalkEngine.ST_TALK
            self.stt.set_pause( True )
            self._fn_callback( VoiceTalkEngine.ST_TALK, talk_text=text, talk_emotion=emotion, talk_model=model )
        else:
            print( f"[TTS] stop")
            self._status = VoiceTalkEngine.ST_LISTEN
            self.stt.set_pause( False )
            self._fn_callback( VoiceTalkEngine.ST_TALK_END, talk_text=None )

    def add_talk(self, text ):
        self.stt.set_pause( True )
        self.tts.add_talk( text )