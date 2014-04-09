#!/usr/bin/python

from STELC_Display import *
import STELC_Recorder as sR
import STELC_Scheduler as sS
import STELC_UploaderDropbox as sUD
#import STELC_UploaderDropbox as sU
import STELC_UploaderGoogleDrive as sU
import STELC_Converter as sV
import STELC_Copier as sC
import threading
import time,os,re,glob,sys

# LOOP_DELAY from STELC_DISPLAY is the delay between display update loops
# LOOP_DELAY = 0.2

# seconds before end of recording to start counting down instead of up
# not implimenting this because the measure of limeLeft is jumpy based
# on record chunck size
#RECORD_END_WARNING = 600
#RECORD_END_WARNING = 20

# default record time if none given
RECORD_SECONDS_DEFAULT = 60*90
#RECORD_SECONDS_DEFAULT = 40

# string first argument for time.strftime()
WAVE_FILENAME_FORMAT = 'STELC_%Y%m%d-%H%M.wav' # string first argument for time.strftime()
PURGE_RE = 'STELC_[0-9]{8}-[0-9]{4}\.' # regular expression for finding files 
                                       # to purge this needs to match the 
                                       # WAVE_FILENAME_FORMAT

# time HH:MM to daily update the schedule based on the calendar
# (updates also happen after events)
DAILY_UPDATE_TIME = "01:15"
# purge will delete recordings until 
# there is space for the next event * this factor
SPACE_ALLOWANCE_FACTOR = 2.5
# used for indicating progress if needed
PROGRESS_CHARS = ['.','^','>','v','<']

DEBUG = 1
sR.DEBUG = DEBUG
sR.INPUT_FORMAT = sR.pyaudio.paInt16
sR.SAMPLE_SIZE = sR.pyaudio.get_sample_size(sR.INPUT_FORMAT)
sR.INPUT_CHANNELS = 1
sR.SAMPLING_RATE = 48000

sV.DEBUG = DEBUG
sV.CONVERTER = '/usr/bin/sox -S %s %s' 

sU.DEBUG = DEBUG
sUD.DEBUG = DEBUG

sS.DEBUG = DEBUG

sC.DEBUG = DEBUG
sC.PROGRESS_CHARS = PROGRESS_CHARS
sC.COPYCMD = "rsync -Pt --modify-window=2 --include='*.mp3' --include='*.wav' --include='*.log' --exclude='*' ./* %s/STELC_pi/"
  
