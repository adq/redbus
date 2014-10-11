#!/usr/bin/env python2.7

import dropbox
import argparse
import os

def doauth(args):
    flow = dropbox.client.DropboxOAuth2FlowNoRedirect(args.dropboxkey, args.dropboxsecret)
    authorize_url = flow.start()
    authorize_url = flow.start()
    print '1. Go to: ' + authorize_url
    print '2. Click "Allow" (you might have to log in first)'
    print '3. Copy the authorization code.'
    code = raw_input("Enter the authorization code here: ").strip()
    access_token, user_id = flow.finish(code)
    print "Your access token is {}".format(access_token)


def doupload(args):
    client = dropbox.client.DropboxClient(args.accesskey)
    with open(args.filename, 'rb') as f:
        client.put_file('stopdb/' + os.path.split(args.filename)[1], f)

def process():
    parser = argparse.ArgumentParser()
    subap = parser.add_subparsers()

    keyap = subap.add_parser('key', help='Get an access key from dropbox')
    keyap.add_argument("dropboxkey", help='Dropbox key')
    keyap.add_argument("dropboxsecret", help='Dropbox secret')

    uploadap = subap.add_parser('upload', help='Upload a file to dropbox')
    uploadap.add_argument("accesskey", help='Dropbox access key')
    uploadap.add_argument("filename", help='Filename to upload')

    args = parser.parse_args()
    if hasattr(args, 'dropboxkey'):
        doauth(args)
    else:
        doupload(args)

if __name__ == "__main__":  # pragma: nocoverage
    process()
