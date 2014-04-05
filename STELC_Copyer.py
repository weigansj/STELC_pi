#!/usr/bin/python
"""
used by STELC_pi to mount an inserted USB drive
copy over the wav and log files and unmount the drive
usb related classes originally from a March 17, 2014
stackoverflow.com post by SpiRail
"""
import re
import subprocess

#used as a quick way to handle shell commands
def getFromShell_raw(command):
    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.readlines()

def getFromShell(command):
    result = getFromShell_raw(command)
    for i in range(len(result)):       
        result[i] = result[i].strip() # strip out white space
    return result



class Mass_storage_device(object):
    def __init__(self, device_file):
       self.device_file = device_file
       self.mount_point = None

    def as_string(self):
        return "%s -> %s" % (self.device_file, self.mount_point)

    """ check if we are already mounted"""
    def is_mounted(self):
        result = getFromShell('mount | grep %s' % self.device_file)
        if result:
            dev, on, self.mount_point, null = result[0].split(' ', 3)
            return True
        return False

    """ If not mounted, attempt to mount """
    def mount(self):
        if not self.is_mounted():
            result = getFromShell('udisks --mount %s' % self.device_file)[0] #print result
            if re.match('^Mounted',result): 
                mounted, dev, at, self.mount_point = result.split(' ')

        return self.mount_point

    def unmount(self):
        if self.is_mounted():
            result = getFromShell('udisks --unmount %s' % self.device_file) #print result
            self.mount_point=None

    def eject(self):
        if self.is_mounted():
            self.unmount()
        result = getFromShell('udisks --eject %s' % self.device_file) #print result
        self.mount_point=None


class Mass_storage_management(object):
    def __init__(self, label=None):
        self.label = label
        self.devices = [] 
        self.devices_with_label(label=label)

    def refresh(self):
        self.devices_with_label(self.label)

    """ Uses udisks to retrieve a raw list of all the /dev/sd* devices """
    def get_sd_list(self):
        devices = []
        for d in getFromShell('udisks --enumerate-device-files'):
            if re.match('^/dev/sd.$',d): 
                devices.append(Mass_storage_device(device_file=d))
        return devices


    """ takes a list of devices and uses udisks --show-info 
    to find their labels, then returns a filtered list"""
    def devices_with_label(self, label=None):
        self.devices = []
        for d in self.get_sd_list():
            if label is None:
                self.devices.append(d)
            else:
                match_string = 'label:\s+%s' % (label)
                for info in getFromShell('udisks --show-info %s' % d.device_file):
                    if re.match(match_string,info): self.devices.append(d)
        return self

    def as_string(self):
        string = ""
        for d in self.devices:
            string+=d.as_string()+'\n'
        return string

    def mount_all(self): 
        for d in self.devices: d.mount()

    def unmount_all(self): 
        for d in self.devices: d.unmount()

    def eject_all(self): 
        for d in self.devices: d.eject()
        self.devices = []



if __name__ == '__main__':
    name = 'my devices'
    m = Mass_storage_management(name)
    print m.as_string()

    print "mounting"
    m.mount_all()
    print m.as_string()

    print "un mounting"
    m.unmount_all()
    print m.as_string()

    print "ejecting"
    m.eject_all()
    print m.as_string()
