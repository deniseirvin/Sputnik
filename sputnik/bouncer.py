"""Sputnik Bouncer Implementation

This module provides the Sputnik Bouncer implementation. As the primary entry
point, the Bouncer is responsible for bootstrapping the entire program.
"""

import asyncio
import os
import redis
from client import Client
from datastore import Datastore
from network import Network
from server import HTTPServer

class Bouncer(object):
    """A singleton that manages connected devices.

    The Bouncer provides the base functionality needed to instantiate a new
    Client or Network. It also acts as a bridge between connected Clients and
    Networks by maintaining an authoritative record of each connected device.

    Attributes:
        clients (set of sputnik.Client): A set of connected Clients.
        datastore (sputnik.Datastore): A Redis interface.
        networks (dict of sputnik.Network): A dictionary of connected Networks.
    """

    def __init__(self):
        """Creates an instance of a Bouncer.

        Initializes an empty set and an empty dictionary for later use, then
        reloads previously connected networks from the Datastore.
        """

        self.clients = set()
        self.networks = dict()

        try: # Attempt a Datastore Connection

            self.datastore = Datastore(hostname="localhost", port="6379")
            self.datastore.database.ping()

        except redis.ConnectionError: # Continue Without Persistence

            self.datastore = None
            print("Failed to Connect to a Redis Instance.\n"
                  "Continuing Without Persistence.")

        if self.datastore:

            if not self.datastore.get_password():
                self.datastore.set_password()

            history = self.datastore.get_networks()
            for credentials in history.values():
                self.add_network(**credentials)

    def start(self, hostname="", port=6667):
        """Starts the IRC and HTTP listen servers.

        This creates the IRC server-portion of the Bouncer, allowing it to
        accept connections from IRC clients. It also starts the HTTP server,
        enabling browsers to connect to the web interface.

        Note:
            This is a blocking call.

        Args:
            hostname (str, optional): Hostname to use. Defaults to ``""``.
            port (int, optional): The port to listen on. Defaults to 6667.
        """

        hport = os.getenv("RUPPELLS_SOCKETS_LOCAL_PORT")
        if hport: port = int(hport)

        loop = asyncio.get_event_loop()
        coro = loop.create_server(lambda: Client(self), hostname, port)
        loop.run_until_complete(coro)
        HTTPServer(self).start()

        try: loop.run_forever()
        except KeyboardInterrupt: pass
        finally: loop.close()

    def add_network(self, network, hostname, port,
                    nickname, username, realname,
                    password=None, usermode=0):
        """Connects the Bouncer to an IRC network.

        This forms the credentials into a dictionary. It then registers the
        network in the datastore, and connects to the indicated IRC network.

        Args:
            network (str): The name of the IRC network to connect to.
            hostname (str): The hostname of the IRC network to connect to.
            port (int): The port to connect using.
            nickname (str): The IRC nickname to use when connecting.
            username (str): The IRC ident to use when connecting.
            realname (str): The real name of the user.
            password (str, optional): Bouncer password. Defaults to ``None``.
            usermode (int, optional): The IRC usermode. Defaults to ``0``.
        """

        credentials = { "network"  : network,
                        "nickname" : nickname,
                        "username" : username,
                        "realname" : realname,
                        "hostname" : hostname,
                        "port"     : port,
                        "password" : password }

        if self.datastore: self.datastore.add_network(**credentials)
        loop = asyncio.get_event_loop()
        coro = loop.create_connection(lambda: Network(self, **credentials),
                                      hostname, port)
        asyncio.async(coro)

    def remove_network(self, network):
        """Removes a network from the Bouncer.

        This disconnects the Bouncer from the indicated network and unregisters
        the network from the datastore.

        Args:
            network (str): the name of a network.
        """

        if network in self.networks:
            self.networks[network].connected = False
            self.networks[network].transport.close()
        if self.datastore: self.datastore.remove_network(network)
