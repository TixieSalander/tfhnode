#!/usr/bin/python
"""
Tux-FreeHost Node: Generate config for the current server.

It tries to read a ./tfhnode.ini:
[node]
db = postgresql+psycopg2://tfhdev@localhost/tfhdev
output-php = ./output/phpfpm/%s.conf
output-nginx = ./output/nginx.conf
"""

from argparse import ArgumentParser, RawDescriptionHelpFormatter
from configparser import ConfigParser
import logging
import sys
import datetime
import os
import socket
from models import *
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from mako.template import Template
from sqlalchemy import func

# TODO:
# - Add user if it does not exists
# - Create home directory if it does not exists
# - require domain to be verified
# - reload nginx
# - DNS
# - Postfix SQL queries on multiple lines.

options = {
    'db' : 'postgresql+psycopg2://tfhdev@localhost/tfhdev',
    'output-php' : './output/phpfpm/%s.conf',
    'output-nginx' : './output/nginx.conf',
}

parser = ArgumentParser(description=__doc__,
    formatter_class=RawDescriptionHelpFormatter)
parser.add_argument('--create-tables', action='store_true',
    dest='create-tables', help='Create tables and exit.')
parser.add_argument('--make-postfix', action='store_true',
    dest='make-postfix', help='Generate postfix scripts and exit.')
parser.add_argument('-v', '--verbose', action='count',
    default=None, dest='verbose', help='Increase verbosity')
parser.add_argument('--db', action='store', dest='db',
    help='Set database info.')
parser.add_argument('--output-php', action='store',
    dest='output-php', help='Set PHP config file. %%s=user')
parser.add_argument('--output-nginx', action='store',
    dest='output-nginx', help='Set nginx config file.')
parser.add_argument('--hostname', action='store',
    dest='hostname', help='Set hostname. Use system\'s if omitted.')

cli_options = vars(parser.parse_args())
config = ConfigParser()
config.read('./tfhnode.ini')
if 'node' in config:
    for d in config.items('node'):
        options[d[0]] = d[1]
else:
    options = dict()
for key in dict(cli_options).keys():
    if cli_options[key] is not None:
        options[key] = cli_options[key]

log_level = logging.WARNING
if options['verbose'] != None:
    verbose = int(options['verbose'])
    if verbose == 1:
        log_level = logging.INFO
    elif verbose >= 2:
        log_level = logging.DEBUG
logging.basicConfig(level=log_level)

dbe = create_engine(options['db'])

if options['create-tables']:
    print('Creating tables...', end='')
    Base.metadata.create_all(dbe)
    print('DONE.')
    exit(0)

if options['make-postfix']:
    print('Generating postfix scripts...')
    header = 'hosts = %s\nuser = %s\npassword = %s\ndbname = %s\n'%(
        dbe.url.host, dbe.url.username, dbe.url.password, dbe.url.database)
    files = {
        'domains' : "SELECT '%s' AS output FROM mailboxes LEFT JOIN domains ON domains.id = mailboxes.domainid WHERE domain='%s' LIMIT 1;",
        'boxes' : "SELECT '%d/%u' FROM mailboxes LEFT JOIN domains ON domains.id = mailboxes.domainid WHERE local_part='%u' AND domain='%d' AND redirect IS NULL",
        'aliases' : "SELECT redirect FROM mailboxes LEFT JOIN domains ON domains.id = mailboxes.domainid WHERE (local_part='%u' AND domain='%d' AND redirect IS NOT NULL) OR (local_part IS NULL AND domain='%d' AND redirect IS NOT NULL AND (SELECT COUNT(*) FROM mailboxes LEFT JOIN domains ON domains.id = mailboxes.domainid WHERE local_part='%u' AND domain='%d') = 0)",
    }
    if not os.path.isdir('./postfix'):
        os.makedirs('./postfix')
    for f in files.keys():
        fh=open('./postfix/'+f+'.cf', 'w')
        fh.write(header)
        fh.write('query = '+files[f]+'\n')
        fh.close()
    exit(0)

dbs = sessionmaker(bind=dbe)()

if 'hostname' in options:
    hostname = options[hostname]
else:
    hostname = socket.gethostname()

logging.info('Server: hostname is %s'%(hostname))

server = dbs.query(Servers).filter_by(fqdn=hostname).first()
if not server:
    logging.critical('Cannot find server id.')
    exit(1)
logging.info('Server: #%d Last run: %s'%(server.id, server.lastupdate))

tplNginx = Template(filename='./templates/nginx.conf')
tplPhp = Template(filename='./templates/phpfpm.conf')
tplBind = Template(filename='./templates/bind.conf')


subq = dbs.query(func.count(VHosts.id).label('vhcount')) \
.filter(and_(VHosts.userid==Users.id, VHosts.server==server)) \
.subquery()
users = dbs.query(Users).filter(subq.as_scalar()>=1).all()

for user in users:
    logging.info('Processing user #%d <%s>'%(user.id, user.username))
    fh = open(options['output-php']%(user.username), 'w')
    fh.write(tplPhp.render(
        user = user.username,
    ))
    fh.close()

fhNginx = open(options['output-nginx'], 'w')
vhosts = dbs.query(VHosts).filter_by(server=server).all()
for vhost in vhosts:
    logging.info('Processing vhost #%d <%s>'%(vhost.id, vhost.name))
    if len(vhost.domains) < 1:
        logging.warning('vhost#%d: no domain.'%(vhost.id))
        continue
    for d in vhost.domains:
        logging.debug('-> domain: %s'%d.domain)
    fhNginx.write(tplNginx.render(
        listen_addr = ('127.0.0.1', '::1'),
        user = vhost.user.username,
        name = vhost.name,
        hostnames = ' '.join([d.domain for d in vhost.domains]),
        autoindex = vhost.autoindex,
        catchall = vhost.catchall,
        rewrites = vhost.rewrites,
        error_pages = vhost.errorpages,
        acl = vhost.acls
    ))
fhNginx.close()



server.lastupdate = datetime.datetime.now()
dbs.commit()

