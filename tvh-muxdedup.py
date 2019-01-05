#! /usr/bin/env python3

#
# TVH json import/export tool, requires python3
#

import os
import sys
import json
import traceback
import urllib.request as urllib
from urllib.parse import urlencode, quote

def env(key, deflt):
    if key in os.environ: return os.environ[key]
    return deflt

DEBUG=False

TVH_API=env('TVH_API_URL', 'http://localhost:9981/api')
TVH_USER=env('TVH_USER', None)
TVH_PASS=env('TVH_PASS', None)
TVH_AUTH=env('TVH_AUTH', 'digest')
PWD_MGR = urllib.HTTPPasswordMgrWithDefaultRealm()
PWD_MGR.add_password(None, TVH_API, TVH_USER, TVH_PASS)

class Response(object):
    def __init__(self, response):
        self.url = response.geturl()
        self.code = response.getcode()
        self.reason = response.msg
        self.headers = response.info()
        self.body = None
        self.ctype = None
        if 'Content-type' in self.headers:
            self.ctype = self.headers['Content-type'].split(';')[0]
            if self.ctype in ['text/x-json', 'application/json']:
                self.body = json.loads(response.read().decode('utf-8'))
        if not self.body:
          self.body = response.read()

def error(lvl, msg, *args):
    sys.stderr.write(msg % args + '\n')
    sys.exit(lvl)

def info(msg, *args):
    print('TVH: ' + msg % args)

class TVHeadend(object):

    def __init__(self, path, headers=None):
        self._headers = headers or {}
        self._path = path or []

    def opener(self):
        handlers = []
        if TVH_AUTH == 'digest':
            handlers.append(urllib.HTTPDigestAuthHandler(PWD_MGR))
        elif TVH_AUTH == 'basic':
            handlers.append(urllib.HTTPBasicAuthHandler(PWD_MGR))
        else:
            handlers.append(urllib.HTTPDigestAuthHandler(PWD_MGR))
            handlers.append(urllib.HTTPBasicAuthHandler(PWD_MGR))
        if DEBUG:
            handlers.append(urllib.HTTPSHandler(debuglevel=1))
        return urllib.build_opener(*handlers)

    def _push(self, data, binary=None, method='PUT'):
        content_type = None
        if binary:
          content_type = 'application/binary'
        else:
          data = data and urlencode(data).encode('utf-8') or None
        opener = self.opener()
        path = self._path
        if path[0] != '/': path = '/' + path
        request = urllib.Request(TVH_API + path, data=data)
        if content_type:
            request.add_header('Content-Type', content_type)
        request.get_method = lambda: method
        try:
            r = Response(opener.open(request))
        except urllib.HTTPError as e:
            r = Response(e)
        return r

    def get(self, binary=None):
        return self._push(None, method='GET')

    def post(self, data):
        return self._push(data, method='POST')

def do_get0(*args):
    if len(args) < 1: error(1, 'get [path] [json_query]')
    path = args[0]
    query = None
    if len(args) > 1:
        query = args[1]
        if type(query) != type({}):
            query = json.loads(query.decode('utf-8'))
    if query:
        for q in query:
            r = query[q]
            if type(r) == type({}) or type(r) == type([]):
                query[q] = json.dumps(r)
    resp = TVHeadend(path).post(query)
    if resp.code != 200 and resp.code != 201:
        error(10, 'HTTP ERROR "%s" %s %s', resp.url, resp.code, resp.reason)
    return resp.body

def main(argv):
    global DEBUG
    global DRYRUN
    if not TVH_USER or not TVH_PASS:
        error(2, 'No credentials')
    for arg in argv:
        if arg == '--debug':
            DEBUG = True
        if arg in ['--no-dry-run','--nodryrun']:
            DRYRUN = False
    do_dedup()

if __name__ == "__main__":
    main(sys.argv)
