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
from models import *
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from mako.template import Template
from sqlalchemy import func
from pwd import getpwnam
from spwd import getspnam
from grp import getgrnam

# TODO:
# - CHMOD 700 ON GENERATED FILES. 
#   ^^^ SERIOUSLY, DO IT
# - Create home directory if it does not exists
# - require domain to be verified
# - reload services
# - DNS
# - Postfix SQL queries on multiple lines.
# - Use templates for --make-* and emperor

options = {
    'db' : 'postgresql+psycopg2://tfhdev@localhost/tfhdev',
    'output-php' : './output/phpfpm/%s.conf',
    'output-emperor' : './output/emperor/',
    'output-nginx' : './output/nginx.conf',
    'output-dovecot' : './output/dovecot-sql.conf',
    'output-pam-pgsql' : './output/pam_pgsql.conf',
    'output-nss-pgsql' : './output/nss-pgsql.conf',
    'output-nss-pgsql-root' : './output/nss-pgsql-root.conf',
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
parser.add_argument('--db', action='store', dest='db',
    help='Set database info.')
parser.add_argument('--output-php', action='store',
    dest='output-php', help='Set PHP config file. %%s=user_vhost')
parser.add_argument('--output-emperor', action='store',
    dest='output-emperor', help='Set supervisor config file. %%s=user')
parser.add_argument('--output-nginx', action='store',
    dest='output-nginx', help='Set nginx config file.')
parser.add_argument('--output-dovecot', action='store',
    dest='output-dovecot', help='Set dovecot config file.')
parser.add_argument('--output-pam-pgsql', action='store',
    dest='output-pam-pgsql', help='Set pam_pgsql.conf location.')
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

if options['make-pam-pgsql']:
    print('Generating pam_pgsql.conf...')
    fh = open(options['output-pam-pgsql'], 'w')
    fh.write('connect = host=%s dbname=%s user=%s password=%s\n'%(
        dbe.url.host, dbe.url.database, dbe.url.username, dbe.url.password))
    fh.write('auth_query = select password from users where username = %u\n')
    fh.write('pwd_query = update users set password = %p where username = %u\n')
    fh.write('acct_query = select FALSE, FALSE, (password is NULL or password = '') from users where username = %u\n')
    fh.close();
    exit(0);
    
if options['make-nss-pgsql']:
    print('Generating nss-pgsql.conf...')
    fh = open(options['output-nss-pgsql'], 'w')
    fh.write('connectionstring = host=%s dbname=%s user=%s password=%s\n'%(
        dbe.url.host, dbe.url.database, dbe.url.username, dbe.url.password))
    fh.write('getpwnam = select username, \'x\' as passwd, \'\' as gecos, (\'/home/\' || username) as homedir, COALESCE(shell, \'/bin/bash\'), (id+1000) as uid, (groupid+1000) as gid from users where username = $1\n')
    fh.write('getpwuid = select username, \'x\' as passwd, \'\' as gecos, (\'/home/\' || username) as homedir, COALESCE(shell, \'/bin/bash\'), (id+1000) as uid, (groupid+1000) as gid from users where id = ($1 - 1000)\n')
    fh.write('getgroupmembersbygid = select username from users where groupid = $1\n')
    fh.write('getgrnam = select name as groupname, \'x\', (id+1000) as gid, ARRAY(SELECT username from users where groupid = groups.id) as members FROM groups WHERE name = $1\n')
    fh.write('getgrgid = select name as groupname, \'x\', (id+1000) as gid, ARRAY(SELECT username from users where groupid = groups.id) as members FROM groups WHERE id = $1-1000\n')
    fh.write('groups_dyn = select groupid from users where groupid = $1 AND groupid <> $2 \n') # wtf.
    fh.close();
    exit(0);

if options['make-nss-pgsql-root']:
    print('Generating nss-pgsql-root.conf...')
    fh = open(options['output-nss-pgsql-root'], 'w')
    fh.write('connectionstring = host=%s dbname=%s user=%s password=%s\n'%(
        dbe.url.host, dbe.url.database, dbe.url.username, dbe.url.password))
    fh.write('shadowbyname = select username as shadow_name, password as shadow_passwd, 15066 AS shadow_lstchg, 0 AS shadow_min, 99999 AS shadow_max, 7 AS shadow_warn, 7 AS shadow_inact, 99999 AS shadow_expire, 0 AS shadow_flag from users where username = $1 and password is not NULL and password != \'\'\n')
    fh.write('shadow = select username as shadow_name, password as shadow_passwd, 15066 AS shadow_lstchg, 0 AS shadow_min, 99999 AS shadow_max, 7 AS shadow_warn, 7 AS shadow_inact, 99999 AS shadow_expire, 0 AS shadow_flag from users where password is not NULL and password != \'\'\n')
    fh.close();
    exit(0);

if options['make-dovecot']:
    print('Generating dovecot scripts...')
    vmailuid = getpwnam('vmail').pw_uid
    vmailgid = getgrnam('vmail').gr_gid
    fh = open(options['output-dovecot'], 'w')
    fh.write('driver = pgsql\n')
    fh.write('connect = host=%s dbname=%s user=%s password=%s\n'%(
        dbe.url.host, dbe.url.database, dbe.url.username, dbe.url.password))
    fh.write('default_pass_scheme = SHA512-CRYPT\n')
    fh.write("password_query = SELECT '%u' as user, password FROM mailboxes LEFT JOIN domains ON domains.id = mailboxes.domainid WHERE local_part='%n' AND domain='%d'\n")
    fh.write('\n')
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
        filename = options['output-emperor']+vhost.user.username+'_'+vhost.name+'.ini'
        logging.debug('-> uwsgi app: '+filename)
        appsocket = '/var/lib/uwsgi/app_%s_%s.sock' %(vhost.user.username, vhost.name)
        fh = open(filename, 'w')
        fh.write('[uwsgi]\n')
        fh.write('master = true\n')
        fh.write('processes = 1\n')
        fh.write('socket = %s\n'%appsocket)
        fh.write('wsgi-file = %s/wsgi.py\n' % vhost.applocation)
        fh.write('chown-socket = %s:www-data\n' % vhost.user.username)
        fh.write('chmod-socket = 660\n')
        fh.write('uid = %s\n' % vhost.user.username)
        fh.write('gid = %s\n' % vhost.user.username)
        fh.write('env = PYTHONUSERBASE=/home/%s/.local/\n' % vhost.user.username)
        fh.write('logto2 = /home/%s/logs/%s_app.log\n' % (vhost.user.username, vhost.name))
        fh.write('logfile-chown = %s\n' % vhost.user.username)
        fh.write('plugins = python32\n')
        fh.write('chdir = %s\n' % vhost.applocation)
        fh.write('cheap = true\n')
#        fh.write('threads = 2')
        fh.write('idle = 64\n')
        fh.write('harakiri = 60\n')
        fh.write('limit-as = 256\n')
        fh.write('max-requests = 100\n')
        fh.write('vacuum = true\n')
        fh.write('enable-threads = true\n')
        fh.write('\n')
        fh.close()

    for d in vhost.domains:
        logging.debug('-> domain: %s'%d.domain)
    fhNginx.write(tplNginx.render(
        listen_addr = (server.ipv4, server.ipv6),
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

server.lastupdate = datetime.datetime.now()
dbs.commit()