class Controller(threading.Thread):
  """
  This is for creating a STELC specific thread for containing and
  controlling the display.  This is where the display triggered methods go
  And of course needs to communicate with a recorder thread
  """
  def __init__(self,recorder,scheduler,converter,uploader,copier):
    self.fail = ''
    self.recorder = recorder
    self.scheduler = scheduler
    self.converter = converter
    self.uploader = uploader
    self.copier = copier
    self.display = Display()
    self.display.status.message = DEFAULT_STATUS
    # create a namespace dictionary for the action methods
    gd = {}
    for key in dir(self):
      if hasattr(self,key): 
        gd[key] = getattr(self,key)
    ## add queries for query block
    # record query for manual start recording
    self.display.query.addQuery(
      Query("Record?",[("Yes",8,False,Action('record()',gd)),
                       ("No",12,False,Action('pass',gd))],defaultResponse=0,
                        up=3,down=4 # up leads to Copy down leads to Update
           ),makeDefault=True
    )
    self.recordQueryNum = 0
    # cancel query for stopping uploads or copying
    self.display.query.addQuery(
      Query("Cancel?",[("Yes",8,True,Action('cancel()',gd)),
                       ("No",12,False,Action('pass',gd))],defaultResponse=1
           ),makeDefault=False
    )
    self.cancelQueryNum = 1
    # Stop query for stopping recording
    self.display.query.addQuery(
      Query("Stop?",[("Yes",8,True,Action('cancel()',gd)),
                     ("No",12,False,Action('pass',gd))],defaultResponse=1
           ),makeDefault=False
    )
    self.stopQueryNum = 2
    # Copy query for copying to USB disk
    self.display.query.addQuery(
      Query("Copy?",[("Yes",8,False,Action('copy()',gd)),
                     ("No",12,False,Action('pass',gd))],defaultResponse=0,
                      up=6,down=0 # up or down buttons lead to Record query
           ),makeDefault=False
    )
    self.copyQueryNum = 3
    # Call cancel just to get schedule updates
    self.display.query.addQuery(
      Query("Update?",[("Yes",8,False,Action('cancel()',gd)),
                       ("No",12,False,Action('pass',gd))],defaultResponse=0,
                        up=0,down=4 # up leads to Copy down leads to Update
           ),makeDefault=False
    )
    self.updateQueryNum = 4
    # Can not cancel
    self.display.query.addQuery(
      Query("Please Wait",[("OK",12,False,Action('pass',gd)),]
                         ,defaultResponse=0
           ),makeDefault=False
    )
    self.waitQueryNum = 5
    # Purge old files
    self.display.query.addQuery(
      Query("Purge?",[("Yes",8,True,Action('purge()',gd)),
                      ("No",12,False,Action('pass',gd))],defaultResponse=1,
                      up=6,down=3 # up or down buttons lead to Record query
           ),makeDefault=False
    )
    self.purgeQueryNum = 6
    # init parent method
    threading.Thread.__init__(self)
    # add events
    self._stop_ = threading.Event()
    self._clear_ = threading.Event()
    self._cancel_ = threading.Event()
    self._recording_ = threading.Event()
    self._converting_ = threading.Event()
    self._uploading_ = threading.Event()
    self._copying_ = threading.Event()

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
    self.converter.start()
    self.uploader.start()
    self.copier.start()
    self.display.on()
    self.thread = threading.Thread(None, self.run, None, (), {})
    self.thread.start()

  def stop(self):
    self._stop_.set()
    fail = self.fail
    if self.recorder.stopped(): fail += "r.%s" % self.recorder.fail
    self.recorder.stop()
    if self.scheduler.stopped(): fail += "s.%s" % self.scheduler.fail
    self.scheduler.stop()
    if self.converter.stopped(): fail += "v.%s" % self.converter.fail
    self.converter.stop()
    if self.uploader.stopped(): fail += "u.%s" % self.uploader.fail
    self.uploader.stop()
    if self.copier.stopped(): fail += "c.%s" % self.copier.fail
    self.copier.stop()
    self.fail = fail

  def stopped(self):
    return self._stop_.isSet()

  def run(self):
    while not self.stopped():
      if self._clear_.isSet(): self.clearAll()
      elif self._cancel_.isSet(): self.cancel()
      elif self._recording_.isSet(): self.recording()
      elif self._converting_.isSet(): self.converting()
      elif self._uploading_.isSet(): self.uploading()
      elif self._copying_.isSet(): self.copying()
      elif self.recorder._stop_.isSet(): self.stop()
      elif self.scheduler._stop_.isSet(): self.stop()
      elif self.converter._stop_.isSet(): self.stop()
      elif self.uploader._stop_.isSet(): self.stop()
      elif self.copier._stop_.isSet(): self.stop()
      else: self.checkSchedule()
        
      self.display.update()
      time.sleep(LOOP_DELAY)

    # these run on the way out after a stop was requested
    self.display.fail(self.fail)
    #self.display.off()

  def cancel(self):
    """
    Called when a cancel is requested from the display
    or the natural end of a process
    """
    print 'cancel method'
    if self._recording_.isSet():
      # if the controller thinks we are recording, clear the event and stop
      self._recording_.clear()
      recordedFile = self.recorder.stopRecording()
      # now pass off to the next step
      self.convert(recordedFile)
      #self.upload(recordedFile)
    elif self._converting_.isSet():
      self._converting_.clear()
      convertedFile = self.converter.convertedFile
      # TODO find way to terminate convert
      if DEBUG: print "convert %s complete" % self.converter.progress
      # if this is a scheduled event update the events convert status
      if self.scheduler._event_.isSet():
        self.scheduler.updateItems(converted=True,
                                   convertFmt=self.converter.convertFormat )
      # now pass off to the next step
      self.upload(convertedFile)
    elif self._uploading_.isSet():
      self._uploading_.clear()
      uploadedFile = self.uploader.uploadFile
      # TODO find way to terminate upload
      if DEBUG: print "upload %s complete" % self.uploader.progress
      # if this is a scheduled event update the events upload status
      if self.scheduler._event_.isSet():
        self.scheduler.updateItems(uploaded=True)
        # this marks the end of a scheduled event
        self.scheduler._event_.clear()
        # so we should update the schedule
        self.updateSchedule()
      self.idle()
    elif self._copying_.isSet():
      self._copying_.clear()
      # TODO find way to terminate copy
      if DEBUG: print "copy progress: %s" % self.copier.progress
      self.idle()
    else:
      # update schedule if there was no event
      # as is the case when the Update Query is selected
      self.updateSchedule()
      # go ahead and upload the logs too
      # TODO this is risky because it does not give a status
      self.scheduler.uploadLogs()

  def record(self, recordSeconds = RECORD_SECONDS_DEFAULT):
    """
    Called when requested to record
    """
    self.clearAll()
    # set the controllers recording event
    self._recording_.set()
    # set up and start the recoring in the recorder thread
    self.recorder.setRecordSeconds(recordSeconds)
    fn = self.recorder.setFilename()
    self.recorder.startRecording()
    # wait untill the recording actually starts
    # TODO this is risky because I do not want to block the display update
    self.recorder._recording_.wait()
    # update the display
    self.display.time.deltaStart = time.time()
    self.display.update(PROCESS)
    self.display.query.setDefaultQuery(self.stopQueryNum)
    self.display.query.clearMessage()
    print 'record method'
    # if this is a scheduled event update the events filename
    if self.scheduler._event_.isSet():
      self.scheduler.updateItems(filename=fn)

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
      self.cancel()

  def convert(self,filename):
    """
    Called when requested to convert
    """
    self.clearAll()
    self._converting_.set()
    # do convertion here
    self.converter.convertFile = filename
    self.converter._startConvert_.set()
    while not self.converter._converting_.isSet():
      if DEBUG: "wait for convert to start"
    self.display.time.deltaStart = time.time()
    self.display.update(PROCESS)
    self.display.query.setDefaultQuery(self.waitQueryNum)
    print 'convert method'

  def converting(self):
    """
    Called while converting is running (called from conrtroller run() loop)
    """
    self.display.status.message = "converting..."
    if not self.converter._converting_.isSet():
      self.cancel()
    else:
      self.converter.progress = self.converter.convert.progress
      self.display.status.message = "convert %s" % self.converter.progress

  def upload(self,uploadFile):
    """
    Called when requested to upload
    """
    self.clearAll()
    self._uploading_.set()
    # do the upload here
    self.uploader.uploadFile = uploadFile
    self.uploader._startUpload_.set()
    while not self.uploader._uploading_.isSet():
      if DEBUG: "wait for upload to start"
    #
    self.display.time.deltaStart = time.time()
    self.display.update(PROCESS)
    self.display.query.setDefaultQuery(self.waitQueryNum)
    print 'upload method'

  def uploading(self):
    """
    Called while uploading is running (called from conrtroller run() loop)
    """
    self.display.status.message = "uploading..."
    if not self.uploader._uploading_.isSet():
      self.cancel()
    else:
      # if the upload updates its progress this will be displayed
      # otherwise we can use the standin
      if not self.uploader.upload.progress:
        if not self.uploader.progress in PROGRESS_CHARS:
          self.uploader.progress = PROGRESS_CHARS[0]
        else:
          self.uploader.progress = PROGRESS_CHARS[(PROGRESS_CHARS.index(
                      self.uploader.progress)+1) % len(PROGRESS_CHARS)]
        if DEBUG: print self.uploader.progress
      else:
        self.uploader.progress = self.uploader.upload.progress
      self.display.status.message = "upload %s" % self.uploader.progress

  def copy(self):
    """
    Called when requested to copy
    """
    self.clearAll()
    self._copying_.set()
    # do the copy here
    self.copier._startCopy_.set()
    while not self.copier._copying_.isSet():
      if DEBUG: "wait for copy to start"
    #
    self.display.time.deltaStart = time.time()
    self.display.update(PROCESS)
    self.display.query.setDefaultQuery(self.waitQueryNum)
    print 'copy method'

  def copying(self):
    """
    Called while copy is running (called from conrtroller run() loop)
    """
    self.display.status.message = "copying..."
    if not self.copier._copying_.isSet():
      self.cancel()
    else:
      self.copier.progress = self.copier.copy.progress
      self.display.status.message = "copy  %s" % self.copier.progress

  def checkSchedule(self):
    """
    This is to see if we should start a recording based on the 
    Schedule event attribute, not to find the next event
    """
    # if we are 15 minutes away start the countdown
    if self.scheduler.isNear(15*60):
      self.scheduler._event_.set()
      self.display.time.deltaStart = self.scheduler.getStart()
      self.display.status.message = "record in"
      self.display.update(PROCESS)
    # as soon as it is close to the time start recording
    if self.scheduler.isNear():
      self.scheduler._event_.set()
      # provide the duration when starting record()
      self.record(recordSeconds = self.scheduler.getDuration())

  def updateSchedule(self):
    """
    This is to tell the scheduler to load the next event from the calendar
    """
    self.scheduler._update_.set()

  def purge(self):
    """
    Called when requested to purge old recordings
    """
    self.scheduler._purge_.set()

  def idle(self):
    """
    Called when we want to return to idle
    """
    self.clearAll()
    self.display.status.message = DEFAULT_STATUS
    self.display.time.deltaStart = 0
    self.display.update(IDLE)
    self.display.query.setDefaultQuery(self.recordQueryNum)


