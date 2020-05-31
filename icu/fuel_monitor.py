import tkinter as tk
import random
import copy

from . import config as configuration

from .constants import BACKGROUND_COLOUR, FUEL_TANK_LINE_THICKNESS, FUEL_TANK_LINE_COLOUR, COLOUR_GREEN, COLOUR_RED, COLOUR_LIGHT_BLUE, COLOUR_BLUE
from .constants import PUMP_HEIGHT, PUMP_WIDTH, OUTLINE_COLOUR, OUTLINE_WIDTH, PUMP_EVENT_RATE, PUMP_FLOW_RATE, PUMP_FAIL_SCHEDULE
from .constants import WARNING_OUTLINE_COLOUR, WARNING_OUTLINE_WIDTH, TANK_ACCEPT_POSITION, TANK_ACCEPT_PROPORTION


from . import event

from .event import Event, EventCallback

from .component import Component, CanvasWidget, SimpleComponent, BoxComponent, LineComponent
from .highlight import Highlight


from pprint import pprint
from itertools import cycle

EVENT_NAME_FAIL = "fail"
EVENT_NAME_TRANSFER = "transfer"
EVENT_NAME_REPAIR = "repair"
EVENT_NAME_HIGHLIGHT = "highlight"  


class FuelTank(EventCallback, Component, CanvasWidget):

    def __init__(self, canvas, x, y, width, height, capacity, fuel, name, highlight):
        super(FuelTank, self).__init__(canvas, x=x, y=y, width=width, height=height, background_colour=BACKGROUND_COLOUR)

        name = "{0}:{1}".format(FuelTank.__name__, name)
        EventCallback.register(self, name)
        Component.register(self, name)

        self.capacity = capacity
        self.fuel = fuel

        fh = (self.fuel / self.capacity) * height
       
        self.components['fuel'] = BoxComponent(canvas, x=x, y=y+height-fh, width=width, height=fh, colour=COLOUR_GREEN, outline_thickness=0)
        self.components['outline'] = BoxComponent(canvas, x=x, y=y, width=width, height=height, outline_thickness=FUEL_TANK_LINE_THICKNESS, outline_colour=FUEL_TANK_LINE_COLOUR)
       
        self.highlight = Highlight(canvas, self, **highlight)

    def sink(self, event):
        pass #updates are handled by pump events

    def update(self, dfuel):
        self.fuel = min(max(self.fuel + dfuel, 0), self.capacity)
        
        fh = (self.fuel / self.capacity) * self.height
        self.components['fuel'].y = self.y + self.height - fh
        self.components['fuel'].height = fh

    def to_dict(self):
        dict(capacity=self.capacity, fuel=self.fuel, highlight=self.highlight.to_dict())

class FuelTankMain(FuelTank):

    def __init__(self, canvas, x, y, width, height, capacity, fuel, name, highlight):
        super(FuelTankMain, self).__init__(canvas, x, y, width, height, capacity, fuel, name, highlight)

        py = height*TANK_ACCEPT_POSITION - height*(TANK_ACCEPT_PROPORTION/2)
        lx, ly, lw = x-0.1*width, y + py, width + width/5
        lh = height * TANK_ACCEPT_PROPORTION

        self.components['limit_box'] = BoxComponent(canvas, x=lx, y=ly, width=lw, height=lh, colour=COLOUR_LIGHT_BLUE, outline_thickness=0)
        self.components['limit_line'] = LineComponent(canvas, lx, ly + lh/2, lx + lw, ly + lh/2, colour=COLOUR_BLUE, thickness=3)
        self.components['back'] = BoxComponent(canvas, x=x, y=y, width=width, height=height, colour=BACKGROUND_COLOUR, outline_thickness=0)
        self.components['fuel'].front()
        self.components['outline'].front()
        
        # in out of limits
        lim = self.limits
        self.__trigger_enter = self.fuel > lim[0] and self.fuel < lim[1]
        self.__trigger_leave = not self.__trigger_enter

    @property
    def limits(self):
        cy, ch = self.capacity*TANK_ACCEPT_POSITION, self.capacity*(TANK_ACCEPT_PROPORTION/2)
        return cy - ch, cy + ch

    def update(self, dfuel):
        super(FuelTankMain, self).update(dfuel)
        lim = self.limits
        if self.fuel > lim[0] and self.fuel < lim[1]:
            #print("in", lim, self.fuel)
            #within the acceptable area
            if self.__trigger_enter:
                self.source('Global', label='fuel', acceptable=True)
                self.__trigger_enter = False
                self.__trigger_leave = True
        else:
            #print("out", lim, self.fuel)
            if self.__trigger_leave:
                self.source('Global', label='fuel', acceptable=False)
                self.__trigger_leave = False
                self.__trigger_enter = True

