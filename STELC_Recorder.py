#!/usr/bin/python

import os,sys,time
import subprocess
import pyaudio
import wave

#recout = open('test_rec.out','w')
#recerr = open('test_rec.err','w')
#rec = subprocess.Popen(
#  ['/usr/bin/sox',
#   '-t','alsa',
#   '-c','1',
#   '-r','48k',
#   '-e','signed',
#   '-b','16',
#   '-S',
#   '-d',
#   '/home/pi/STELC_record/test_rec.wav',
#   'trim','0','0:10'],
#  bufsize=-1,
#  stdout=subprocess.PIPE,
#  stderr=subprocess.PIPE,
#  universal_newlines=True,
#  close_fds=True)
#
#while rec.poll() == None:
#  line = rec.stderr.readline()
#  while line:
#    recerr.write(line)
#    recerr.flush()
#    line = rec.stderr.readline()
#
#recout.writelines(rec.stdout.readlines())
#print rec.poll()

# 65536 correspondes to about 1.3 sec between callbacks
# but is also helps to minimize Input Overflows
CHUNK = 65536
#CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
RECORD_SECONDS = 5400
#RECORD_SECONDS = 20
WAVE_OUTPUT_FILENAME = "test_rec.wav"
COUNTER = {'InputUnderflow':0,'InputOverflow':0,'OutputUnderflow':0,'OutputOverflow':0,'PrimingOutput':0}
END_STREAM_TIME = 0

p = pyaudio.PyAudio()
DEVICE_INDEX = p.get_default_input_device_info()['index']

def callback(in_data, frame_count, time_info, status):
  """
  callback for pyaudio stream
  """
  #print frame_count,time_info['input_buffer_adc_time'],time_info['current_time'],time_info['output_buffer_dac_time'],status
  if status & pyaudio.paInputUnderflow: COUNTER['InputUnderflow'] += 1
  if status & pyaudio.paInputOverflow: COUNTER['InputOverflow'] += 1
  if status & pyaudio.paOutputUnderflow: COUNTER['OutputUnderflow'] += 1
  if status & pyaudio.paOutputOverflow: COUNTER['OutputOverflow'] += 1
  if status & pyaudio.paPrimingOutput: COUNTER['PrimingOutput'] += 1
  returnStatus = pyaudio.paContinue
  #print START+RECORD_SECONDS,time_info['current_time']
  if END_STREAM_TIME < time_info['current_time']:
    returnStatus = pyaudio.paComplete
  wf.writeframes(in_data)
  return (None, returnStatus)

stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=DEVICE_INDEX,
                frames_per_buffer=CHUNK,
                stream_callback=callback)

wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
wf.setnchannels(CHANNELS)
wf.setsampwidth(p.get_sample_size(FORMAT))
wf.setframerate(RATE)

print("* recording")


END_STREAM_TIME = stream.get_time() + RECORD_SECONDS
stream.start_stream()

while stream.is_active():
  time.sleep(0.5)
  
print("* done recording")
stream.stop_stream()
stream.close()
wf.close()

p.terminate()

for key in COUNTER.keys():
  print key,COUNTER[key]




