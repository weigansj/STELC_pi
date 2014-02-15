#!/usr/bin/python

from STELC_Display import *
import STELC_Recorder as sR
import STELC_Scheduler as sS
import STELC_Uploader as sU
import threading
import time

# LOOP_DELAY from STELC_DISPLAY is the delay between display update loops
# LOOP_DELAY = 0.2

# seconds before end of recording to start counting down instead of up
# not implimenting this because the measure of limeLeft is jumpy based
# on record chunck size
#RECORD_END_WARNING = 600
#RECORD_END_WARNING = 20

# default record time if none given
RECORD_SECONDS_DEFAULT = 10800
#RECORD_SECONDS_DEFAULT = 40
DEBUG = 1
  
class Controller(threading.Thread):
  """
  This is for creating a STELC specific thread for containing and
  controlling the display.  This is where the display triggered methods go
  And of course needs to communicate with a recorder thread
  """
  def __init__(self,recorder,scheduler,uploader):
    self.recorder = recorder
    self.scheduler = scheduler
    self.uploader = uploader
    self.display = Display()
    self.display.status.message = DEFAULT_STATUS
    # create a namespace dictionary for the action methods
    gd = {}
    for key in dir(self):
      if hasattr(self,key): 
        gd[key] = getattr(self,key)
    # add queries for query block
    self.display.query.addQuery(
      Query("Record?",[("Yes",8,False,Action('record()',gd)),
                       ("No",12,False,Action('pass',gd))],defaultResponse=0
           ),makeDefault=True
    )
    self.recordQueryNum = 0
    self.display.query.addQuery(
      Query("Cancel?",[("Yes",8,True,Action('cancel()',gd)),
                       ("No",12,False,Action('pass',gd))],defaultResponse=1
           ),makeDefault=False
    )
    self.cancelQueryNum = 1
    # init parent method
    threading.Thread.__init__(self)
    # add events
    self._stop_ = threading.Event()
    self._clear_ = threading.Event()
    self._cancel_ = threading.Event()
    self._recording_ = threading.Event()
    self._converting_ = threading.Event()
    self._uploading_ = threading.Event()

  def clearAll(self,but=None):
    for a in self.__dict__:
      if (a[0] == '_' and a[-1] == '_' and a != but and
          isinstance(self.__dict__[a],threading._Event)):
        self.__dict__[a].clear()

  def showAll(self):
    for a in self.__dict__:
      if (a[0] == '_' and a[-1] == '_' and 
          isinstance(self.__dict__[a],threading._Event)):
        print a,self.__dict__[a].isSet()

  def start(self):
    self.recorder.start()
    self.scheduler.start()
    self.uploader.start()
    self.display.on()
    self.thread = threading.Thread(None, self.run, None, (), {})
    self.thread.start()

  def stop(self):
    self._stop_.set()
    self.display.off()

  def stopped(self):
    return self._stop_.isSet()

  def cancel(self):
    """
    Called when a cancel is requested from the display
    """
    if self.recording():
      # if the controller thinks we are recording then stop
      self.recorder.stopRecording()
    # TODO hand off to next step here?
    self.clearAll()
    self.idle()
    print 'cancel method'

  def record(self, recordSeconds = RECORD_SECONDS_DEFAULT):
    """
    Called when requested to record
    """
    self.clearAll()
    # set the controllers recording event
    self._recording_.set()
    # set up and start the recoring in the recorder thread
    self.recorder.setRecordSeconds(recordSeconds)
    self.recorder.setFilename()
    self.recorder.startRecording()
    # wait untill the recording actually starts
    # TODO this is risky because I do not want to block the display update
    self.recorder._recording_.wait()
    # update the display
    self.display.time.deltaStart = time.time()
    self.display.update(PROCESS)
    self.display.query.setDefaultQuery(self.cancelQueryNum)
    self.display.query.clearMessage()
    print 'record method'

  def recording(self):
    """
    Called while recording is running (called from conrtroller run() loop)
    """
    self.display.status.message = "recording..."
    # not implimenting this since timLeft() is jumpy based on chunk size
    #if self.recorder.timeLeft() < RECORD_END_WARNING:
    #  self.display.time.deltaStart = time.time() + self.recorder.timeLeft()
    #  if DEBUG: print "countdown %s" % self.recorder.timeLeft()
    if not self.recorder.recordStreamActive():
      self.recorder.stopRecording()
      # TODO hand off to next step here?
      self.clearAll()
      self.idle()

  def convert(self):
    """
    Called when requested to convert
    """
    self.clearAll()
    self._converting_.set()
    self.display.time.deltaStart = time.time()
    self.display.update(PROCESS)
    self.display.query.setDefaultQuery(self.cancelQueryNum)
    self.display.query.clearMessage()
    print 'convert method'

  def converting(self):
    """
    Called while converting is running (called from conrtroller run() loop)
    """
    self.display.status.message = "converting..."

  def upload(self):
    """
    Called when requested to upload
    """
    self.clearAll()
    self._uploading_.set()
    self.display.time.deltaStart = time.time()
    self.display.update(PROCESS)
    self.display.query.setDefaultQuery(self.cancelQueryNum)
    print 'upload method'

  def uploading(self):
    """
    Called while uploading is running (called from conrtroller run() loop)
    """
    self.display.status.message = "uploading..."

  def idle(self):
    """
    Called when we want to return to idle
    """
    self.clearAll()
    self.display.status.message = DEFAULT_STATUS
    self.display.time.deltaStart = 0
    self.display.update(IDLE)
    self.display.query.setDefaultQuery(self.recordQueryNum)

  def run(self):
    while not self.stopped():
      if self._clear_.isSet(): self.clearAll()
      elif self._cancel_.isSet(): self.cancel()
      elif self._recording_.isSet(): self.recording()
      elif self._converting_.isSet(): self.converting()
      elif self._uploading_.isSet(): self.uploading()
        
      self.display.update()
      time.sleep(LOOP_DELAY)