class FuelTankInfinite(FuelTank):

    def __init__(self, *args, **kwargs):
        super(FuelTankInfinite, self).__init__(*args, **kwargs)

    def update(self, dfuel):
        pass

class Pump(EventCallback, Component, CanvasWidget):

    __components__ = {} #just names

    def all_components():
        return {k:v for k,v in Pump.__components__.items()}

    ON_COLOUR = COLOUR_GREEN
    OFF_COLOUR = BACKGROUND_COLOUR
    FAIL_COLOUR = COLOUR_RED
    COLOURS = [ON_COLOUR, OFF_COLOUR, FAIL_COLOUR]

    def __init__(self, canvas, config, x, y, width, height, tank1, tank2, text, state=1, highlight={}):
        super(Pump, self).__init__(canvas, x=x, y=y, width=width, height=height, background_colour=Pump.COLOURS[state], outline_thickness=OUTLINE_WIDTH)

        name = "{0}{1}".format(tank1.name.split(':')[1], tank2.name.split(':')[1])
        name = "{0}:{1}".format(Pump.__name__, name)
        
        default_config = configuration.default_pump_config()
        config = config.get(name, default_config)

        self.flow_rate = config.get('flow_rate', default_config['flow_rate'])
        self.event_rate = config.get('event_rate', default_config['event_rate'])

        EventCallback.register(self, name)
        Component.register(self, name)

        #parent.pumps[self.name] = self
        self.__state = state
        self.tank1 = tank1
        self.tank2 = tank2

        self.bind("<Button-1>", self.click_callback) #bind mouse events

        #self.generator = PumpEventGenerator(self, flow_rate=PUMP_FLOW_RATE[self.name.split(":")[1]], event_rate=PUMP_EVENT_RATE)

        self.highlight = Highlight(canvas, self, **highlight)

        assert self.name not in Pump.__components__
        Pump.__components__[self.name] = self

    def start(self):
        event.event_scheduler.schedule(self.__transfer(), sleep=cycle([int(1000/self.event_rate)]))

    def __transfer(self):
        while self.state == 0: #on
            yield self.transfer()

    def transfer(self):
        print("TRANSFER")
        if self.tank1.fuel == 0 or self.tank2.fuel == self.tank2.capacity:
            return None #no event...

        flow = self.flow_rate / self.event_rate
        self.tank1.update(-flow)
        self.tank2.update(flow)
        return Event(self.name, 'Global', label=EVENT_NAME_TRANSFER, value=flow) #has no effect

    def to_dict(self):
        return dict(state=self.state, highlight=self.highlight.to_dict())

    @property
    def name(self):
        return self._Component__name

    @property
    def state(self):
        return self.__state

    @state.setter
    def state(self, value):
        self.__state = value
        self.background_colour = Pump.COLOURS[value]
        if value == 0:
            self.start()

    def highlight(self, state):
        self.highlight_state = state
        self.canvas.itemconfigure(self.highlight_rect, state=('hidden', 'normal')[state])

    def click_callback(self, *args):
        print('click')
        if self.state != 2: #the pump has failed
            self.state = abs(self.__state - 1)

        self.source('Global', label='click', value=self.state) #notify global


    def sink(self, event):
        if event.data.label == EVENT_NAME_TRANSFER: #this may never happen... the event generator is now internal TODO refactor
            self.tank1.update(-event.data.value)
            self.tank2.update(event.data.value)
        elif event.data.label == EVENT_NAME_FAIL:
            self.state = 2 # failed (unusable)
        elif event.data.label == EVENT_NAME_REPAIR:
            self.state = 1 # not transfering (useable)


