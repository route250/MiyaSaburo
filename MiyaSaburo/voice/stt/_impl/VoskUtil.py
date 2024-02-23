import sys, os, re
from pathlib import Path
import vosk
from vosk import Model, KaldiRecognizer, SpkModel
import numpy as np

import logging
logger = logging.getLogger('voice')

class NetworkError(Exception):
    def __init__(self, *args):
        super().__init__(*args)

def sound_normalize( audio_data, *, scale:float=0.8, lowcut:float=0 ):
    if isinstance(audio_data,np.ndarray):
        if audio_data.dtype == np.float32:
            # 音声データの正規化
            max_abs_value = np.max(np.abs(audio_data))
            if lowcut<=0 or max_abs_value>=lowcut:
                return audio_data / (max_abs_value * scale)
            else:
                return audio_data * 0
        if audio_data.dtype == np.int16:
            max_abs_value = np.max(np.abs(audio_data))
            iscale =int(32767*scale)
            ilowcut = int(32767*lowcut)
            if ilowcut<=0 or max_abs_value>=ilowcut:
                return audio_data / (max_abs_value * iscale)
            else:
                return audio_data * 0
    return audio_data

def sound_float_to_int16( audio_data, *, scale:float=0.8, lowcut:float=0 ):
    """音声の正規化とint16化"""
    if not isinstance(audio_data,np.ndarray) or audio_data.dtype != np.float32:
        return audio_data
    max_abs_value = np.max(np.abs(audio_data))
    if lowcut<=0 or max_abs_value>=lowcut:
        rate = max_abs_value * scale
        xfloat = audio_data / rate
        xfloat1 = xfloat * 32767
        xint16 = xfloat1.astype(np.int16)
        return xint16
    else:
        return np.zeros( len(audio_data), dtype=np.int16 )

def get_vosk_model( lang:str='ja' ) ->Model:
    # search and load model
    for pattern in [ rf"vosk-model-{lang}",rf"vosk-model-small-{lang}"]:
        for directory in vosk.MODEL_DIRS:
            if directory is None or not Path(directory).exists():
                continue
            model_file_list = [ f for f in os.listdir(directory) if os.path.isdir(f) ]
            model_file = [model for model in model_file_list if re.match(pattern, model)]
            if len(model_file) == 0:
                continue
            try:
                return Model(str(Path(directory, model_file[0])))
            except:
                logger.exception(f"can not load vosk model {model_file[0]}")

    # cleanup zip file when download error?
    try:
        for directory in vosk.MODEL_DIRS:
            if directory is None or not Path(directory).exists():
                continue
            for f in os.listdir(directory):
                ff = os.path.join(directory,f)
                if os.path.isfile(ff) and re.match(r"vosk-model(-small)?-{}.*\.zip".format(lang), f):
                    logger.error(f"remove vosk model {ff}")
                    os.unlink(ff)
    except Exception as ex:
        logger.exception('cleanup??')

    # download model
    try:
        m:Model = Model(lang=lang)
        return m
    except Exception as ex:
        logger.exception(f"ERROR:can not load vosk model {ex}")
    return None

def get_vosk_spk_model(m:Model=None):
    for directory in vosk.MODEL_DIRS:
        if directory is None or not Path(directory).exists():
            continue
        model_file_list = os.listdir(directory)
        model_file = [model for model in model_file_list if re.match(r"vosk-model-spk-", model)]
        if model_file != []:
            return SpkModel(str(Path(directory, model_file[0])))
        
    p:str = m.get_model_path('vosk-model-spk-0.4',None) if m is not None else None
    if p is not None:
        return SpkModel( p )
    return None