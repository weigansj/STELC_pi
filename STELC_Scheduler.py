#!/usr/bin/python
"""
  Determine Schedule from Google Calendar
  This requires a Service Account Client ID which can
  be optained from https://console.developers.google.com
  under "APIs & auth -> Credentials"
"""
import httplib2
import pprint
import sys

from apiclient.discovery import build
from oauth2client.client import SignedJwtAssertionCredentials
from GoogleCreds import *
# GoogleCreds contains only globals with values from
#  the Google Devlopers Console including:
#OAUTH_SERVICE_PRIVATE_KEY_FILENAME = ''
#OAUTH_SERVICE_CLIENT_ID = ''
#OAUTH_SERVICE_EMAIL_ADDRESS = ''
#OAUTH_SERVICE_PUBLIC_KEY_FINGERPRINTS = ('')

class Schedule():
  """
  This is for keeping track of the schedule for recording,  I think I would like
  to use a Google Calendar API for this.
  """
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
      scope='https://www.googleapis.com/auth/calendar',
      user_agent='STELC_pi/0.0')
  http = httplib2.Http()
  http = credentials.authorize(http)

  service = build("calendar", "v3", http=http)

  # List all the tasklists for the account.
  lists = service.calendarList().list().execute(http=http)
  pprint.pprint(lists)


if __name__ == '__main__':
  main(sys.argv)
