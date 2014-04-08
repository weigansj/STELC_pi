#!/usr/bin/python

from Adafruit_CharLCDPlate import Adafruit_CharLCDPlate
import os
import time
import string

# update cycle time for display
LOOP_DELAY = 0.2
# time to turn off display when idle
IDLE_SLEEP_DELAY = 60

# display status, related to the query block
OFF = 0
IDLE = 1
PROCESS = 2
QUERY = 3

DEFAULT_STATUS = "STELC pi "

DEBUG = 0


class ScrollingBlock():
  """
  super class to and scrolling to a display block
  """
  def __init__(self):
    # current offset for message
    self.offset = 0
    # rate at which to scroll (offset per sec)
    self.offsetRate = 1.0
    # record keeper for when the message was last offset
    self.offsetTime = time.time()
    # default is to scroll, can also oscillate
    self.offsetOscillate = False
    # offset change per step
    self.offsetStep = 1
    # length of the display block
    self.blockLength = 9
    # where does the block start
    self.blockStart = (0,0)
    # message to display in block
    self.message = ""
    # length of space between scrolling message and its copy updates
    # to int(self.blockLength/2) every cycle
    self.spacerLength = 0
    
  def update(self):
    """
    called every display update loop to determine if scrolling is needed
    """
    #create a long form of message with a spacer and a copy of the message
    self.spacerLength = int(self.blockLength/2)
    longM = "%s%s%s" % (self.message," "*self.spacerLength,self.message)
    #offset and truncate message to fit block
    shortM = longM[self.offset:self.offset + self.blockLength]
    self.out = shortM
    # determine if scrolling is necessary
    if (len(self.message) > self.blockLength):
      # call the scroll calculation
      self.scroll(self.message)
    else:
      # fill the unused space to prevent left behind characters
      self.out = self.message + " "*(self.blockLength-len(self.out)+1)
    
  def scroll(self,msg):
    """
    determine the size of the offset
    """
    # is it time to do the offset?
    if time.time() - self.offsetTime > self.offsetRate:
      self.offsetTime = time.time()
      # do we oscillate
      if self.offsetOscillate:
        # is offset large enough to change direction?
        if self.offset > len(msg) - self.blockLength -1:
          # by subtracting 1, first cycle stops scroll, second changes
          # its direction, values for offsetStep will still only be 1,0, and -1
          # this would work differently if the offset was larger than 1
          self.offsetStep = self.offsetStep - 1
      # have we scrolled to the start of the message copy
      if self.offset > len(msg)+self.spacerLength-2:
        self.offset = 0
      # have we oscillated backward past the start
      elif self.offset < 0:
        self.offset = 0
        self.offsetStep = 1
      # if neither do the offset
      else:
        self.offset = self.offset + self.offsetStep



class StatusBlock(ScrollingBlock):
  """
  This block is for a status display meant for status messages only
  """
  def __init__(self,myLcd):
    self.lcd = myLcd
    ScrollingBlock.__init__(self)
    self.offset = 0
    self.offsetRate = 0.5
    self.offsetOscillate = True
    self.offsetTime = time.time()
    self.blockLength = 10
    self.blockStart = (0,0)
    self.message = ""
    
  def update(self):
    ScrollingBlock.update(self)
    self.lcd.setCursor(self.blockStart[0],self.blockStart[1])
    self.lcd.message(self.out)



class TimeBlock(ScrollingBlock):
  """
  This block is for a clock for current time of countup ro countdown
  """
  def __init__(self,myLcd):
    self.lcd = myLcd
    ScrollingBlock.__init__(self)
    self.offset = 0
    self.offsetRate = 1.5
    self.offsetTime = time.time()
    self.blockLength = 6
    self.blockStart = (16-self.blockLength,0)
    self.weekDay = ("Mo","Tu","We","Th","Fr","Sa","Su")
    self.message = ""
    # if deltaStart == 0 we display a clock
    # if deltaStart != current time display absolute delta from current time
    self.deltaStart = 0

  def update(self):
    self.blockStart = (16-self.blockLength,0)
    self.lastMessage = self.message
    self.timeTuple = time.localtime()
    self.message = "%2s %02d:%02d:%02d" % (self.weekDay[self.timeTuple[6]],
                                             self.timeTuple[3],
                                             self.timeTuple[4],
                                             self.timeTuple[5])
    if self.deltaStart > 0:
      delta = abs(time.time() - self.deltaStart)
      self.message = "%02d:%02d" % (int(delta/60.0),int(delta%60.0))

    ScrollingBlock.update(self)
    self.lcd.setCursor(self.blockStart[0],self.blockStart[1])
    self.lcd.message(self.out)



