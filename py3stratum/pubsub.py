import weakref
from .connection_registry import ConnectionRegistry
from . import custom_exceptions
import hashlib
import random
import string
from . import logger
log = logger.get_logger('pubsub')

def subscribe(func):
    '''Decorator detect Subscription object in result and subscribe connection'''
    def inner(self, *args, **kwargs):
        subs = func(self, *args, **kwargs)
        return Pubsub.subscribe(self.connection_ref(), subs)
    return inner

def unsubscribe(func):
    '''Decorator detect Subscription object in result and unsubscribe connection'''
    def inner(self, *args, **kwargs):
        subs = func(self, *args, **kwargs)
        if isinstance(subs, Subscription):
            return Pubsub.unsubscribe(self.connection_ref(), subscription=subs)
        else:
            return Pubsub.unsubscribe(self.connection_ref(), key=subs)
    return inner

class Subscription(object):
    def __init__(self, event=None, params=None):
        if hasattr(self, 'event'):
            if event:
                raise Exception("Event name already defined in Subscription object")
        else:
            if not event:
                raise Exception("Please define event name in constructor")
            else:
                self.event = event

        self.params = params # Internal parameters for subscription object
        self.connection_ref = None
        self.client_id = None
        if self.params is not None and len(self.params) > 0:
            try:
                self.miner_version = self.params[0]
            except:
                self.miner_version = None
        self.worker_name = None
        self.worker_password = None

    def process(self, *args, **kwargs):
        return args

    def set_worker(self,session=None):
        if session is None:
            session = self.connection_ref().get_session()
        if self.worker_name is None or self.worker_password is None:
            if 'authorized' in session:
                for worker_name,worker_password in session['authorized'].items():
                    self.worker_name = worker_name
                    self.worker_password = worker_password

    def get_info(self):
        #log.debug("Subscription vars: %s" % str(vars(self)))

        if self.worker_name is None or self.worker_password is None:
            log.debug("Subscribe: (ID: %s), (IP: %s), (Miner Version: %s)" % (
                            str(self.get_key()),
                            str(self.connection_ref()._get_ip()),
                            str(self.miner_version)
                        )
                    )
        else:
            log.debug("Subscription: (ID: %s), (IP: %s), (Worker: %s), (Pass: %s), (Miner Version: %s)" % (
                            str(self.get_key()),
                            str(self.connection_ref()._get_ip()),
                            str(self.worker_name),
                            str(self.worker_password),
                            str(self.miner_version)
                        )
                    )

    def set_key(self,subscription_keys=[]):

        subscription_key=None

        while subscription_key==None:
            new_key = str( ''.join(random.choice(string.digits) for i in range(10)))
            if new_key not in subscription_keys:
                subscription_key = new_key
                #print("subscription_key:", subscription_key)
                continue
        self.client_id = subscription_key

    def get_key(self):
        return self.client_id
        '''This is an identifier for current subscription. It is sent to the client,
        so result should not contain any sensitive information.'''
        return hashlib.md5(str((self.event, self.params)).encode('utf-8')).hexdigest()
    
    def get_session(self):
        '''Connection session may be useful in filter or process functions'''
        return self.connection_ref().get_session()
        
    @classmethod
    def emit(cls, *args, **kwargs):
        '''Shortcut for emiting this event to all subscribers.'''
        if not hasattr(cls, 'event'):
            raise Exception("Subscription.emit() can be used only for subclasses with filled 'event' class variable.")
        return Pubsub.emit(cls.event, *args, **kwargs)
        
    def emit_single(self, *args, **kwargs):
        '''Perform emit of this event just for current subscription.'''
        conn = self.connection_ref()
        if conn == None:
            # Connection is closed
            return

        payload = self.process(*args, **kwargs)
        if payload != None:
            if isinstance(payload, (tuple, list)):
                conn.writeJsonRequest(self.event, payload, is_notification=True)
                self.after_emit(*args, **kwargs)
            else:
                raise Exception("Return object from process() method must be list or None")

    def after_emit(self, *args, **kwargs):
        pass
    
    # Once function is defined, it will be called every time
    #def after_subscribe(self, _):
    #    pass
    
    def __eq__(self, other):
        return (isinstance(other, Subscription) and other.get_key() == self.get_key())
    
    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.get_key())

class Pubsub(object):
    subscriptions = {}
    
    @classmethod
    def subscribe(cls, connection, subscription):
        if connection == None:
            raise custom_exceptions.PubsubException('Subscriber not connected')

        cls.subscriptions.setdefault(subscription.event, weakref.WeakKeyDictionary())

        subscription_keys = list(cls.subscriptions[subscription.event].keys())

        subscription.set_key(subscription_keys)

        key = subscription.get_key()

        session = ConnectionRegistry.get_session(connection)
        if session == None:
            raise custom_exceptions.PubsubException('No session found')
        
        subscription.connection_ref = weakref.ref(connection)
        session.setdefault('subscriptions', {})
        
        if key in session['subscriptions']:
            raise custom_exceptions.AlreadySubscribedException('This connection is already subscribed for such event.')
        
        session['subscriptions'][key] = subscription

        cls.subscriptions[subscription.event][subscription] = None

        subscription.get_info()

        if hasattr(subscription, 'after_subscribe'):
            if connection.on_finish != None:
                # If subscription is processed during the request, wait to
                # finish and then process the callback
                connection.on_finish.addCallback(subscription.after_subscribe)
            else:
                # If subscription is NOT processed during the request (any real use case?),
                # process callback instantly (better now than never).
                subscription.after_subscribe(True)
        
        # List of 2-tuples is prepared for future multi-subscriptions
        return ((subscription.event, key),)
    
    @classmethod
    def unsubscribe(cls, connection, subscription=None, key=None):
        if connection == None:
            raise custom_exceptions.PubsubException('Subscriber not connected')
        
        session = ConnectionRegistry.get_session(connection)
        if session == None:
            raise custom_exceptions.PubsubException('No session found')
        
        if subscription:
            key = subscription.get_key()

        try:
            # Subscription don't need to be removed from cls.subscriptions,
            # because it uses weak reference there.
            del session['subscriptions'][key]
        except KeyError:
            print("Warning: Cannot remove subscription from connection session")
            return False
            
        return True
        
    @classmethod
    def get_subscription_count(cls, event):
        return len(cls.subscriptions.get(event, {}))

    @classmethod
    def get_subscription(cls, connection, event, key=None):
        '''Return subscription object for given connection and event'''
        session = ConnectionRegistry.get_session(connection)
        if session == None:
            raise custom_exceptions.PubsubException('No session found')

        if key == None:    
            sub = [ sub for sub in list(session.get('subscriptions', {}).values()) if sub.event == event ]
            try:
                return sub[0]
            except IndexError:
                raise custom_exceptions.PubsubException('Not subscribed for event %s' % event)

        else:
            raise Exception('Searching subscriptions by key is not implemented yet')
              
    @classmethod
    def iterate_subscribers(cls, event):
        for subscription in cls.subscriptions.get(event, weakref.WeakKeyDictionary()).keyrefs():
            subscription = subscription()
            if subscription == None:
                # Subscriber is no more connected
                continue

            subscription.get_info()

            yield subscription
            
    @classmethod
    def emit(cls, event, *args, **kwargs):
        for subscription in cls.iterate_subscribers(event):                        
            subscription.emit_single(*args, **kwargs)

