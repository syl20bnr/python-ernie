import inspect
import sys
import os
import logging
import bert
import struct
# For windows: Force binary mode for stdin and stdout in order to prevent
# behind the scene conversions of '\n' to '\r\n' and 26 to EOF.
# Sources:
# http://erlang.org/pipermail/erlang-questions/2003-December/010976.html
# http://www.gossamer-threads.com/lists/python/python/68639
try:
    import msvcrt
    msvcrt.setmode(sys.stdin.fileno(),  os.O_BINARY) 
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY) 
except Exception:
    pass


class Ernie(object):
    mods = {}
    logger = None

    @classmethod
    def mod(cls, name):
        if cls.mods.has_key(name) == False:
            cls.mods[name] = Mod(name)
        return cls.mods[name]

    @classmethod
    def logfile(cls, file):
        logging.basicConfig(filename=file,level=logging.DEBUG)
        cls.logger = logging.getLogger('ernie')

    @classmethod
    def log(cls, text):
        if cls.logger != None:
            cls.logger.debug(text)

    def dispatch(self, mod, fun, args):
        if Ernie.mods.has_key(mod) == False:
            raise ServerError("No such module '" + mod + "'")
        if Ernie.mods[mod].funs.has_key(fun) == False:
            raise ServerError("No such function '" + mod + ":" + fun + "'")
        return Ernie.mods[mod].funs[fun](*args)

    def read_4(self, input):
        raw = input.read(4)
        if len(raw) == 0:
            return None
        return struct.unpack('!L', raw)[0]

    def read_berp(self, input):
        packet_size = self.read_4(input)
        if packet_size == None:
            return None
        ber = input.read(packet_size)
        return bert.decode(ber)

    def write_berp(self, output, obj):
        data = bert.encode(obj)
        output.write(struct.pack("!L", len(data)))
        output.write(data)
        output.flush()

    def start(self, quiet_on_read_err=False):
        Ernie.log("Starting")
        # On windows nouse_stdio is ignored by Erlang at the port creation,
        # so we cannot use file descriptor 3 and 4 for communication.
        # We must use file descriptors 0 and 1.
        fdi, fdo = (0, 1) if os.name is 'nt' else (3, 4)
        input = os.fdopen(fdi)
        output = os.fdopen(fdo, "w")

        while(True):
            ipy = self.read_berp(input)
            if ipy == None:
                if not quiet_on_read_err:
                    print ('Could not read BERP length header. '
                           'Ernie server may have gone away. '
                           'Exiting now.')
                exit()

            if len(ipy) == 4 and ipy[0] == bert.Atom('call'):
                mod, fun, args = ipy[1:4]
                self.log("-> " + ipy.__str__())
                try:
                    res = self.dispatch(mod, fun, args)
                    opy = (bert.Atom('reply'), res)
                    self.log("<- " + opy.__str__())
                    try:
                        self.write_berp(output, opy)
                    except IOError as e:
                        if quiet_on_read_err:
                            # quiet on read error
                            exit()
                        else:
                            raise e
                except ServerError, e:
                    opy = (bert.Atom('error'), (bert.Atom('server'), 0, str(type(e)), str(e), ''))
                    self.log("<- " + opy.__str__())
                    try:
                        self.write_berp(output, opy)
                    except IOError as e:
                        if quiet_on_read_err:
                            # quiet on read error
                            exit()
                        else:
                            raise e
                except Exception, e:
                    opy = (bert.Atom('error'), (bert.Atom('user'), 0, str(type(e)), str(e), ''))
                    self.log("<- " + opy.__str__())
                    try:
                        self.write_berp(output, opy)
                    except IOError as e:
                        if quiet_on_read_err:
                            # quiet on read error
                            exit()
                        else:
                            raise e
            elif len(ipy) == 4 and ipy[0] == bert.Atom('cast'):
                mod, fun, args = ipy[1:4]
                self.log("-> " + ipy.__str__())
                try:
                    res = self.dispatch(mod, fun, args)
                except:
                    pass
                try:
                    self.write_berp(output, (bert.Atom('noreply')))
                except IOError as e:
                    if quiet_on_read_err:
                        # quiet on read error
                        exit()
                    else:
                        raise e
            else:
                self.log("-> " + ipy.__str__())
                opy = (bert.Atom('error'), (bert.Atom('server'), 0, "Invalid request: " + ipy.__str__()))
                self.log("<- " + opy.__str__())
                try:
                    self.write_berp(output, opy)
                except IOError as e:
                    if quiet_on_read_err:
                        # quiet on read error
                        exit()
                    else:
                        raise e

class ServerError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

class Mod:
    def __init__(self, name):
        self.name = name
        self.funs = {}

    def fun(self, name, func):
        self.funs[name] = func
