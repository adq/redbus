# -*- coding: utf-8 -*-
# Copyright 2010, 2011 Andrew De Quincey - adq@lidskialf.net
# Copyright 2010, 2011 Colin Paton - cozzarp@googlemail.com
# This file is part of rEdBus.
#
#  rEdBus is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  rEdBus is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with rEdBus.  If not, see <http://www.gnu.org/licenses/>.

import struct
import sys
import os
import urllib
import urllib2
import time
import lxml.html
from lxml import etree
import json
import hashlib
import dropbox
import settings
import tempfile
import gzip
import shutil
import argparse


def getLrtData():
    # Grab the list of all bus services
    services = {}
    resp = urllib2.urlopen("http://www.mybustracker.co.uk/")
    tree = lxml.html.fromstring(resp.read().decode('utf-8'))
    for option in tree.xpath("//select[@name='serviceRef']/option"):
        serviceCode = option.attrib["value"].strip()
        serviceName = option.text.split('-', 1)[0].strip()
        serviceRoute = option.text.split('-', 1)[1].strip()
        services[serviceName] = {'name': serviceName,
                                 'code': serviceCode,
                                 'route': serviceRoute,
                                 'provider': 'LRT',
                                 'stops': 0}

    # Now get all the stops
    stops = []
    seenStops = {}
    for service in services:
        params = urllib.parse.urlencode({'googleMapMode': '2',
                                         'googleServiceRef': services[service]['code'],
                                         })

        resp = urllib.request.urlopen("http://www.mybustracker.co.uk/update.php?widget=BTMap&widgetId=main&updateId=updateMap", params.encode('utf-8'))
        updateXml = etree.fromstring(resp.read())
        updateJson = json.loads(updateXml.xpath('/ajaxUpdate/updateElement')[0].text)

    #    if len(updateJson['deviations']):
    #        print(updateJson['deviations'])

        for m in updateJson['markers']:
            if 'content' not in m:
                continue

            stopName = m['content']['name']
            stopCode = m['content']['stopId']
            x = m['x']
            y = m['y']

            stopServices = []
            for curservicename in [name for (_code, name) in m['content']['lignes']]:
                service = services.get(curservicename)

                if service is None:
                    print >>sys.stderr, "Warning: Stop %s has services which do not exist (%s)" % (stopCode, service)
                else:
                    stopServices.append(service)
                    service['stops'] += 1

            # skip stops with no services arriving at them
            if len(stopServices) == 0:
                continue

            facing = ''
            marker = m['img']['url'].split('/')[-1]
            if marker == 'marker_0.png':
                facing = 'N'
            elif marker == 'marker_1.png':
                facing = 'NE'
            elif marker == 'marker_2.png':
                facing = 'E'
            elif marker == 'marker_3.png':
                facing = 'SE'
            elif marker == 'marker_4.png':
                facing = 'S'
            elif marker == 'marker_5.png':
                facing = 'SW'
            elif marker == 'marker_6.png':
                facing = 'W'
            elif marker == 'marker_7.png':
                facing = 'NW'
            elif marker == 'marker_x.png':
                facing = 'X'
            elif marker == 'diversion.png':
                facing = 'D'

            if stopCode is None or len(stopCode) == 0:
                print(m)
                continue

            if stopCode not in seenStops:
                stops.append({'code': stopCode,
                              'name': stopName,
                              'x':        x,
                              'y':        y,
                              'services': stopServices,
                              'facing':   facing,
                              'type':     'BCT',
                              'source':   'LRT'})
                seenStops[stopCode] = True

    return (services, stops)


# Algorithms "inspired by" wikipedia kd-tree page algorithms :-)
class Node:
    def write(self, treeFile, stopNamesFile, recordnumgen):
        # recurse on children
        leftfilepos=-1
        if self.leftChild:
            leftfilepos=self.leftChild.write(treeFile,stopNamesFile,recordnumgen)
        rightfilepos=-1
        if self.rightChild:
            rightfilepos=self.rightChild.write(treeFile,stopNamesFile,recordnumgen)

        # write out the stop name
        stopNameOffset = stopNamesFile.tell()
        stopNamesFile.write((self.details['name'] + '\0').encode('utf-8'))

        # figure out the facing field
        facing = 0
        if self.details['facing'] == 'N':
            facing |= 0x08 | 0
        elif self.details['facing'] == 'NE':
            facing |= 0x08 | 1
        elif self.details['facing'] == 'E':
            facing |= 0x08 | 2
        elif self.details['facing'] == 'SE':
            facing |= 0x08 | 3
        elif self.details['facing'] == 'S':
            facing |= 0x08 | 4
        elif self.details['facing'] == 'SW':
            facing |= 0x08 | 5
        elif self.details['facing'] == 'W':
            facing |= 0x08 | 6
        elif self.details['facing'] == 'NW':
            facing |= 0x08 | 7
        elif self.details['facing'] == 'X':
            facing |= 0x08 | 0x10
        elif self.details['facing'] == 'D':
            facing |= 0x08 | 0x20

        # bitmap of which services stop here
        stopmap = 0
        for service in self.details['services']:
            stopmap |= 1 << service['idx']

        # write the record
        treeFile.write(struct.pack(">hhIiiQQBI",
                                    leftfilepos,
                                    rightfilepos,
                                    self.details['code'],
                                    int(self.details['x'] * 1000000),
                                    int(self.details['y'] * 1000000),
                                    (stopmap >> 64) & 0xffffffffffffffff,
                                    stopmap & 0xffffffffffffffff,
                                    facing,  # note, 4 bits are unused here
                                    stopNameOffset
                                   ))
        return next(recordnumgen)


