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
import subprocess,os.path,sys

UPLOADER = '/home/pi/Dropbox-Uploader/dropbox_uploader.sh'
DEBUG = 1

class Upload():
  """
  This is for keeping uploading the recoded file to Dropbox.
  """
  def __init__(self):
    pass

  def upload(self,uploadFile):
    localFile = os.path.abspath(uploadFile)
    remoteFile = os.path.basename(localFile)
    pipeOut = open('.dropbox_upload.out','w')
    pipeErr = open('.dropbox_upload.err','w')
    uploadPipe = subprocess.Popen(
      [UPLOADER,'-p','upload',localFile,remoteFile],
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
        line = uploadPipe.stderr.readline()

    pipeOut.writelines(uploadPipe.stdout.readlines())
    if DEBUG: print uploadPipe.poll()

if __name__ == '__main__':
  u = Upload()
  u.upload(sys.argv[-1])
