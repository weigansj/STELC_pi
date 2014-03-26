#!/usr/bin/python
"""
  Determine Schedule from Google Calendar
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

import time
from dateutil import parser
import yaml

class Schedule():
  """
  This is for keeping track of the schedule for recording,  I think I would like
  to use a Google Calendar API for this.
  """
  def __init__(self):
    self._blankEvent = {
      'id': '', # eventID for GoogleAPI
      'start': time.time(),
      'duration': 0.0,
      'status': {'filename': None, # flag for the filename
                 'uploaded': False, # flag for if the file has been uploaded
                 'purged': False} # flag to if the file has been locally purged
    }

  def getNext(self):
    """
    return an eventDict for the next recording event
    """
    pass

  def getId(self,eventId):
    """
    return an eventDict for the recording event with the given Google eventId
    """
    pass

  def findOldEvent(self,filename):
    """
    return an old recording eventDict based on the filename
    """
    pass

  def markUploaded(self,eventDict):
    """
    mark this event as Uploaded on the calendar
    """
    pass

  def purge(self,eventDict):
    """
    purge the file for this event and mark as purged on the calendar
    """
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
      scope=('https://www.googleapis.com/auth/calendar',),
      user_agent='STELC_pi/0.0')
  http = httplib2.Http()
  http = credentials.authorize(http)

  service = build("calendar", "v3", http=http)

  # List all the calendars for the account.
  allCalendars = service.calendarList().list().execute(http=http)
  pprint.pprint(allCalendars)
  
  # List all events on the shared calendar
  allEvents = service.events().list(
    calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID).execute(http=http)
  pprint.pprint(allEvents)
  
  # print the description of the first event
  eventId = allEvents['items'][0]['id']
  thisEvent = service.events().get(
    calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID,
    eventId = eventId).execute(http=http)
  print thisEvent['description']

  s = Schedule()
  e = s._blankEvent
  e['id']=eventId
  e['status']['filename']="testfile.wav"
  
  # modify the description
  #oldDescription = "%s" % thisEvent['description']
  #newDescription = "%s\n%s" % (oldDescription,"test")
  service.events().patch(
    calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID,
    eventId=e['id'],
    body={'description':yaml.dump(e['status'],default_flow_style=False)}).execute(http=http)
  thisEvent = service.events().get(
    calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID,
    eventId = e['id']).execute(http=http)
  print thisEvent['description']
    
if __name__ == '__main__':
  main(sys.argv)