class Action():
  """
  Action instances are assigned as part of a query.  It is whatever happens
  when a particular query is selected and verified (if needed)
  This can be overloaded which whatever actions.  The action should be
  executed within the do method.
  Any action should take less time than the IDLE_SLEEP_DELAY so that the
  display update loop is not frozen (setting thread events for example)
  """
  def __init__(self,atn,*ns):
    self.action = compile(atn,'action code','exec')
    self.ns = ns
    
  def do(self):
    if len(self.ns) > 0:
      if len(self.ns) > 1:
        exec self.action in self.ns[0], self.ns[1]
      else:
        exec self.action in self.ns[0]
    else:
      exec self.action



class Query():
  """
  A Query is a class for questions and answers from the button pad
  """
  def __init__(self,message="Well?",
                    responses=[('Yes',7,True,None),
                               ('No',11,False,None)],defaultResponse=1,
                    up=None,
                    down=None
              ):
    """
    message is the message for the display
    responses is a list of responses where each response is a tuple containing
     (message,position,needVerify,action) where position is 
     where the cursor goes when the reponces is highlighted
     needVerify is whether this response needs verification
     and action is the action for a selected/verified response
    """
    # non response part of message
    self.message = message
    # list of responses
    self.responses = responses
    # default cursor position
    self.defaultPosition = self.responses[defaultResponse][1]
    # current cursor position
    self.position = self.defaultPosition
    # current selected response
    self.selected = None
    # is this a currently actively displayed query
    self.active = False
    # query number to change to is up is pressed
    self.up = up
    # query number to change to is down is pressed
    self.down = down

  def reset(self):
    """
    reset a query to its default
    """
    self.position = self.defaultPosition
    self.selected = None
    self.active = False

  def makeVerifier(self):
    """
    return an active verifier instance with the action from a given response
    """
    if self.selected:
      # create an active verifier
      v = Verifier(self.selected[3])
      # inactivate myself
      self.active = False
    else:
      v = None
      raise "No selected response can not make verifier"
    return v

  def nextPosition(self):
    """
    change the cursor position to the next response position
    """
    pi = 0
    for ri in range(len(self.responses)):
      if self.position == self.responses[ri][1]:
        pi = ri+1
    if pi >= len(self.responses): pi = 0
    self.position = self.responses[pi][1]

  def prevPosition(self):
    """
    change the cursor position to the previous response position
    """
    pi = 0
    for ri in range(len(self.responses)):
      if self.position == self.responses[ri][1]:
        pi = ri-1
    if pi < 0: pi = len(self.responses)-1
    self.position = self.responses[pi][1]

  def makeMessage(self,blockLength):
    ml = list((blockLength+1)*" ")
    ml[0:len(self.message)] = list(self.message)
    for r in self.responses:
      ml[r[1]+1:len(r[0])+1] = list(r[0])
    ml[self.position:self.position+1]=">"
    return string.join(ml,'')
    

class Verifier(Query):
  """
  Special Query to verify other queries
  """
  def __init__(self,action):
    m = "Sure?"
    r = [('Yes',7,False,action),
         ('No',11,False,Action('pass'))]
    s = 1
    Query.__init__(self,message=m,responses=r,defaultResponse=s)
    self.active = True
    