class Recorder(threading.Thread):
  """
  This if for creating a STELC specific thread for containing and
  controlling the recorder.
  """
  def __init__(self):
    # init parent method
    threading.Thread.__init__(self)
    # add events
    # stop the thread
    self._stop_ = threading.Event()
    # clear all threading events
    self._clear_ = threading.Event()
    # start recording
    self._startRecording_ = threading.Event()
    # recording in process
    self._recording_ = threading.Event()
    # pause recording
    self._pauseRecording_ = threading.Event()
    # stop recording
    self._stopRecording_ = threading.Event()
    # default attrributes
    self.record = None
    self.waveFilename = 'test.wav'
    self.recordSeconds = 20
  
  def clearAll(self,but=None):
    for a in self.__dict__:
      if (a[0] == '_' and a[-1] == '_' and a != but and
          isinstance(self.__dict__[a],threading._Event)):
        self.__dict__[a].clear()

  def showAll(self):
    for a in self.__dict__:
      if (a[0] == '_' and a[-1] == '_' and 
          isinstance(self.__dict__[a],threading._Event)):
        print a,self.__dict__[a].isSet()

#  def start(self):
#    self.thread = threading.Thread(None, self.run, None, (), {})
#    self.thread.start()
#
  def stop(self):
    self._stop_.set()

  def stopped(self):
    return self._stop_.isSet()

  def setFilename(self, *name):
    """
    return the current recording filename, or set a new one
    """
    if name:
      if self.recroding(): raise sR.RecordingError, 'Can not set new filename'
      else: self.waveFilename  = name[0]
    else:
      if not self.recording(): 
        self.waveFilename = time.strftime('STELC_%Y%m%d-%H%M.wav',
                                          time.localtime())
    return self.waveFilename

  def setRecordSeconds(self, *sec):
    """
    return or set the record time
    """
    if sec:
      if self.recording(): raise sR.RecordingError, 'Can not set record time'
      else: self.recordSeconds = sec[0]
    return self.recordSeconds

  def timeLeft(self):
    """
    return the time left in the recording
    """
    return self.record.timeLeft
    
  def recording(self):
    return self._recording_.isSet()

  def recordStreamActive(self):
    if self.record and self.recording():
      return self.record.stream.is_active()
    elif not self.record:
      raise sR.RecordingError, 'no active recording instance, thus no active stream'
    else:
      raise threading.ThreadingError, '_recording_ event not set'


  def startRecording(self):
    """
    create and start a new Record instance with the current settings
    """
    self.record = sR.Record(recordSeconds = self.recordSeconds,
                            waveFilename = self.waveFilename)
    self.record.start()
    self._recording_.set()

  def pauseRecording(self):
    """
    pause the current recording, this just stops the wave file output
    the thread still needs to think it is recording
    """
    if self.record and self.recording():
      self.record.pause()
    elif not self.record:
      raise sR.RecordingError, 'can not pause; no active recording instance'
    else:
      raise threading.ThreadingError, 'can not pause; _recording_ event not set'

  def stopRecording(self):
    """
    stop a recording, delete the instance and reset to None
    """
    if self.record and self.recording():
      # stop recording
      self.record.stop()
      # delete and reset the instance
      del self.record
      self.record = None
      # clear event
      self._recording_.clear()
    elif not self.record:
      raise sR.RecordingError, 'can not stop; no active recording instance'
    else:
      raise threading.ThreadingError, 'can not stop; _recording_ event not set'
  
  def run(self):
    while not self.stopped():
      if self._clear_.isSet(): self.clearAll()
      elif self._stopRecording_.isSet(): self.stopRecording()
      elif self._pauseRecording_.isSet(): self.pauseRecording()
      elif self._startRecording_.isSet(): self.startRecording()
      time.sleep(LOOP_DELAY)


