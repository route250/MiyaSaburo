import sys,os,traceback

from ..stt import RecognizerGoogle, VoiceSplitter, SttEngine
from ..tts import TtsEngine

import logging
logger = logging.getLogger('voice')

class VoiceTalkEngine:
    EOT:str = TtsEngine.EOT
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
        self.text_confidence = 1.0
        self.text_stat=0
        self.stt:SttEngine = SttEngine( callback=self._fn_stt_callback)
        self.tts:TtsEngine = TtsEngine( speaker=speaker, talk_callback=self._tts_callback)

    def _fn_callback(self, stat:int, *, listen_text=None, confidence=None, talk_text=None, talk_emotion=None, talk_model=None ):
        if stat == VoiceTalkEngine.ST_LISTEN:
            self.tts.play_beep1()
        elif stat == VoiceTalkEngine.ST_LISTEN_END:
            self.tts.play_beep2()

        if self._callback is not None:
            try:
                self._callback( stat, listen_text=listen_text, confidence=None, talk_text=talk_text, talk_emotion=talk_emotion, talk_model=talk_model )
            except:
                logger.exception('')
        else:
            if stat == VoiceTalkEngine.ST_LISTEN:
                logger.info( f"[VoiceTalkEngine] listen {listen_text} {confidence}" )
            elif stat == VoiceTalkEngine.ST_LISTEN_END:
                logger.info( f"[VoiceTalkEngine] listen {listen_text} {confidence} __EOT__" )
            elif stat == VoiceTalkEngine.ST_TALK:
                logger.info( f"[VoiceTalkEngine] talk {talk_text}" )
            elif stat == VoiceTalkEngine.ST_TALK_END:
                logger.info( f"[VoiceTalkEngine] talk END" )

    def start(self):
        self._status = VoiceTalkEngine.ST_LISTEN
        self.stt.start_recording()

    def stop(self):
        self._status = VoiceTalkEngine.ST_STOPPED
        self.stt.stop_recording()

    def get_recognized_text(self):
        if self.text_stat==3:
            self.text_stat = 0
            if len(self.text_buf)>0:
                text = ' '.join(self.text_buf)
                confs = self.text_confidence
                return text, confs
        return None,None

    def _fn_stt_callback(self, start_sec, end_sec, stat, texts, confidence ):
        copy_texts = []
        copy_confidence = 1.0
        s = -1
        if stat==1:
            logger.info( f"[STT] {start_sec:.3f} - {end_sec:.3f} {stat} START")
            s = VoiceTalkEngine.ST_LISTEN
            copy_texts = self.text_buf = []
            copy_confidence = 1.0
        elif stat==2:
            logger.info( f"[STT] {start_sec:.3f} - {end_sec:.3f} {stat} {texts} {confidence}")
            s = VoiceTalkEngine.ST_LISTEN
            copy_texts = self.text_buf = [t for t in texts]
            copy_confidence = self.text_confidence = confidence
        elif stat==3:
            logger.info( f"[STT] {start_sec:.3f} - {end_sec:.3f} {stat} {texts} {confidence} EOT")
            self.text_stat = 3
            s = VoiceTalkEngine.ST_LISTEN_END
            copy_texts = self.text_buf = [t for t in texts]
            copy_confidence = self.text_confidence = confidence
        self._fn_callback( s, listen_text=copy_texts, confidence=copy_confidence )

    def _tts_callback(self, text:str, emotion:int, model:str):
        """音声合成からの通知により、再生中は音声認識を止める"""
        if text:
            logger.info( f"[TTS] {text}")
            self._status = VoiceTalkEngine.ST_TALK
            self.stt.set_pause( True )
            self._fn_callback( VoiceTalkEngine.ST_TALK, talk_text=text, talk_emotion=emotion, talk_model=model )
        else:
            logger.info( f"[TTS] stop")
            self._status = VoiceTalkEngine.ST_LISTEN
            self.stt.set_pause( False )
            self._fn_callback( VoiceTalkEngine.ST_TALK_END, talk_text=None )

    def add_talk(self, text ):
        self.stt.set_pause( True )
        self.tts.add_talk( text )