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
import urllib.request
import urllib.parse
import datetime
import time
import re
import lxml.html
from lxml import etree
import json


def getLrtData():
    # Grab the list of all bus services
    services = {}
    resp = urllib.request.urlopen("http://www.mybustracker.co.uk/")
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
    stops = {}
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

            if not stopCode in stops:
                stops[stopCode] = {'code': stopCode,
                                   'name': stopName,
                                   'x':        x,
                                   'y':        y,
                                   'services': stopServices,
                                   'facing':   facing,
                                   'type':     'BCT',
                                   'source':   'LRT'}

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
        for service in stop['services']:
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


def makeStopsDat(services, stops, destfile):
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
    treeFile = open(destfile + ".tree", "wb")
    treeFile.write(struct.pack(">BBBB", ord('b'), ord('u'), ord('s'), ord('3')))  # magic
    treeFile.write(struct.pack(">I", 0))  # integer root tree pos placeholder
    treeFile.write(struct.pack(">ii", 55946052, -3188879))  # Default map pos at centre of Edinburgh

    # The stop names file
    stopNamesFile = open(destfile + ".stopnames", "wb")

    # Build + write the tree
    def recordnumgenerator():
        num=0
        while 1:
            yield num
            num+=1
    rootpos = makeKdTree(stops).write(treeFile, stopNamesFile, recordnumgenerator())

    # output file headers and close 'em
    treeFile.seek(4, os.SEEK_SET)
    treeFile.write(struct.pack('>i',rootpos))
    treeFile.close()
    stopNamesFile.close()

    # output the services
    servicesFile = open(destfile + ".services", "wb")
    servicesFile.write(struct.pack('>i', len(servicesList)))
    for service in servicesList:
        servicesFile.write(struct.pack(">B", 0))  # service provider byte; currently 0 == LRT
        servicesFile.write((service['ServiceName'] + '\0').encode('utf-8'))
    servicesFile.close()


def dropboxKey(dropboxkey, dropboxsecret):
    flow = dropbox.client.DropboxOAuth2FlowNoRedirect(dropboxkey, dropboxsecret)
    authorize_url = flow.start()
    print '1. Go to: ' + authorize_url
    print '2. Click "Allow" (you might have to log in first)'
    print '3. Copy the authorization code.'
    code = raw_input("Enter the authorization code here: ").strip()
    access_token, user_id = flow.finish(code)
    print "Your access token is {}".format(access_token)


def dropboxUpload(accesskey, filename):
    client = dropbox.client.DropboxClient(accesskey)
    with open(filename, 'rb') as f:
        client.put_file('stopdb/' + os.path.split(filename)[1], f)


def dopublish():


    . /etc/redbus.conf

    INSTDIR=/usr/local/redbus/stopdb

    nowdate=`date +%Y-%m-%dT%H:%M:%S`
    dataformat=bus3

    # Download data from remote sites
    $INSTDIR/getlrtdata $nowdate || exit 1

    # Extract stops from XML
    #$INSTDIR/getnaptandata $INSTDIR/stopdata/NaPTAN620.xml $nowdate || exit 1
    #$INSTDIR/getnaptandata $INSTDIR/stopdata/NaPTAN627.xml $nowdate || exit 1
    #$INSTDIR/getnaptandata $INSTDIR/stopdata/NaPTAN628.xml $nowdate || exit 1

    # Generate new stops database
    $INSTDIR/makestopsdat $INSTDIR/$dataformat $nowdate || exit 1
    cat $INSTDIR/$dataformat.tree $INSTDIR/$dataformat.services $INSTDIR/$dataformat.stopnames > $INSTDIR/$dataformat.dat
    /usr/bin/gzip -n -f -9 $INSTDIR/$dataformat.dat || exit 1
    newsum=`/usr/bin/md5sum $INSTDIR/$dataformat.dat.gz | cut -f1 -d ' '` || exit 1

    # handle old data
    if [ ! -f $INSTDIR/$dataformat.dat.gz.old ]; then
      echo "Old data file is missing!"
      exit 1
    fi
    oldsum=`/usr/bin/md5sum $INSTDIR/$dataformat.dat.gz.old | cut -f1 -d ' '` || exit 1
    rm -f $INSTDIR/$dataformat.dat.gz.old
    cp -f $INSTDIR/$dataformat.dat.gz $INSTDIR/$dataformat.dat.gz.old

    # Publish if something has changed!
    if [ x$oldsum != x$newsum ]; then
      OUTFILE=$dataformat.dat-`date +%s`.gz
      mv $INSTDIR/$dataformat.dat.gz $INSTDIR/$OUTFILE
      $INSTDIR/dropbox_upload.py upload $DROPBOX_ACCESS_KEY $INSTDIR/$OUTFILE || exit 1
      rm -f $OUTFILE
    else
      # Otherwise, no changed => delete the duplicated data from the database
      $INSTDIR/removedata LATEST
    fi


def process():
    parser = argparse.ArgumentParser()
    subap = parser.add_subparsers()

    keyap = subap.add_parser('dropboxkey', help='Get an access key from dropbox')
    keyap.add_argument("dropboxkey", help='Dropbox key')
    keyap.add_argument("dropboxsecret", help='Dropbox secret')

    uploadap = subap.add_parser('publishstops', help='Publish stops data')

    args = parser.parse_args()
    if hasattr(args, 'dropboxkey'):
        dropboxKey(args.dropboxkey, args.dropboxsecret)
    else:
        dopublish()


if __name__ == "__main__":  # pragma: nocoverage
    process()