class Wing(CanvasWidget):
    
    def __init__(self, canvas, config, small_tank_name, med_tank_name, big_tank_name, highlight):
        super(Wing, self).__init__(canvas)

        width = height = 1 #everything will scale relative to the super widget

        #create full tanks
        fts = width / 4

        ftw_small = width / 6
        ftw_med = ftw_small * 1.4
        ftw_large = ftw_small * 2

        fth = height / 3
        margin = 0.05 #using padding here is a bit too tricky, maybe update TODO


        self.components['link'] = BoxComponent(canvas, x=fts, y=margin + fth/2 + fth/3, width=2 * fts, height=height-2*margin - fth - fth/3, outline_thickness=OUTLINE_WIDTH)
        
        self.components['tank1'] = FuelTank(canvas, fts - ftw_small/2, height - margin - fth, ftw_small, fth, 1000, 100, small_tank_name, highlight)
        self.components['tank2'] = FuelTankInfinite(canvas, 3 * fts - ftw_med/2, height - margin - fth, ftw_med, fth, 2000, 1000, med_tank_name, highlight)
        self.components['tank3'] = FuelTankMain(canvas, 2 * fts - ftw_large/2, margin, ftw_large, fth, 3000, 1000, big_tank_name, highlight)

        self.tanks = {small_tank_name:self.components['tank1'], med_tank_name:self.components['tank2'], big_tank_name:self.components['tank3']}

        #create pumps
        cx = (fts + ftw_small/2)
        ex = (3 * fts - ftw_med/2)
        ecx = (cx + ex) / 2
        ecy = height - margin - fth / 2

        pw = width / 16
        ph = height / 20

        self.components['pump21'] = Pump(canvas, config, ecx - pw/2, ecy - ph/2, pw, ph, self.components['tank2'], self.components['tank1'], "<", highlight=highlight)
        self.components['pump13'] = Pump(canvas, config, fts - pw/2, height/2 - ph/2, pw, ph, self.components['tank1'], self.components['tank3'], '^', highlight=highlight)
        self.components['pump23'] = Pump(canvas, config, 3 * fts - pw/2, height /2 - ph/2, pw, ph, self.components['tank2'], self.components['tank3'], '^', highlight=highlight)
       
        #self.components['link'].back()
   
class FuelWidget(CanvasWidget):

    def __init__(self, canvas, config, width, height):
        super(FuelWidget, self).__init__(canvas, width=width, height=height, background_colour=BACKGROUND_COLOUR)

        self.tanks = {}
        self.pumps = {}

        highlight = config['overlay'] #highlight options
        
        self.wing_left  = Wing(canvas, config, "C", "E", "A", highlight)
        self.wing_right = Wing(canvas, config, "D", "F", "B", highlight)
        
        self.tanks.update(self.wing_left.tanks)
        self.tanks.update(self.wing_right.tanks)

        self.components['wl'] = self.wing_left
        self.components['wr'] = self.wing_right

        self.layout_manager.fill('wl', 'Y')
        self.layout_manager.fill('wr', 'Y')
        self.layout_manager.split('wl', 'X', .5)
        self.layout_manager.split('wr', 'X', .5)
        
        (ax, ay) = self.tanks['A'].position
        (aw, ah) = self.tanks['A'].size
        ax = ax + aw / 2
        ay = ay + ah / 2

        (bx, by) = self.tanks['B'].position
        (bw, bh) = self.tanks['B'].size

        bx = bx + bw / 2
        by = by + bh / 2

        self.components['AB'] = SimpleComponent(canvas, canvas.create_line(ax+aw/2,ay-ah/6,bx-bw/2,by-bh/6, width=OUTLINE_WIDTH))
        self.components['BA'] =  SimpleComponent(canvas, canvas.create_line(ax+aw/2,ay+ah/6,bx-bw/2,by+bh/6, width=OUTLINE_WIDTH))

        w,h = self.wing_left.components['pump21'].size

        self.components['pumpAB'] = Pump(canvas, config, (ax+bx)/2, ay-ah/6 - h/2, w, h, self.tanks['A'], self.tanks['B'], ">", highlight=highlight)
        self.components['pumpBA'] = Pump(canvas, config, (ax+bx)/2, ay+ah/6 - h/2, w, h, self.tanks['B'], self.tanks['A'], "<", highlight=highlight)

        print(Pump.all_components().keys())

    def highlight(self, child=None):
        if child is None:
            print("highlight self")
        elif child in self.pumps:
            print("highlight pump")
            pump = self.pumps[child]

        elif child in self.tanks:
            print("highlight tank")
        else:
            raise ValueError("Invalid child widget: {0}".format(child))