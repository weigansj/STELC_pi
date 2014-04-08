#!/usr/bin/python
"""
used by STELC_pi to mount an inserted USB drive
copy over the wav and log files and unmount the drive
"""
import re,sys
import subprocess,time

DEBUG = 1
PROGRESS_CHARS = ['.','^','>','v','<']
COPYCMD = "rsync -Pt --modify-window=2 --include='*.mp3' --include='*.wav' --include='*.log' --exclude='*' ./* %s/STELC_pi/" # command used to copy the files the %s is the USB mount point

class Copy():
  """
  """
  def __init__(self):
    self.progressCount = 0
    self.progress = '.'
    self.incrProgress()
    self.devDict = {}
    self.usbDevices = []

  def incrProgress(self):
    self.progressCount += 1
    self.progress = PROGRESS_CHARS[self.progressCount % len(PROGRESS_CHARS)]
    if DEBUG: 
      sys.stdout.write("%s\r" % self.progress)
      sys.stdout.flush()

  def updateDeviceAttributes(self):
    """
    update the devDict and usbDevices attributes
    """
    self.incrProgress()
    self.devDict = self.getDeviceDict()
    self.usbDevices = self.getRemovableFilesystems()

  def getRemovableFilesystems(self):
    """
    returns a list of two item tuples of removable filesystems (like USB sticks)
    the first item in the tuple is the partition device file
    the second item is the parent device file
    """
    myList = []
    for pKey in self.devDict.keys():
      if (self.devDict[pKey]['usage'] == "filesystem" and
          self.devDict[pKey]['is read only'] != '1'):
        dObj = self.devDict[pKey]['partition']['part of']
        for dKey in self.devDict.keys():
          if (self.devDict[dKey]['object path'] == dObj and 
              self.devDict[dKey]['removable'] == '1' and
              self.devDict[dKey]['drive']['detachable'] == '1' and
              self.devDict[dKey]['is read only'] != '1'):
            myList.append((pKey,dKey))
    return myList

  def getDeviceDict(self):
    """
    use udisks to get a list of all devices
    """
    # list all device files of devices known
    devices = subprocess.check_output(['udisks --enumerate-device-files | grep -v "dev/disk"'],shell=True).splitlines()
    devDict = {}
    for d in devices:
      devDict[d]=self.getInfoDict(d)
      self.incrProgress()
    return devDict

  def getInfoDict(self,d):
    """
    use udisks to get the info from one device
    """
    keyOne = ''
    keyTwo = ''
    infoDict = {}
    info = subprocess.check_output(['udisks','--show-info',d]).splitlines()
    infoDict['object path'] = info[0].split(' ')[-1]
    for item in info[1:]:
      myMatch = re.search('^( +)([^ ][^:]*): *([^ ].*)?$',item)
      if myMatch:
        sp,key,val = myMatch.groups()
        if DEBUG > 1: print "%s->%s->%s" % (d,key,val)
        if len(sp) == 2:
          infoDict[key] = val
          keyOne = key
        elif len(sp) == 4:
          if type(infoDict[keyOne]) == str or \
             infoDict[keyOne] == None:
            infoDict[keyOne] = {}
          infoDict[keyOne][key] = val
          keyTwo = key
        elif len(sp) == 6:
          if type(infoDict[keyOne][keyTwo]) == str or \
             infoDict[keyOne][keyTwo] == None:
            infoDict[keyOne][keyTwo] = {}
          infoDict[keyOne][keyTwo][key] = val
    return infoDict

  def mount(self,devTpl):
    if self.devDict[devTpl[0]]['is mounted'] != '1':
      subprocess.check_call(['udisks','--mount',devTpl[0]])
    for d in devTpl: self.devDict[d] = self.getInfoDict(d)
    self.incrProgress()

  def getUsbMounts(self,deviceList):
    mntList = []
    for (p,d) in deviceList:
      if self.devDict[p]['is mounted'] == '1':
        mntList.append(self.devDict[p]['mount paths'].split()[0])
    return mntList

  def unmount(self,devTpl):
    if self.devDict[devTpl[0]]['is mounted'] == '1':
      subprocess.check_call(['udisks','--unmount',devTpl[0]])
    for d in devTpl: self.devDict[d] = self.getInfoDict(d)
    self.incrProgress()

  def detach(self,devTpl):
    if self.devDict[devTpl[1]]['drive']['detachable'] == '1':
      subprocess.check_call(['udisks','--detach',devTpl[1]])
    for d in devTpl: self.devDict[d] = self.getInfoDict(d)
    self.incrProgress()

  def copy(self):
    """
    mount a usb stick, rsync the wav and log files, unmount and detach the stick
    """
    # locate and mount usb sticks
    self.updateDeviceAttributes()
    for usbDev in self.usbDevices:
      try: self.mount(usbDev)
      except: 
        self.progress = "%s mount fail" % self.devDict[usbDev[0]]['label']
        if DEBUG: print self.progress
        time.sleep(2.0)
    # files for stdout and stderr
    pipeOut = open('copy_stdout.log','w')
    pipeErr = open('copy_stderr.log','w')
    # loop trough each mounted stick
    mntCount = 0
    for mnt in self.getUsbMounts(self.usbDevices):
      mntCount += 1
      fileCount = 0
      # open the pipe with the copy command
      copyCmd = COPYCMD % mnt
      if DEBUG: print "copy command: %s" % copyCmd
      pipeOut.write("copy command: %s\n" % copyCmd)
      pipeErr.write("copy command: %s\n" % copyCmd)
      copyPipe = subprocess.Popen(copyCmd,
        shell=True,
        bufsize=-1,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        close_fds=True)
      # poll lack of completion
      while copyPipe.poll() == None:
        # read any lines produced
        line = copyPipe.stdout.readline()
        while line:
          pipeOut.write(line)
          pipeOut.flush()
          # count files
          if re.search('^[^ ]',line): fileCount += 0.5
          else: 
            # extract % complete for each file
            myMatch = re.search('\s([0-9]+%)\s',line)
            if myMatch: self.progress = "%d.%d %s" % (mntCount,fileCount,myMatch.group(1))
            if DEBUG: print "rsync progress %s" % self.progress
          line = copyPipe.stdout.readline()

      pipeErr.writelines(copyPipe.stderr.readlines())
      if DEBUG: print "rsync done %s" % copyPipe.poll()

    pipeOut.close()
    pipeErr.close()

    # locate, unmount, and detach usb sticks
    self.updateDeviceAttributes()
    for usbDev in self.usbDevices:
      try: self.unmount(usbDev)
      except: 
        self.progress = "%s unmount fail" % self.devDict[usbDev[0]]['label']
        if DEBUG: print self.progress
        time.sleep(2.0)
      try: self.detach(usbDev)
      except: 
        # this reports failure but seems to still work
        #self.progress = "%s detach fail" % self.devDict[usbDev[0]]['label']
        if DEBUG: print  "%s detach fail" % self.devDict[usbDev[0]]['label']
        time.sleep(2.0)
    self.progress = "DONE"
    if DEBUG: print "DONE"
    time.sleep(10.0)


if __name__ == '__main__':
  c = Copy()
  c.updateDeviceAttributes()
  print c.usbDevices
  c.copy()