class Scheduler(threading.Thread):
  def __init__(self):
    # init parent method
    threading.Thread.__init__(self)
    # add events
    # stop the thread
    self._stop_ = threading.Event()
    # clear all threading events
    self._clear_ = threading.Event()
  
  def clearAll(self,but=None):
    for a in self.__dict__:
      if (a[0] == '_' and a[-1] == '_' and a != but and
          isinstance(self.__dict__[a],threading._Event)):
        self.__dict__[a].clear()

  def showAll(self):
    for a in self.__dict__:
      if (a[0] == '_' and a[-1] == '_' and 
          isinstance(self.__dict__[a],threading._Event)):
        print a,self.__dict__[a].isSet()

  def stop(self):
    self._stop_.set()

  def stopped(self):
    return self._stop_.isSet()

  def run(self):
    while not self.stopped():
      if self._clear_.isSet(): self.clearAll()
      time.sleep(LOOP_DELAY)


class Uploader(threading.Thread):
  def __init__(self):
    # init parent method
    threading.Thread.__init__(self)
    # add events
    # stop the thread
    self._stop_ = threading.Event()
    # clear all threading events
    self._clear_ = threading.Event()
  
  def clearAll(self,but=None):
    for a in self.__dict__:
      if (a[0] == '_' and a[-1] == '_' and a != but and
          isinstance(self.__dict__[a],threading._Event)):
        self.__dict__[a].clear()

  def showAll(self):
    for a in self.__dict__:
      if (a[0] == '_' and a[-1] == '_' and 
          isinstance(self.__dict__[a],threading._Event)):
        print a,self.__dict__[a].isSet()

  def stop(self):
    self._stop_.set()

  def stopped(self):
    return self._stop_.isSet()

  def run(self):
    while not self.stopped():
      if self._clear_.isSet(): self.clearAll()
      time.sleep(LOOP_DELAY)
      

if __name__ == '__main__':
  r = Recorder()
  s = Scheduler()
  u = Uploader()
  c = Controller(r,s,u)
  c.start()
