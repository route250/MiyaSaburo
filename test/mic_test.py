
import time
import numpy as np
import sounddevice as sd

#{
#  'name': 'Microsoft Sound Mapper - Input', 'index': 0, 'hostapi': 0,
#  'max_input_channels': 2, 'max_output_channels': 0,
#  'default_low_input_latency': 0.09, 'default_low_output_latency': 0.09, 'default_high_input_latency': 0.18, 'default_high_output_latency': 0.18,
# 'default_samplerate': 44100.0
#}

printshape=False
buffer=[]
buffer0=[]
buffer1=[]
def _fn_audio_callback( data,frame,time,state ):
    global printshape
    if not printshape:
        printshape=True
        print( f"SHAPE {len(data.shape)} {data.shape} {data.dtype}")
    if len(data.shape)==1:
        buffer.append(data.copy())
    else:
        buffer.append(data[:,0].copy())

def main():

    n1 = np.array( [[1,11],[2,12],[3,13]])
    n2 = np.array( [[4,14],[5,15],[6,16]])
    n12 = np.concatenate( [n1,n2])
    print(n12)
    nx1 = n12[:,1]
    print(nx1)

    samplerate=16000
    bs=int(samplerate*0.2)
    devname=0
    channels=None
    audioinput = sd.InputStream( samplerate=samplerate, blocksize=bs, device=devname, channels=channels, callback=_fn_audio_callback )
    #audioinput = sd.InputStream( callback=_fn_audio_callback )
    print( f"録音スタート")
    audioinput.start()
    time.sleep(5)
    audioinput.stop()
    print( f"録音ストップ" )
    f32data = np.concatenate(buffer)
    print( f"audio {f32data.shape}")
    f32data2= f32data#.reshape( [len(f32data),1] )
    #f32data2 = np.insert( f32data2, 1, f32data, axis=1)
    print( f"audio {f32data2.shape}")
    print( f"再生スタート" )
    sd.play( f32data2, samplerate=samplerate, blocking=True)
    print( f"再生ストップ" )

def record_and_play(duration=5, sample_rate=44100):
    # 録音
    print("録音開始...")
    recorded_data = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=2, dtype=np.float32)
    sd.wait()  # 録音が終わるまで待機
    print("録音終了")

    print( sd.default.input )
    # 再生
    print("再生開始...")
    sd.play(recorded_data, samplerate=sample_rate)
    sd.wait()  # 再生が終わるまで待機
    print("再生終了")

if __name__=="__main__":
    main()
    #recoard_and_play_is()
    #record_and_play()