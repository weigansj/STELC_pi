#!/usr/bin/python

from STELC_Display import *
import threading
import time


class Controller(threading.Thread):
  """
  This if for creating a STELC specific thread for containing and
  controlling the display.  This is where the display triggered methods go
  And of course needs to communicate with a recorder thread
  """
  def __init__(self,recorder):
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
    self.clearAll()
    self.idle()
    print 'cancel method'

  def record(self):
    """
    Called when requested to record
    """
    self.clearAll()
    self._recording_.set()
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
    self._stop_ = threading.Event()
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

  def start(self):
    self.thread = threading.Thread(None, self.run, None, (), {})
    self.thread.start()

  def stop(self):
    self._stop_.set()

  def stopped(self):
    return self._stop_.isSet()

  def run(self):
    while not self.stopped():
      if self._clear_.isSet(): self.clearAll()
      

if __name__ == '__main__':
  r = Recorder()
  r.start()
  c = Controller(r)
  c.start()