def makeKdTree(pointList, ndims=2, depth=0):
    if not pointList:
        return

    # Select axis based on depth so that axis cycles through all valid values
    axis = depth % ndims

    # Sort point list and choose median as pivot element
    pointList.sort(key=lambda point: point['x'] if axis == 0 else point['y'])
    median = int(len(pointList)/2)

    # Create node and construct subtrees
    node = Node()
    node.details = pointList[median]
    node.leftChild = makeKdTree(pointList[0:median], ndims, depth+1)
    node.rightChild = makeKdTree(pointList[median+1:], ndims, depth+1)
    return node


def makeStopsDat(services, stops, filename):
    # Check we don't have too many services or stops for current file format!
    if len(services) > 128:
        print >>sys.stderr, "Error: more than 128 services found - need to fix file format!"
        sys.exit(1)
    if len(stops) > 32767:
        print >>sys.stderr, "Error: more than 32767 stops found - need to fix file format!"
        sys.exit(1)

    # assign each service an internal idx, first sorting the names consistently so they map to the same IDs if there's been no actual change
    idx = 0
    for servicename in sorted(services.keys()):
        services[servicename]['idx'] = idx
        idx += 1

    # Open treefile and write header
    treeFile = tempfile.TemporaryFile()
    treeFile.write(struct.pack(">BBBB", ord('b'), ord('u'), ord('s'), ord('3')))  # magic "bus3"
    treeFile.write(struct.pack(">I", 0))  # integer root tree pos placeholder
    treeFile.write(struct.pack(">ii", 55946052, -3188879))  # Default map pos at centre of Edinburgh

    # Build + write the tree
    def recordnumgenerator():
        num=0
        while 1:
            yield num
            num+=1
    stopNamesFile = tempfile.TemporaryFile()
    rootpos = makeKdTree(stops).write(treeFile, stopNamesFile, recordnumgenerator())

    # append the stop names
    stopNamesFile.flush()
    stopNamesFile.seek(0, os.SEEK_SET)
    treeFile.write(stopNamesFile.read())
    stopNamesFile.close()

    # output the services
    treeFile.write(struct.pack('>i', len(services)))
    for service in sorted(services, key=lambda x: x['idx']):
        treeFile.write(struct.pack(">B", 0))  # service provider byte; currently 0 == LRT
        treeFile.write((service['name'] + '\0').encode('utf-8'))

    # update file headers
    treeFile.seek(4, os.SEEK_SET)
    treeFile.write(struct.pack('>i',rootpos))

    # gzip it into final output file
    treeFile.seek(0, os.SEEK_SET)
    with gzip.GzipFile(filename, 'w', 9) as f:
        f.write(treeFile.read())
    treeFile.close()


def dropboxKey(dropboxkey, dropboxsecret):
    flow = dropbox.client.DropboxOAuth2FlowNoRedirect(dropboxkey, dropboxsecret)
    authorize_url = flow.start()
    print '1. Go to: ' + authorize_url
    print '2. Click "Allow" (you might have to log in first)'
    print '3. Copy the authorization code.'
    code = raw_input("Enter the authorization code here: ").strip()
    access_token, user_id = flow.finish(code)
    print "Your access token is {}".format(access_token)


def dropboxUpload(srcfilename, destfilename):
    client = dropbox.client.DropboxClient(settings.DROPBOX_ACCESS_KEY)
    with open(srcfilename, 'rb') as f:
        client.put_file(destfilename, f)


def dropboxPurge():
    client = dropbox.client.DropboxClient(settings.DROPBOX_ACCESS_KEY)
    files = sorted(client.metadata('/stopdb/')['contents'], key=lambda x: x['path'], reverse=True)
    if len(files) > 5:
        for curfile in files[5:]:
            client.file_delete(curfile['path'])


def md5(filename):
    if not os.path.exists(filename):
        return ''

    m = hashlib.md5()
    with open(filename, 'r') as f:
        m.update(f.read())
    return m.digest()


def dopublish():
    # get and generate the data
    (services, stops) = getLrtData()
    makeStopsDat(services, stops, 'bus3.dat.gz')

    # do stuff with file if it was different from the previous one
    newmd5 = md5('bus3.dat.gz')
    oldmd5 = md5('bus3.dat.gz.old')
    if newmd5 != oldmd5:
        dropboxUpload('bus3.dat.gz', 'stopdb/bus3.dat-{}.gz'.format(int(time.time())))
        shutil.copyfile('bus3.dat.gz', 'bus3.dat.gz.old')
        # dropboxPurge()


def process():
    parser = argparse.ArgumentParser()
    subap = parser.add_subparsers()

    keyap = subap.add_parser('dropboxkey', help='Get an access key from dropbox')
    keyap.add_argument("dropboxkey", help='Dropbox key')
    keyap.add_argument("dropboxsecret", help='Dropbox secret')

    subap.add_parser('publishstops', help='Publish stops data')

    args = parser.parse_args()
    if hasattr(args, 'dropboxkey'):
        dropboxKey(args.dropboxkey, args.dropboxsecret)
    else:
        dopublish()


if __name__ == "__main__":  # pragma: nocoverage
    process()
