#!/usr/bin/python
"""OmnikExport program.

Get data from a Wi-Fi kit logger and save/send the data to the defined plugin(s)
"""
import socket  # Needed for talking to logger
import sys
import logging
import logging.config
import ConfigParser
import optparse
import os
from PluginLoader import Plugin
import InverterMsg  # Import the Msg handler
import InverterLib  # Import the library

class OmnikExport(object):
    """
    Get data from the inverter(s) and store the data in a configured output
    format/location.

    """

    config = None
    logger = None

    def __init__(self, config_file):
        # Load the setting
        config_files = [InverterLib.expand_path('config-default.cfg'),
                        InverterLib.expand_path(config_file)]

        self.config = ConfigParser.RawConfigParser()
        self.config.read(config_files)

        # add command line option -p / --plugins to override the output plugins used
        parser = optparse.OptionParser()
        parser.add_option('-p', '--plugins',
                action="store", dest="plugins",
                help="output plugins to use")

        self.options, self.args = parser.parse_args()

    def run(self):
        """Get information from inverter and store is configured outputs."""

        self.build_logger(self.config)

        # Load output plugins
        # Prepare path for plugin loading
        sys.path.append(InverterLib.expand_path('outputs'))

        Plugin.config = self.config
        Plugin.logger = self.logger

        enabled_plugins = self.config.get('general', 'enabled_plugins')\
                                     .split(',')
        
        # if -p / --plugin option giving at command line, override enabled plugins
        if self.options.plugins:
            enabled_plugins = self.options.plugins.split(',')
        
        for plugin_name in enabled_plugins:
            plugin_name = plugin_name.strip()
            self.logger.debug('Importing output plugin ' + plugin_name)
            __import__(plugin_name)

        # Connect to logger
        ip = self.config.get('logger', 'ip')
        port = self.config.get('logger', 'port')
        timeout = self.config.getfloat('logger', 'timeout')

        for res in socket.getaddrinfo(ip, port, socket.AF_INET,
                                      socket.SOCK_STREAM):
            family, socktype, proto, canonname, sockadress = res
            try:
                self.logger.info('connecting to {0} port {1}'.format(ip, port))
                logger_socket = socket.socket(family, socktype, proto)
                logger_socket.settimeout(timeout)
                logger_socket.connect(sockadress)
            except socket.error as msg:
                self.logger.error('Could not open socket')
                self.logger.error(msg)
                sys.exit(1)

        wifi_serial = self.config.getint('logger', 'wifi_sn')
        data = InverterLib.generate_string(int(wifi_serial))
        logger_socket.sendall(data)

        #dump raw data to log
        self.logger.debug('RAW sent Packet (len={0}): '.format(len(data))+':'.join(x.encode('hex') for x in data))

        okflag = False
        while (not okflag):

            data = logger_socket.recv(1500)
    
            #dump raw data to log
            self.logger.debug('RAW received Packet (len={0}): '.format(len(data))+':'.join(x.encode('hex') for x in data))
    
            msg = InverterMsg.InverterMsg(data)
    
            if (msg.ok)[:9] == 'DATA SEND':
                self.logger.debug("Exit Status: {0}".format(msg.ok))
                logger_socket.close()
                okflag = True
                continue

            if (msg.ok)[:11] == 'NO INVERTER':
                self.logger.debug("Inverter(s) are in sleep mode: {0} received".format(msg.ok))
                logger_socket.close()
                okflag = True
                continue

            self.logger.info("Inverter ID: {0}".format(msg.id))
            self.logger.info("Inverter main firmware version: {0}".format(msg.main_fwver))
            self.logger.info("Inverter slave firmware version: {0}".format(msg.slave_fwver))
            self.logger.info("RUN State: {0}".format(msg.run_state))
    
            for plugin in Plugin.plugins:
                self.logger.debug('Run plugin' + plugin.__class__.__name__)
                plugin.process_message(msg)

    def build_logger(self, config):
        # Build logger
        """
        Build logger for this program


        Args:
            config: ConfigParser with settings from file
        """
        log_levels = dict(notset=0, debug=10, info=20, warning=30, error=40, critical=50)
        log_dict = {
            'version': 1,
            'formatters': {
                'f': {'format': '%(asctime)s %(levelname)s %(message)s'}
            },
            'handlers': {
                'none': {'class': 'logging.NullHandler'},
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'f'
                },
                'file': {
                    'class': 'logging.FileHandler',
                    'filename': InverterLib.expand_path(config.get('log',
                                                              'filename')),
                    'formatter': 'f'},
            },
            'loggers': {
                'OmnikLogger': {
                    'handlers': config.get('log', 'type').split(','),
                    'level': log_levels[config.get('log', 'level')]
                }
            }
        }
        logging.config.dictConfig(log_dict)
        self.logger = logging.getLogger('OmnikLogger')

    def override_config(self, section, option, value):
        """Override config settings"""
        self.config.set(section, option, value)

if __name__ == "__main__":
    omnik_exporter = OmnikExport('config.cfg')
    omnik_exporter.run()