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

import time,datetime
import yaml,re

DEBUG = 1
LOOK_AHEAD = 60.*60.*24.*7. # number of seconds ahead to look for new events

def googleDateTime(myTime):
  """
  convert a floating point seconds since Unix epoch time into a JSON dataTime
  for Google API
  note the Google Calendar API seems to store the
  start and end times with the time zone offset which already includes DST
  """
  myIso = time.strftime('%Y-%m-%dT%H:%M:%S',time.localtime(myTime))
  myTz = "%03d:%02d" % (-1*time.altzone/3600 , time.altzone%3600)
  return "%s%s" % (myIso,myTz)

def epochTime(googleDateTime):
  """
  convert a Google API JSON dataTime into seconds since Unix epoch
  note the Google Calendar API seems to store the
  start and end times with the time zone offset which already includes DST
  """
  myMatch = re.search('([+-]([0-9][0-9]):([0-9][0-9]))$',googleDateTime)
  if myMatch:
    altZone = float(myMatch.group(2))*60. + float(myMatch.group(3))
    altZone *= 60.
    if myMatch.group(1)[0] == "+": altZone *= -1
  elif googleDateTime[-1] == "Z":
    altZone = 0
  else: altZone = time.altzone
  myMatch = re.search('(\.[0-9]+)$',googleDateTime)
  if myMatch:
    fracSec = float(myMatch.group(1))
  else: fracSec = 0.0
  myTime = float(time.strftime('%s',
            time.strptime(googleDateTime[0:19],'%Y-%m-%dT%H:%M:%S')))
  myTime = myTime + fracSec + altZone - time.altzone
  return myTime

class Schedule():
  """
  This is for keeping track of the schedule for recording,  I think I would like
  to use a Google Calendar API for this.
  """
  def __init__(self):
    self._blankEvent = {
      'id': '', # eventID for GoogleAPI
      'start': 0.0,
      'duration': 0.0,
      'status': {'filename': None, # flag for the filename
                 'uploaded': False, # flag for if the file has been uploaded
                 'purged': False} # flag to if the file has been locally purged
    }
    self.event = self._blankEvent.copy()
    self.http = None
    self.service = None

  def connect(self):
    """
    connect to the Google Calendar API
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
      scope=('https://www.googleapis.com/auth/calendar',),
      user_agent='STELC_pi/0.0')
    http = httplib2.Http()
    self.http = credentials.authorize(http)
    self.service = build("calendar", "v3", http=self.http)

  def itemToEvent(self,item):
    """
    convert a Google calendar API events list item to a Schedule event
    """
    event = self._blankEvent.copy()
    event['id'] = item['id']
    start = epochTime(item['start']['dateTime'])
    end = epochTime(item['end']['dateTime'])
    event['start'] = start
    event['duration'] = end - start
    status = event['status']
    try:
      status = yaml.load(event['description'])
    except:
      pass
    event['status'] = status
    return event

  def getNext(self):
    """
    return an eventDict for the next recording event
    and set the event attribure to eventDict
    """
    now = time.time()
    later = now + LOOK_AHEAD
    if DEBUG: print "get next event between %s and %s" % (now,later)
    events = self.service.events().list(
      calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID,
      orderBy='startTime', # sort by start time
      singleEvents=True, # expect recurring events into single events
      timeMax=googleDateTime(later), #limit to events starting before later
      timeMin=googleDateTime(now) #limit to events ending after now
    ).execute(http=self.http)
    # if there is anything in the list return the first one
    if events['items']:
      if DEBUG: pprint.pprint(events['items'][0])
      self.event = self.itemToEvent(events['items'][0])
      return self.event
    else: return self._blankEvent.copy()

  def putEvent(self):
    """
    put the status items from the current event in the description of the 
    calendar item
    """
    self.service.events().patch(
      calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID,
      eventId=self.event['id'],
      body={'description':yaml.dump(self.event['status'],
                                    default_flow_style=False)}
    ).execute(http=self.http)


def main(argv):
  s = Schedule()
  s.connect()
  pprint.pprint(s.getNext())
  ## List all the calendars for the account.
  #allCalendars = s.service.calendarList().list().execute(http=s.http)
  #pprint.pprint(allCalendars)
  
  ## List all events on the shared calendar
  #allEvents = s.service.events().list(
  #  calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID).execute(http=s.http)
  #pprint.pprint(allEvents)
  
  ## print the description of the first event
  #eventId = allEvents['items'][0]['id']
  #thisEvent = s.service.events().get(
  #  calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID,
  #  eventId = eventId).execute(http=s.http)
  #print thisEvent['description']

  #e = s._blankEvent
  #e['id']=eventId
  #e['status']['filename']="testfile.wav"
  
  ## modify the description
  ##oldDescription = "%s" % thisEvent['description']
  ##newDescription = "%s\n%s" % (oldDescription,"test")
  #s.service.events().patch(
  #  calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID,
  #  eventId=e['id'],
  #  body={'description':yaml.dump(e['status'],default_flow_style=False)}).execute(http=s.http)
  #thisEvent = s.service.events().get(
  #  calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID,
  #  eventId = e['id']).execute(http=s.http)
  #print thisEvent['description']
    
if __name__ == '__main__':
  main(sys.argv)
