#!/usr/bin/env python3
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
import subprocess
from models import *
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from mako.template import Template
from sqlalchemy import func
from pwd import getpwnam
from grp import getgrnam, getgrgid

# TODO:
# - CHMOD 700 ON GENERATED FILES. 
#   ^^^ SERIOUSLY, DO IT
# - require domain to be verified
# - DNS
# - Postfix SQL queries on multiple lines.
# - Use templates for --make-* and emperor
# - move postfix/ to output/, use output-postfix
# - chown -R /home/<user> when created

options = {
    'db' : 'postgresql+psycopg2://tfhdev@localhost/tfhdev',
    'output-php' : './output/phpfpm/%s.conf',
    'output-emperor' : './output/emperor/',
    'output-nginx' : './output/nginx.conf',
    'output-dovecot' : './output/dovecot-sql.conf',
    'output-pam-pgsql' : './output/pam_pgsql.conf',
    'output-nss-pgsql' : './output/nss-pgsql.conf',
    'output-nss-pgsql-root' : './output/nss-pgsql-root.conf',
    'password-scheme' : 'SHA512-CRYPT',
}

parser = ArgumentParser(description=__doc__,
    formatter_class=RawDescriptionHelpFormatter)
parser.add_argument('--create-tables', action='store_true',
    dest='create-tables', help='Create tables and exit.')
parser.add_argument('--make-postfix', action='store_true',
    dest='make-postfix', help='Generate postfix scripts and exit.')
parser.add_argument('--make-dovecot', action='store_true',
    dest='make-dovecot', help='Generate dovecot scripts and exit.')
parser.add_argument('--make-pam-pgsql', action='store_true',
    dest='make-pam-pgsql', help='Generate pam_pgsql.conf and exit.')
parser.add_argument('--make-nss-pgsql', action='store_true',
    dest='make-nss-pgsql', help='Generate nss_pgsql.conf and exit.')
parser.add_argument('--make-nss-pgsql-root', action='store_true',
    dest='make-nss-pgsql-root', help='Generate nss_pgsql-root.conf and exit.')
parser.add_argument('-v', '--verbose', action='store_true',
    default=None, dest='verbose', help='Increase verbosity')

for option in options:
    parser.add_argument('--'+option, action='store', dest=option)


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

if options['make-pam-pgsql']:
    print('Generating pam_pgsql.conf...')
    tpl = Template(filename='./templates/pam_pgsql.conf')
    fh = open(options['output-pam-pgsql'], 'w')
    fh.write(tpl.render(
        host=dbe.url.host, db=dbe.url.database,
        user=dbe.url.username, password=dbe.url.password,
    ))
    fh.close()
    exit(0);
    
if options['make-nss-pgsql']:
    print('Generating nss-pgsql.conf...')
    tpl = Template(filename='./templates/nss-pgsql.conf')
    fh = open(options['output-nss-pgsql'], 'w')
    fh.write(tpl.render(
        host=dbe.url.host, db=dbe.url.database,
        user='tfh_node_passwd', password='passwdfile',
    ))
    # passwd db need to be readable by every user.
    # tfh_node_passwd should only be able to read needed columns on that table
    fh.close()
    exit(0);

if options['make-nss-pgsql-root']:
    print('Generating nss-pgsql-root.conf...')
    tpl = Template(filename='./templates/nss-pgsql-root.conf')
    fh = open(options['output-nss-pgsql-root'], 'w')
    fh.write(tpl.render(
        host=dbe.url.host, db=dbe.url.database,
        user=dbe.url.username, password=dbe.url.password,
    ))
    fh.close()
    exit(0);

if options['make-dovecot']:
    print('Generating dovecot-sql.conf...')
    tpl = Template(filename='./templates/dovecot-sql.conf')
    fh = open(options['output-dovecot'], 'w')
    fh.write(tpl.render(
        host=dbe.url.host, db=dbe.url.database,
        user=dbe.url.username, password=dbe.url.password,
        passwdscheme=options['password-scheme'],
    ))
    fh.close()
    exit(0);

dbs = sessionmaker(bind=dbe)()

if 'hostname' in options and options['hostname']:
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
    home = '/home/%s'%(user.username)
    if not os.path.isdir(home):
        os.makedirs(home)
        os.system('chown %s:%s -R /home/%s/'%(
            user.username,user.username,user.username))
    if not os.path.isdir(home+'/logs'):
        os.makedirs(home+'/logs')
        os.system('chown %s:%s -R /home/%s/logs/'%(
            user.username,user.username,user.username))
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
    
    if not vhost.path:
        # Before vhost.path...
        pubdir = '/home/%s/http_%s/' % (vhost.user.username, vhost.name)
        legacydir = '/home/%s/public_http/' % (vhost.user.username)
        if not os.path.isdir(pubdir):
            if os.path.isdir(legacydir):
                pubdir = legacydir
            else:
                os.makedirs(pubdir)
                os.system('chown %s:%s -R %s'%(
                    user.username, user.username, pubdir))
    else:
        pubdir = os.path.abspath(vhost.path)
        if not pubdir.startswith('/home/'+vhost.user.username+'/'):
            # Should not be out of user's /home
            logging.warning('vhost#%d: invalid path.')
            continue
        if not os.path.isdir(pubdir):
            logging.warning('vhost#%d: path does not exists.')
            continue
        if getpwuid(stat(pubdir).st_uid).pw_name != vhost.user.username:
            logging.warning('vhost#%d: path does not belong to user.')
            continue

    appsocket = None

    if vhost.apptype == 0x20: # uwsgi apps
        # FIXME: Make check on vhost.applocation
        tpl = Template(filename='./templates/uwsgi.conf')
        filename = options['output-emperor']+vhost.user.username+'_'+vhost.name+'.ini'
        logging.debug('-> uwsgi app: '+filename)
        appsocket = '/var/lib/uwsgi/app_%s_%s.sock' %(vhost.user.username, vhost.name)
        fh = open(filename, 'w')
        fh.write(tpl.render(
            vhost=vhost, user=vhost.user,
        ))
        fh.close()

    for d in vhost.domains:
        logging.debug('-> domain: %s'%d.domain)
    addresses = ['127.0.0.1', server.ipv4]
    if server.ipv6:
        addresses.append(server.ipv6)
    fhNginx.write(tplNginx.render(
        listen_addr = addresses,
        user = vhost.user.username,
        name = vhost.name,
        pubdir = pubdir,
        hostnames = ' '.join([d.domain for d in vhost.domains]),
        autoindex = vhost.autoindex,
        catchall = vhost.catchall,
        rewrites = vhost.rewrites,
        error_pages = vhost.errorpages,
        acl = vhost.acls,
        apptype = vhost.apptype,
        appsocket = appsocket,
        applocation = vhost.applocation,
    ))
fhNginx.close()

signals = {
    # (process, signal, pidfile)
    ('php5-fpm', 'SIGUSR2', '/run/php5-fpm.pid'),
    ('nginx', 'SIGHUP', '/run/nginx.pid'),
}
for process, signal, pidfile in signals:
    try:
        pid = int(open(pidfile).read())
        r = subprocess.call(['kill', '-'+signal, str(pid)])
        if r != 0:
            logging.error('Failed to sent %s to %s!', signal, process)
    except FileNotFoundError:
        logging.warning('Pidfile not found for '+process)
        continue

server.lastupdate = datetime.datetime.now()
dbs.commit()

