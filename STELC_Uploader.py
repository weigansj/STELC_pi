#!/user/bin/python
"""
Uploads a file to dropbox using the dropbox_uploader.sh from Andrea Fabrizi
which first needs to be installed in ~/Dropbox-Uloader as per
  cd ~
  git clone https://github.com/andreafabrizi/Dropbox-Uploader.git
  cd Dropbox-Uploader
  ./dropbox_uploader.sh
This will require a Dropbox account and some interaction with
Dropbox to get it set up.
"""
import subprocess,os.path,sys,re

UPLOADER = '/home/pi/Dropbox-Uploader/dropbox_uploader.sh'
DEBUG = 1

class Upload():
  """
  This is for keeping uploading the recoded file to Dropbox.
  """
  def __init__(self):
    self.progress = '0%'
    self.localFile = ''
    self.remoteFile = ''

  def upload(self,uploadFile):
    """
    upload the file given and track the progess
    """
    # local filename
    self.localFile = os.path.abspath(uploadFile)
    # filename on Dropbox
    self.remoteFile = os.path.basename(self.localFile)
    # files for stdout and stderr
    pipeOut = open('.dropbox_upload.out','w')
    pipeErr = open('.dropbox_upload.err','w')
    # open the pipe
    if DEBUG: print "upload command: %s %s %s %s %s" %(
      UPLOADER,'-p','upload',self.localFile,self.remoteFile)
    uploadPipe = subprocess.Popen(
      [UPLOADER,'-p','upload',self.localFile,self.remoteFile],
      bufsize=-1,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      universal_newlines=True,
      close_fds=True)
    while uploadPipe.poll() == None:
      line = uploadPipe.stderr.readline()
      while line:
        pipeErr.write(line)
        pipeErr.flush()
        myMatch = re.search(' ([0-9\.]+%)$',line)
        if myMatch:
          self.progress = myMatch.group(1)
        if DEBUG: print "upload progress %s" % self.progress
        line = uploadPipe.stderr.readline()

    pipeOut.writelines(uploadPipe.stdout.readlines())
    if DEBUG: print "DONE %s" % uploadPipe.poll()
    pipeOut.close()
    pipeErr.close()

if __name__ == '__main__':
  u = Upload()
  u.upload(sys.argv[-1])
  del u