class QueryBlock():
  """
  Query blocks need to display but also take input from the
  buttons.  It controls the "state" of the display and the
  update method returns a state for the display based on input
  from the buttons.  
  """  
  def __init__(self,myLcd,defaultQuery=0,*qs):
    self.lcd = myLcd
    # list of query instances
    self.queries = list(qs)
    self.blockLength = 16
    self.blockStart = (0,1)
    self.message = " "*(self.blockLength+1)
    # default query is the one that comes up
    # if a button is pressed in IDLE mode
    self.defaultQuery = (self.queries) and qs[defaultQuery] or None
    self.btn = ((self.lcd.SELECT, 'Select'),
                (self.lcd.LEFT  , 'Left  '),
                (self.lcd.UP    , 'Up    '),
                (self.lcd.DOWN  , 'Down  '),
                (self.lcd.RIGHT , 'Right '))
    self.lastPressed = None
    self.lastState = IDLE
    self.saveState = IDLE
    self.state = IDLE
    self.timeOfState = time.time()

  def setDefaultQuery(self,defaultQuery=0):
    self.defaultQuery = self.queries[defaultQuery]

  def activateDefault(self):
    if self.defaultQuery: 
      # inactivate all queries
      for q in self.queries: q.active=False
      # activate the default query
      self.defaultQuery.active = True

  def activateQueryNum(self,queryNum):
    if queryNum >= 0 and queryNum < len(self.queries):
      # inactivate all queries
      for q in self.queries: q.active=False
      # activate query by number
      self.queries[queryNum].active = True

  def addQuery(self,query=Query(),makeDefault=True):
    self.queries.append(query)
    if makeDefault: self.defaultQuery = query

  def clearMessage(self):
    self.message = " "*(self.blockLength+1)
    
  def update(self,enterIdleState=False,
                  enterProcessState=False,
                  enterQueryState=False):
    """
    This is called for regular display updates,
    but since it is not scrolling if can also be called whenever a state
    changes, or needs to change.
    PROCESS, QUERY, and IDLE states can be requested
    """
    self.lastState = self.state

    # change state to OFF display if idle for too long
    if self.state == IDLE:
      if time.time()-self.timeOfState > IDLE_SLEEP_DELAY:
        self.state = OFF
    # enter (or re-enter) idle state if requested
    if enterIdleState:
      self.state = IDLE
      self.clearMessage()
    # enter process state if requested
    if enterProcessState:
      self.state = PROCESS
      self.clearMessage()
    # enter query state if requested
    if enterQueryState:
      self.state = QUERY
      self.clearMessage()
      
    # check buttons
    pressed = self.buttonCheck()
    
    if DEBUG: print "QB",self.state,pressed,self.lastPressed
    # has a button been pressed
    if pressed != None and self.lastPressed != pressed:
      if DEBUG: print "in loop"
      # change state back to IDLE if button pressed when OFF
      if self.state == OFF:
        self.state = IDLE
      # for anything else other than OFF
      else:
        # if a button is hit in PROCESS or IDLE go to QUERY
        # the process should activate its own query from 
        # another thread when it starts which will only
        # be displayed when QUERY is entered
        if (self.state == PROCESS or self.state == IDLE):
          self.activateDefault()
          self.state = QUERY
        elif self.state == QUERY:
          # we are in query mode and a button was pressed
          # lets find the active query
          # loop through all queries
          for q in self.queries:
            # is the query currently active?
            if q.active:
              if DEBUG: print "in active q",pressed
              # button actions
              if pressed == self.lcd.RIGHT:
                q.nextPosition()
              elif pressed == self.lcd.LEFT:
                q.prevPosition()
              elif pressed == self.lcd.UP:
                self.activateQueryNum(q.up)
              elif pressed == self.lcd.DOWN:
                self.activateQueryNum(q.down)
              elif pressed == self.lcd.SELECT:
                # loop through reponces to figure out which was picked
                for r in q.responses:
                  if q.position == r[1]:
                    # assign selected response to q attribute
                    q.selected = r
                # if we have a selected option and it needs
                # verification make a new verifier and 
                # append it to the queries list
                if q.selected and q.selected[2]:
                  # inactivate the query
                  q.active = False
                  # append a new verifier query to the queries list
                  self.queries.append(q.makeVerifier())
                # if we have a seleted option that does not need verification
                elif q.selected:
                  if DEBUG: print "in selected q no verify",pressed
                  # clear the query block
                  self.clearMessage()
                  # inactivate the query
                  q.active = False
                  # if this is a verifier remove it from the queries list
                  if isinstance(q,Verifier): self.queries.remove(q)
                  # do the action
                  if q.selected[3] and isinstance(q.selected[3],Action):
                    if DEBUG: print "in selected q do action",pressed
                    # update lastPressed in case the action does an update
                    self.lastPressed = pressed
                    # do the action
                    q.selected[3].do()
                    if DEBUG: print "in selected q after action",pressed
                  else:
                    print "no action for option"
                    print self.state
                else:
                  print "selection made on invalid position"
                  print self.state
              else:
                print pressed
                print self.state
              # only one active query allowed
              break
    
    self.lastPressed = pressed

    # whether or not a button was pressed lets update the message for an active query
    # if we are in QUERY mode
    if self.state == QUERY:
      for q in self.queries:
        # is this an active query
        if q.active:
          self.message = q.makeMessage(self.blockLength)
          # only one query should be active at a time
          break
      # if we are in QUERY mode with no active query
      else:
        self.clearMessage()
        # go back to last state
        if self.saveState != QUERY:
          self.state = self.saveState
          self.timeOfState = time.time()
        else:
          print "want to leave QUERY mode, but the saved state was also QUERY"
          print self.state

    # set time we entered a new state
    if self.state != self.lastState:
      self.saveState = self.lastState
      self.timeOfState = time.time()
      
    # update the display
    self.out = self.message
    self.lcd.setCursor(self.blockStart[0],self.blockStart[1])
    self.lcd.message(self.out)
    return self.state

  def buttonCheck(self):
    """
    has a button been pressed, return which one if it has
    if the update method is not called with high enough frequency
    button presses could be missed.
    """
    pressed = None
    for b in self.btn:
      if self.lcd.buttonPressed(b[0]):
        pressed = b[0]
    return(pressed)




