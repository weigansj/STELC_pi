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
DEBUG=0

class RecordingError(Exception):
  pass

class Record:
  """
  Instantiating this class opens a new stream and WAV filename
  The start method is used to start the recording, and stop to stop it
  The chunk, inputFormat, inputChannels, and samplingRate can take some
  fiddling to get to work depending on the audio recording device.
  May also have to fiddle with /etc/modprobe.d/alsa-base.conf and
  /etc/asound.conf to get the right driver loaded in the right way.
  Also /etc/security/limits.d/audio.conf if you want
  to enable realtime permissions.
  """
  # 65536 correspondes to about 1.3 sec between callbacks
  # but is also helps to minimize Input Overflows
  chunk = 65536
  #chunk = 1024
  inputFormat = pyaudio.paInt16
  inputChannels = 1
  samplingRate = 48000
  errorCounter = {'InputUnderflow':0,
                   'InputOverflow':0,
                   'OutputUnderflow':0,
                   'OutputOverflow':0,
                   'PrimingOutput':0}

  def __init__(self,recordSeconds=10,waveFilename="test_rec.wav",blocking=False):
    """
    load PyAudio, create stream, and open wav file
    takes recordSeconds for the recording length
    and waveFilename for the wav file which will be opened
    default is to run in callback mode, blocking mode does not currently work
    """
    # initialize PortAudio
    self.p = pyaudio.PyAudio()
    # det default recording device
    self.devIndex = self.p.get_default_input_device_info()['index']
    # set callback or None for blocking mode
    # blocking mode does not work at this time
    self.blocking = blocking
    callback = not self.blocking and self.callback or None
    # set wave filename and recording time
    self.waveFilename = waveFilename
    self.recordSeconds = recordSeconds
    # open the stream, but do not start it
    self.stream = self.p.open(format=self.inputFormat,
                              channels=self.inputChannels,
                              rate=self.samplingRate,
                              input=True,
                              start=False,
                              input_device_index=self.devIndex,
                              frames_per_buffer=self.chunk,
                              stream_callback=callback)

    # open wave file
    self.wf = wave.open(self.waveFilename, 'wb')
    self.wf.setnchannels(self.inputChannels)
    self.wf.setsampwidth(self.p.get_sample_size(self.inputFormat))
    self.wf.setframerate(self.samplingRate)
    # set tracking flags
    self.endStreamTime = 0
    self.timeLeft = 0
    self.isStarted = False
    self.isPaused = False
    self.isStopped = False
    
  def callback(self, in_data, frame_count, time_info, status):
    """
    callback for pyaudio stream
    """
    # print timing data
    if DEBUG:
      print "%6d frames, %9.3fs adc in, %9.3fs now, %9.3fs dac out" %(
        frame_count,time_info['input_buffer_adc_time'],
        time_info['current_time'],time_info['output_buffer_dac_time'])
    # log errors by type
    if status & pyaudio.paInputUnderflow: self.errorCounter['InputUnderflow'] += 1
    if status & pyaudio.paInputOverflow: self.errorCounter['InputOverflow'] += 1
    if status & pyaudio.paOutputUnderflow: self.errorCounter['OutputUnderflow'] += 1
    if status & pyaudio.paOutputOverflow: self.errorCounter['OutputOverflow'] += 1
    if status & pyaudio.paPrimingOutput: self.errorCounter['PrimingOutput'] += 1
    # set time left
    self.timeLeft = self.endStreamTime-time_info['current_time']
    # print staus and time left
    if DEBUG: print "status = %d, %fs left, start->%s, pause->%s, stop->%s" % (
      status,self.timeLeft,self.isStarted,self.isPaused,self.isStopped)
    # normally Continue recording
    returnStatus = pyaudio.paContinue
    # return Abort if stopped
    if self.isStopped:
      if DEBUG: print "* aborting early"
      returnStatus = pyaudio.paAbort
    # return Complete when designated time runs out
    elif self.endStreamTime < time_info['current_time']:
      returnStatus = pyaudio.paComplete
    # return Continue if paused before time runs out
    elif self.isPaused:
      returnStatus = pyaudio.paContinue
    # write the frame data to the wave file if not Paused
    if not self.isPaused: self.wf.writeframes(in_data)
    # print where we are in the wave file
    if DEBUG: print "wave file position %s" % self.wf.tell()
    return (None, returnStatus)
  
  def start(self):
    """
    Start or restart a pause recording
    note that if the recordSeconds time runs out before
    a pause is restarted the recording will still stop
    """
    if DEBUG: print("* recording")
    # only start the stream and set the time if this is not a restart
    if not self.isPaused:
      self.endStreamTime = self.stream.get_time() + self.recordSeconds
      self.stream.start_stream()
    # set tracking flags
    self.isStarted = True
    self.isPaused = False
    self.isStopped = False
    
  def pause(self):
    """
    a pause method to allow recording to stop and restart
    I can not seem to use self.stream.stop_stream() to do this
    as it seems to freeze the execution
    """
    if DEBUG: print("* paused recording")
    self.isPaused = True

  def stop(self):
    """
    stop stream, close stream and close wave file
    """
    self.isStarted = False
    self.isPaused = False
    self.isStopped = True
    # wait for the callback to return with an
    # paAbort if we are attempting to stop early
    while self.stream.is_active():
      time.sleep(0.1)
    if DEBUG: print("* done recording")
    self.stream.stop_stream()
    self.stream.close()
    self.wf.close()
    self.endStreamTime = 0
    self.timeLeft = 0
    
  def __del__(self):
    """
    stop recording on way out and terminal pyAudio
    """
    if not self.isStopped: self.stop()  
    self.p.terminate()
    if DEBUG:
      for key in self.errorCounter.keys():
        print key,self.errorCounter[key]


if __name__ == '__main__':
  DEBUG = 1
  r = Record(recordSeconds=40)
  r.start()
  time.sleep(10)
  r.pause()
  time.sleep(10)
  r.start()
  time.sleep(10)
  #while r.stream.is_active():
  #  time.sleep(0.5)
  r.stop()
  del r

