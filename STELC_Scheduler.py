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
import copy

from apiclient.discovery import build
from oauth2client.client import SignedJwtAssertionCredentials
from GoogleCreds import *

import time,datetime,calendar
import yaml,re

DEBUG = 1
LOOK_AHEAD = 60.*60.*24.*8. # number of seconds ahead to look for new events
BLANKEVENT = {
  'id': None, # eventID for GoogleAPI
  'summary': '', # summary text
  'start': 0.0,
  'duration': 0.0,
  'status': {'filename': None, # flag for the filename
             #'mp3': None, # flag for the mp3 filename
             'uploaded': False, # flag for if the file has been uploaded
             #'purged': False, # flag to if the file has been locally purged
            }
}
 

def googleDateTime(myTime):
  """
  convert a floating point seconds since Unix epoch time into a JSON dataTime
  for Google API
  """
  myIso = time.strftime('%Y-%m-%dT%H:%M:%S',time.localtime(myTime))
  # use appropriate offset for DST or not
  myZoneOffset = time.daylight and time.altzone or time.timezone
  # west of UTC should be negative in this format
  myTz = "%03d:%02d" % (-1*myZoneOffset/3600 , myZoneOffset%3600)
  return "%s%s" % (myIso,myTz)

def epochTime(googleDateTime):
  """
  convert a Google API JSON dataTime into localtime seconds since Unix epoch
  """
  myZoneOffsetNow = time.daylight and time.altzone or time.timezone
  # extract any frational seconds
  myMatch = re.search('(\.[0-9]+)$',googleDateTime)
  if myMatch:
    fracSec = float(myMatch.group(1))
  else: fracSec = 0.0
  # get the time in secs since Epoch, time in google Calendar is assumed to
  # be local unless it stored as UTC, in this case it will apply to offset
  # alternate timezones are not handled
  if googleDateTime[-1] == 'Z':
    myTime = calendar.timegm(time.strptime(googleDateTime[0:19],'%Y-%m-%dT%H:%M:%S'))
  else:
    myTime = time.mktime(time.strptime(googleDateTime[0:19],'%Y-%m-%dT%H:%M:%S'))

  myTime += fracSec
  return myTime

class Schedule():
  """
  This is for keeping track of the schedule for recording,  I think I would like
  to use a Google Calendar API for this.
  Note that I have not included anything for refreshing credentials or whatever
  is needed,  so far I just always call connect() before I do any getNext() or
  getBy()
  """
  def __init__(self):
    self.event = self.getBlank()
    self.http = None
    self.service = None

  def getBlank(self):
    return copy.deepcopy(BLANKEVENT)
  
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
    # start with a blank eventDict
    event = self.getBlank()
    # assign the values based on the item
    event['id'] = item['id']
    event['summary'] = item['summary']
    start = epochTime(item['start']['dateTime'])
    end = epochTime(item['end']['dateTime'])
    event['start'] = start
    event['duration'] = end - start
    # extract the status key dictionary from the items description
    if item.has_key('description'):
      status = event['status']
      try:
         status = yaml.load(item['description'])
      except:
       raise
      # only use as status if I had it in the description
      # otherwise keey the default
      if status: event['status'] = status
    return event

  def getNext(self):
    """
    return an eventDict for the next recording event
    and set the event attribure to eventDict
    if none is found a blank event is returned
    the self.event attrubute is reset only for a successful find
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
    else: return self.getBlank()

  def getBy(self,key,val):
    """
    return an eventDict for an event for which the key argument
    equals the val argument, and set the event attribute to the eventDict
    if none is found a blank event is returned
    the self.event attrubute is reset only for a successful find
    """
    now = time.time()
    later = now + LOOK_AHEAD
    rtnEvent = self.getBlank()
    if DEBUG: print "get all events looking for %s=%s" % (key,val)
    page_token = None
    while True:
      events = self.service.events().list(
       calendarId=OAUTH_SERVICE_SHARED_CALENDAR_ID,
       orderBy='startTime', # sort by start time
       singleEvents=True, # expect recurring events into single events
       timeMax=googleDateTime(later), #limit to events starting before later
       pageToken = page_token
      ).execute(http=self.http)
      # loop through all items and return the first match
      for item in events['items']:
        if DEBUG > 2: pprint.pprint(item)
        testEvent = self.itemToEvent(item)
        if DEBUG > 1: pprint.pprint(testEvent)
        if key in ('id','summary','start','duration'):
          if testEvent[key] == val:
            self.event = testEvent
            rtnEvent = self.event
            break
        elif testEvent['status'].has_key(key):
          if testEvent['status'][key] == val:
            self.event = testEvent
            rtnEvent = self.event
            break
      page_token = events.get('nextPageToken')
      # if we found a match or if there are no more events stop
      if self.event is rtnEvent or not page_token: break

    # return the event (will be a blank event if I can not find one)
    if DEBUG: pprint.pprint(rtnEvent)
    return rtnEvent

  def putEvent(self):
    """
    put the status items from the current event in the description of the 
    calendar item
    Note the fact that the Schedule class can only modify the calendar
    item's description is by design.  The schedule drives the recorder,
    not the other way around
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
  s.getNext()
  s.getBy('id','mofjmjqimrr46o3f9mpjftaehs')
  s.getBy('filename','STELC_20140406-1013.wav')
  s.getBy('filename','notthereanywhere.wav')

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

  #e = s.getBlank()
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