class Display():
  """
  Creates a display command instance.
  Its update method calles the update method for all the blocks, and
  hence should be called at the frequency which updates are desired.
  """
  def __init__(self):    
    self.lcd = Adafruit_CharLCDPlate()
    self.lcd.begin(16,2)
    self.lcd.clear()
    self.lcd.home()
    self.time = TimeBlock(self.lcd)
    self.status = StatusBlock(self.lcd)
    self.query = QueryBlock(self.lcd)
    self.lastState = OFF
    self.state = OFF
    
  def update(self,state=None):
    self.time.update()
    self.status.update()
    # set our own lastState and state based on the query block
    self.lastState = self.query.lastState
    if state and state == IDLE:
      self.state = self.query.update(enterIdleState=True)
    elif state and state == PROCESS:
      self.state = self.query.update(enterProcessState=True)
    elif state and state == QUERY: self.state = self.query.update(enterQueryState=True)
    else: self.state = self.query.update()
    if DEBUG: print state,self.state

    # turn off if we just changed to OFF
    # turn on if we just changed from OFF
    if self.state == OFF and self.lastState != OFF:
      self.off()
    if self.state != OFF and self.lastState == OFF:
      self.on()

    if DEBUG: print self.state
      
  def on(self):
    self.query.update(enterIdleState=True)
    self.lcd.display()
    self.lcd.backlight(self.lcd.ON)

  def off(self):
    self.lcd.noDisplay()
    self.lcd.backlight(self.lcd.OFF)

  def fail(self,message=''):
    self.lcd.display()
    self.lcd.clear()
    self.lcd.home()
    self.lcd.backlight(self.lcd.ON)
    self.lcd.message("EPIC FAIL\n%s" % message)

if __name__ == '__main__':
  d = Display()
  d.status.message = "testing ..."
  d.query.addQuery(Query("?",[("A",7,True,Action('print "a"')),
                             ("B",9,False,Action('print dir()')),
                             ("C",11,True,Action('print self')),
                             ("D",13,False,None)],1),False)
  while (True):
    d.update()
    time.sleep(LOOP_DELAY)


