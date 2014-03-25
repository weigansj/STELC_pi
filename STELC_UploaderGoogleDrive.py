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
import sys

from apiclient.discovery import build
from oauth2client.client import SignedJwtAssertionCredentials
from GoogleCreds import *

class Upload():
  def __init__(self):
    pass

  def start():
    pass


def main(argv):
  # Load the key in PKCS 12 format that you downloaded from the Google API
  # Console when you created your Service account.
  f = file(OAUTH_SERVICE_PRIVATE_KEY_FILENAME, 'rb')
  key = f.read()
  f.close()

  # Create an httplib2.Http object to handle our HTTP requests and authorize it
  # with the Credentials. Note that the first parameter, service_account_name,
  # is the Email address created for the Service account. It must be the email
  # address associated with the key that was created.
  credentials = SignedJwtAssertionCredentials(
      OAUTH_SERVICE_EMAIL_ADDRESS,
      key,
      scope=('https://www.googleapis.com/auth/drive',),
      user_agent='STELC_pi/0.0')
  http = httplib2.Http()
  http = credentials.authorize(http)

  service = build("drive", "v2", http=http)

  # List all files
  topFiles = service.files().list().execute(http=http)
  #pprint.pprint(topFiles)

  # shared folder
  folderId = filter(lambda x:(
                      x['title']==OAUTH_SERVICE_SHARED_FOLDER_TITLE and 
                      x['mimeType']==u'application/vnd.google-apps.folder'),
                    topFiles['items'])[0]['id']
                    
  # list contents
  for child in service.children().list(folderId=folderId).execute(http=http)['items']:
      fileMeta = service.files().get(fileId=child['id']).execute(http=http)
      pprint.pprint(fileMeta)

  #get id for folder
    
if __name__ == '__main__':
  main(sys.argv)