class Recorder(threading.Thread):
  """
  This if for creating a STELC specific thread for containing and
  controlling the recorder.
  """
  def __init__(self):
    self.fail = ''
    # init parent method
    threading.Thread.__init__(self)
    # add events
    # stop the thread
    self._stop_ = threading.Event()
    # clear all threading events
    self._clear_ = threading.Event()
    ## start recording
    #self._startRecording_ = threading.Event()
    # recording in process
    self._recording_ = threading.Event()
    ## pause recording
    #self._pauseRecording_ = threading.Event()
    ## stop recording
    #self._stopRecording_ = threading.Event()
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

  def stop(self):
    self._stop_.set()

  def stopped(self):
    return self._stop_.isSet()

  def run(self):
    while not self.stopped():
      if self._clear_.isSet(): self.clearAll()
      #elif self._stopRecording_.isSet(): self.stopRecording()
      #elif self._pauseRecording_.isSet(): self.pauseRecording()
      #elif self._startRecording_.isSet(): self.startRecording()
      time.sleep(LOOP_DELAY)

  def setFilename(self, *name):
    """
    return the current recording filename, or set a new one
    """
    if name:
      if self.recroding(): raise sR.RecordingError, 'Can not set new filename'
      else: self.waveFilename  = name[0]
    else:
      if not self.recording(): 
        self.waveFilename = time.strftime(WAVE_FILENAME_FORMAT,
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
    return the filename that was recorded
    """
    if self.record and self.recording():
      filename = self.setFilename()
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
    return filename


class Scheduler(threading.Thread):
  def __init__(self):
    self.fail = ''
    # init parent method
    threading.Thread.__init__(self)
    # add events
    # stop the thread
    self._stop_ = threading.Event()
    # clear all threading events
    self._clear_ = threading.Event()
    # request update of schedule from calendar
    self._update_ = threading.Event()
    # request purge of old recordings
    self._purge_ = threading.Event()
    # when record is called as a result of a scheduled event
    self._event_ = threading.Event()
    # when an event needs updating back to the calendar
    self._eventUpdate_ = threading.Event()
    # this is created as the start because
    # it needs to store an event
    self.schedule = sS.Schedule()
  
  def start(self):
    # do an update on startup
    self.schedule.connect()
    self.schedule.getNext()
    if DEBUG: print "expected size %d bytes" % self.getExpectedFilesize()
    self.thread = threading.Thread(None, self.run, None, (), {})
    self.thread.start()

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
      elif self._eventUpdate_.isSet(): self.putEvent()
      # if we are in the middle on an event, only eventUpdates are allowed
      elif self._event_.isSet(): pass
      elif self._update_.isSet(): self.updateEvent()
      elif self._purge_.isSet(): self.purgeOld()
      elif time.strftime('%H:%M',time.localtime()) == DAILY_UPDATE_TIME:
        startTime = time.time()
        self.purgeOld()
        self.updateEvent()
        self.uploadLogs()
        # if the update is fast, force it to take a minute
        # so that my daily check only happens once
        endTime = time.time()
        if endTime - startTime <= 60.: time.sleep(60.+startTime-endTime)
      time.sleep(LOOP_DELAY)

  def epicFail(self,fail=''):
    self.fail = fail
    self.stop()

  def getAvailableSpace(self):
    """
    available space on device
    """
    return os.statvfs('.').f_bsize*os.statvfs('.').f_bavail

  def getExpectedFilesize(self):
    """
    expected size of next scheduled recording in bytes
    """
    size = sR.SAMPLE_SIZE*sR.INPUT_CHANNELS*sR.SAMPLING_RATE
    if self.getDuration() > 0: size *= self.getDuration()
    else: size *= RECORD_SECONDS_DEFAULT
    return size

  def updateEvent(self):
    self._update_.clear()
    self.schedule.connect()
    nextEvent = self.schedule.getNext()
    if DEBUG: print nextEvent

  def getStart(self):
    return self.schedule.event['start']

  def getDuration(self):
    return self.schedule.event['duration']

  def isNear(self,howNear=10.*LOOP_DELAY):
    """
    if the time difference is than howNear return true
    howNear default of 10x LOOP_DELAY is for starting
    """
    if (self.schedule.event['duration'] > 0 and 
        self.schedule.event['start'] - time.time() >= 0 and
        self.schedule.event['start'] - time.time() < howNear):
     return True
    else: return False

  def updateItems(self,**status):
    """
      update items in the current events status
    """
    for (key,val) in status.items():
      self.schedule.event['status'][key] = val
    self._eventUpdate_.set()

  def putEvent(self):
    """
    update calendar item description based on event status
    """
    self._eventUpdate_.clear()
    self.schedule.connect()
    self.schedule.putEvent()

  def uploadLogs(self):
    print "*** %s Available Space %d MB" % (time.ctime(),
                                  self.getAvailableSpace())
    sys.stdout.flush()
    sys.stderr.flush()
    for logFile in glob.glob('*.log'):
      if DEBUG: print "upload filename: %s" % logFile
      upload = sUD.Upload()
      upload.upload(logFile)
      del upload

  def purgeOld(self):
    """
    purge old recordings
    """
    self._purge_.clear()
    # get all files recorded and converted  by STELC_pi
    purgeList = filter(lambda x:re.search(PURGE_RE,x),os.listdir('.'))
    # sort based on modification times
    purgeList.sort(cmp=lambda x,y: cmp(os.stat(x).st_mtime,os.stat(y).st_mtime))
    if DEBUG: print purgeList
    # lets take the most recent recording off the table for purging
    purgeList.pop()
    # go through the purge list starting with the oldest
    purgeList.reverse()
    purgeSchedule = sS.Schedule()
    while purgeList:
      if self.getExpectedFilesize()*SPACE_ALLOWANCE_FACTOR > self.getAvailableSpace():
        fileToPurge = purgeList.pop()
        # remove the file
        if DEBUG: print "removing %s" % fileToPurge
        os.remove(fileToPurge)
        # find any events that match this file
        purgeSchedule.connect()
        purgeSchedule.getBy('filename',fileToPurge)
        # mark as purged
        purgeSchedule.event['status']['purged']=True
        # if an id has been assigned it is on calendar and should be updated
        if purgeSchedule.event['id']: purgeSchedule.putEvent()
      else:
        break
    # the only time we will exit this loop normally is if we run out of files
    # and we still do not have enough space on the device
    else: self.epicFail("disk full")
    del purgeSchedule


class Converter(threading.Thread):
  def __init__(self):
    self.fail = ''
    # init parent method
    threading.Thread.__init__(self)
    # add events
    # stop the thread
    self._stop_ = threading.Event()
    # clear all threading events
    self._clear_ = threading.Event()
    # start the convertion
    # I think I will need this here becuase the convertion
    # blocks as opposed the the record.start() above which used the callback
    # withing the STELC_Recorder module
    self._startConvert_ = threading.Event()
    # currently converting
    self._converting_ = threading.Event()
    self.convert = None
    self.convertFormat = 'mp3'
    self.convertFile = ''
    self.convertedFile = ''
    self.progress = '0%'
    self.clip = 0
  
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
      elif self._startConvert_.isSet():
        self._converting_.set()
        self.startConvert()
      elif self._converting_.isSet():
        self.progress = self.convert.progress
        self.clip = self.convert.clip
      time.sleep(LOOP_DELAY)

  def startConvert(self):
    if DEBUG: print "startConvert set filename: %s" % self.convertFile
    self.convert = sV.Convert()
    # clear this flag after the Convert object has been created
    self._startConvert_.clear()
    self.convertedFile = self.convert.convert(self.convertFile,self.convertFormat)
    del self.convert
    self.convert = None
    self._converting_.clear()


class Uploader(threading.Thread):
  def __init__(self):
    self.fail = ''
    # init parent method
    threading.Thread.__init__(self)
    # add events
    # stop the thread
    self._stop_ = threading.Event()
    # clear all threading events
    self._clear_ = threading.Event()
    # start the upload
    # I think I will need this here becuase the upload
    # blocks as opposed the the record.start() above which used the callback
    # withing the STELC_Recorder module
    self._startUpload_ = threading.Event()
    # currently uploading
    self._uploading_ = threading.Event()
    self.upload = None
    self.uploadFile = ''
    self.progress = '0%'
  
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
      elif self._startUpload_.isSet():
        self._uploading_.set()
        self.startUpload()
      elif self._uploading_.isSet():
        self.progress = self.upload.progress
      time.sleep(LOOP_DELAY)

  def startUpload(self):
    if DEBUG: print "startUpload set filename: %s" % self.uploadFile
    self.upload = sU.Upload()
    # clear this flag after the Upload object has been created
    self._startUpload_.clear()
    self.upload.upload(self.uploadFile)
    del self.upload
    self.upload = None
    self._uploading_.clear()


class Copier(threading.Thread):
  def __init__(self):
    self.fail = ''
    # init parent method
    threading.Thread.__init__(self)
    # add events
    # stop the thread
    self._stop_ = threading.Event()
    # clear all threading events
    self._clear_ = threading.Event()
    # start the copy
    self._startCopy_ = threading.Event()
    # currently copying
    self._copying_ = threading.Event()
    self.copy = None
    self.progress = '.'
  
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
      elif self._startCopy_.isSet():
        self._copying_.set()
        self.startCopy()
      elif self._copying_.isSet():
        self.progress = self.copy.progress
      time.sleep(LOOP_DELAY)

  def startCopy(self):
    if DEBUG: print "startCopy"
    self.copy = sC.Copy()
    # clear this flag after the Copy object has been created
    self._startCopy_.clear()
    # scan the devices
    self.copy.updateDeviceAttributes()
    if DEBUG: print "USB devices to which to copy:%s" % self.copy.usbDevices
    self.copy.copy()
    del self.copy
    self.copy = None
    self._copying_.clear()
      

if __name__ == '__main__':
  r = Recorder()
  s = Scheduler()
  v = Converter()
  u = Uploader()
  d = Copier()
  c = Controller(r,s,v,u,d)
  c.start()
