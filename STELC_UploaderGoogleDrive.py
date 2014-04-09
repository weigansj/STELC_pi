#!/usr/bin/python
"""
  Upload files to Google Drive
  This requires a Service Account Client ID which can
  be optained from https://console.developers.google.com
  under "APIs & auth -> Credentials"

  The credentials which result should be assigned to globals
  in GoogleCreds.py
    OAUTH_SERVICE_PRIVATE_KEY_FILENAME = '' # filename of private key file
    OAUTH_SERVICE_CLIENT_ID = '' # client ID for service account
    OAUTH_SERVICE_EMAIL_ADDRESS = '' # email given for service account
    OAUTH_SERVICE_PUBLIC_KEY_FINGERPRINTS = ('',) # tuple of public key fingerprint(s)
    OAUTH_SERVICE_SHARED_CALENDAR_ID = # calendar id to use for schedule
  You will also need to share the calendar given by OAUTH_SERVICE_SHARED_CALENDAR_ID
    using the Google Calendar UI with the email given in OAUTH_SERVICE_EMAIL_ADDRESS
  Scheduled recordings should be the only events on this calendar
"""
import httplib2
import pprint
import sys,os.path

from apiclient.discovery import build
from oauth2client.client import SignedJwtAssertionCredentials
from apiclient import errors
from apiclient.http import MediaFileUpload
from GoogleCreds import *

DEBUG = 2

class Upload():
  """
  This is for uploading the recorded file to Google Drive
  """

  def __init__(self):
    self.progress = None
    self.localFile = ''
    self.remoteFile = ''
    self.http = None
    self.service = None

  def connect(self):
    """
    connect to the Google Drive API
    """
    # Load the key in PKCS 12 format that you downloaded from the Google API
    # Console when you created your Service account.
    f = file(OAUTH_SERVICE_PRIVATE_KEY_FILENAME, 'rb')
    key = f.read()
    f.close()

    # Create an httplib2.Http object to handle our HTTP requests and 
    # authorize it with the Credentials. Note that the first parameter, 
    # service_account_name, is the Email address created for the Service 
    # account. It must be the email address associated with the key that 
    # was created.
    credentials = SignedJwtAssertionCredentials(
      OAUTH_SERVICE_EMAIL_ADDRESS,
      key,
      scope=('https://www.googleapis.com/auth/drive',),
      user_agent='STELC_pi/1.0')
    http = httplib2.Http()
    self.http = credentials.authorize(http)
    self.service = build("drive", "v2", http=self.http)

  def getFolderId(self):
    # List all files
    topFiles = self.service.files().list().execute(http=self.http)
    #pprint.pprint(topFiles)
   
    # shared folder
    folderId = filter(lambda x:(
                       x['title']==OAUTH_SERVICE_SHARED_FOLDER_TITLE and 
                       x['mimeType']==u'application/vnd.google-apps.folder'),
                     topFiles['items'])[0]['id']
    # list contents
    if DEBUG > 1:
      for child in self.service.children().list(
                        folderId=folderId).execute(http=self.http)['items']:
         fileMeta = self.service.files().get(
                        fileId=child['id']).execute(http=self.http)
         pprint.pprint(fileMeta)

    return folderId
                     
  def upload(self,uploadFile):
    """
    upload the file given and track the progress
    This does the full connect, get folder is and upload
    so that it is interchangable with the Dropbox Uploader
    """
    # local filename
    self.localFile = os.path.abspath(uploadFile)
    # filename on Dropbox
    self.remoteFile = os.path.basename(self.localFile)
    # connect to Google Drive API
    self.connect()
    folderId = self.getFolderId()
    # media body
    # determine mime type
    ext = os.path.splitext(uploadFile)[-1]
    mime_type='application/vnd.google-apps.audio'
    if ext == '.mp3' or ext == '.MP3': mime_type='audio/mpeg'
    if ext == '.wav' or ext == '.WAV': mime_type='audio/x-wav'
    if ext == '.log' or ext == '.log': mime_type='text/plain'
    media_body = MediaFileUpload(self.localFile,mimetype=mime_type,resumable=True)
    body = {
      'title': uploadFile,
      'descrption': 'recorded service',
      'mimeType': mime_type,
      'parents': [{'id': folderId}]
    }
    try:
      thisFile = self.service.files().insert(
        body=body,
        media_body=media_body).execute(http=self.http)
      if DEBUG: print 'File ID: %s' % thisFile['id']
      if DEBUG > 1: pprint.pprint(thisFile)
      return thisFile
    except errors.HttpError, error:
      print 'An error occured: %s' % error
      return None


if __name__ == '__main__':
  #main(sys.argv)
  u = Upload()
  u.upload(sys.argv[-1])
  del u
