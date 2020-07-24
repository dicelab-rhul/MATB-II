"""
    Defines eyetracking classes, most notably the Eyetracker class which interfaces with psychopy. 

    @Author: Benedict Wilkins
    @Date: 2020-04-02 21:49:01
"""

import threading

from collections import deque

from threading import Thread
import random

from time import sleep

from sys import version_info

if version_info.major + version_info.minor / 10 < 3.7:
    from time import time
else:
    from time import time_ns as time

from .. import event

from . import filter

__all__ = ('filter',)


class EyeTrackingError(Exception):
    """ 
        An error that may be thrown by an EyeTracker, typically will wrap a psychopy error.
    """
    
    def __init__(self, message, cause=None):
        super(EyeTrackingError, self).__init__(message)
        if cause is not None:
            self.__cause__ = cause

class EyeTrackerBase(event.EventCallback, threading.Thread):

    def __init__(self, filter=None, **kwargs):

        super(EyeTrackerBase, self).__init__(**kwargs)
        if filter is None:
            filter =lambda t,x,y:dict(timestamp=t,x=x,y=y,label="place")
            
        self.__filter = filter

    def source(self, x, y, timestamp=None):
        e = self.__filter(timestamp,x,y)
        #transform to screen window coordinates
        if e is not None:
            super().source('Overlay:0', **e)

class EyeTracker(EyeTrackerBase):

    def __init__(self, filter=None, sample_rate = 300, calibrate=True):
        super(EyeTracker, self).__init__(filter)
        self.daemon = True #??? TODO any issue with this closing down psychopy?
        #https://stackoverflow.com/questions/40391812/running-code-when-closing-a-python-daemon
        try:
            from psychopy.iohub import launchHubServer
        except Exception as e:
            raise EyeTrackingError("IMPORT FAILED.", cause=e)

        #self.io = connect_eyetracker(sample_rate = sample_rate)
    
        iohub_config = {'eyetracker.hw.tobii.EyeTracker':
                       {'name':'tracker','runtime_settings':{'sampling_rate':sample_rate}}}
        self.io = launchHubServer(**iohub_config)    
        self.tracker = self.io.devices.tracker
        self.sample_rate = sample_rate
        
        if calibrate:
            if not self.tracker.runSetupProcedure():
                print("WARNING: EYETRACKER CALIBRATION FAILED")
        
        self.closed = threading.Event()
        name = "{0}:{1}".format(EyeTracker.__name__, str(0))
        self.register(name)
            
    def run(self):
    
        self.tracker.setRecordingState(True) #what is this?
        while not self.closed.is_set():
            for e in self.tracker.getEvents(asType='dict'): #this might cause the thread to hang... TODO fix it!
                self.source(x=e['left_gaze_x'], y=e['left_gaze_y'], timestamp=e['time'])
        self.io.quit()
    
    def close(self):
        self.closed.set()

class EyeTrackerStub(EyeTrackerBase):
    """ 
        A stub EyeTracker class that uses the current mouse position as a stand in for gaze position, 
        use for testing without eyetracking hardware.
    """

    def __init__(self, root, filter=None, sample_rate = 300, **kwargs):
        super(EyeTrackerStub, self).__init__(filter, **kwargs)
        self.daemon = True
        self.sample_rate = sample_rate
        self.__time = 0
        root.bind("<Motion>", self.update)

        self.closed = threading.Event()
        self.register(self.__class__.__name__)

        self._p_mouse_x = 0
        self._p_mouse_y = 0

        self._n_mouse_x = 0
        self._n_mouse_y = 0
    
    def update(self, event):
        """ 
            Called when the mouse moves, updates internal mouse (x,y).

            Args:
                event (mouseevent): a mouse event generated that defines x,y attributes.
        """
        self._n_mouse_x = event.x
        self._n_mouse_y = event.y

    def run(self):
        """
            Generates events that move the current overlay (if it exists).
        """
        while not self.closed.is_set():
            self.__time += 1
            sleep(1. / self.sample_rate)
            #self.source('Overlay:Overlay', label='move', dx=random.randint(0,10), dy=random.randint(0,10), timestamp=self.__time)
            #if self._p_mouse_x != self._n_mouse_x or self._p_mouse_y != self._n_mouse_y:
            self.source(time(), self._n_mouse_x, self._n_mouse_y)
            
            self._p_mouse_x = self._n_mouse_x
            self._p_mouse_y = self._n_mouse_y

    def close(self):
        """ 
            Force the thread to exit.
        """
        self.closed.set()

def eyetracker(root, filter=None, sample_rate=300, calibrate=True, stub=False):
    """ Creates a new Eyetracker (there should only ever be one).
    Args:
        root (tk): tk root window.
        filter: a filter for x,y - averaging, gaze points etc (see eyetracker.filter)
        sample_rate (int, optional): number of samples (events) per second. Defaults to 300.
        calibrate (bool, optional): calibrate the eyetracker. Defaults to True.
        stub (bool, optional): use a stub class (see StubEyeTracker) if hardware is not available. Defaults to False.
    
    Returns:
        (EyeTracker): The new EyeTracker.
    """ 
    if not stub:
        try:
            return EyeTracker(filter=filter, sample_rate=sample_rate, calibrate=calibrate)
        except:
            print("FAILED TO INITIALISE EYE TRACKER DUE TO:")
            traceback.print_exc()
            print(" ---- USING STUB EYETRACKER (MOUSE COORDINATE)")
    return EyeTrackerStub(root, filter=filter, sample_rate=sample_rate)

