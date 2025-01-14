from twisted.python import log
import py3stratum
import platform

print("Python Version:", platform.python_version())

import py3stratum.settings as settings

# This variable is used as an application handler by twistd 
application = py3stratum.setup()

from twisted.internet import reactor

def heartbeat():
    log.msg('heartbeat')
    reactor.callLater(60, heartbeat)

if settings.DEBUG:
    reactor.callLater(0, heartbeat)

# Load all services from service_repository module.
try:
    import service_repository
except ImportError:
    print ("***** Is service_repository missing? Add service_repository module to your python path!")