#!/usr/bin/env python3
"""
Tux-FreeHost Node: Generate config for the current server.

It tries to read a ./tfhnode.ini:
[node]
db = postgresql+psycopg2://tfhdev@localhost/tfhdev
output-php = ./output/phpfpm/%s.conf
output-nginx = ./output/nginx.conf
"""

from argparse import ArgumentParser, ArgumentError, RawDescriptionHelpFormatter
from configparser import ConfigParser
import logging
import sys
import datetime
import os
import socket
import subprocess
from models import *
from services import *
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from mako.template import Template
from sqlalchemy import func
import psycopg2

options = {
    'db' : 'postgresql+psycopg2://tfhdev@localhost/tfhdev',
    'output-php' : './output/phpfpm/',
    'output-emperor' : './output/emperor/',
    'output-nginx' : './output/nginx/',
    'hostname' : None,
    'ssl-port' : '444',
    'gen-all' : True,
    'make-http-dirs' : True,
    'reload-services' : True,
}

def main():
    config = ConfigParser()
    config.read('./tfhnode.ini')
    if 'node' in config:
        for d in config.items('node'):
            options[d[0]] = d[1]

    parser = ArgumentParser(description=__doc__)
    parser.set_defaults(**options)
    parser.add_argument('-v', '--verbose', action='count',
        default=None, dest='verbose', help='Increase verbosity')

    for option in options:
        try:
            if isinstance(options[option], bool):
                parser.add_argument('--'+option, action='store_true', dest=option)
                parser.add_argument('--no-'+option, action='store_false',
                    dest=option)
            else:
                parser.add_argument('--'+option, action='store', dest=option)
        except ArgumentError:
            pass

    cli_options = vars(parser.parse_args())
    for o in cli_options:
        options[o] = cli_options[o]

    log_level = logging.WARNING
    if options['verbose'] != None:
        verbose = int(options['verbose'])
        if verbose == 1:
            log_level = logging.INFO
        elif verbose >= 2:
            log_level = logging.DEBUG
    logging.basicConfig(level=log_level)
    
    directories = (
        options['output-nginx'],
        options['output-emperor'],
        options['output-php'],
    )
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)

    dbe = create_engine(options['db'])
    dbc = dbe.connect()
    pg_conn = dbc.connection
    pg_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    dbs = sessionmaker(bind=dbe)()

    server = get_server(dbs, options)

    nginx_service = NginxService(options['output-nginx'], '/run/nginx.pid',
        server=server, options=options)
    uwsgi_service = UwsgiService(options['output-emperor'])
    phpfpm_service = PhpfpmService(options['output-php'], '/run/php5-fpm.pid')

    appservices = {
        0x10 : phpfpm_service,
        0x20 : uwsgi_service,
    }

    vhosts = dbs.query(VHosts).filter_by(server=server).all()
    nginx_service.clear()
    uwsgi_service.clear()
    phpfpm_service.clear()
    for vhost in vhosts:
        nginx_service.generate_vhost(vhost)
        gen_vhost_app(vhost, appservices)

    if options['reload-services']:
        reload_services((nginx_service, uwsgi_service, phpfpm_service))

    server.lastupdate = datetime.datetime.now()
    dbs.commit()
    
def get_server(dbs, options):
    hostname = options['hostname'] or socket.gethostname()
    logging.info('server: hostname is %s'%(hostname))

    server = dbs.query(Servers).filter_by(fqdn=hostname).first()
    if not server:
        logging.critical('server: Cannot find server id in database.')
        exit(1)

    logging.info('server: #%d Last run: %s'%(server.id, server.lastupdate))
    return server

def gen_vhost_app(vhost, services):
    for apptype, service in services.items():
        if vhost.apptype & apptype:
            service.generate_vhost(vhost)
        else:
            service.remove_vhost(vhost)

def reload_services(services):
    for service in services:
        service.reload()

if __name__ == '__main__':
    main()

