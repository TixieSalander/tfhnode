#!/usr/bin/env python3
"""
Generate configuration files and SQL tables.
"""

from argparse import ArgumentParser
from configparser import ConfigParser
import logging
import os
from models import *
from sqlalchemy import *
from mako.template import Template

options = {
    'db' : 'postgresql+psycopg2://tfhdev@localhost/tfhdev',
    'password-scheme' : 'SHA512-CRYPT',
}

generators = (
    # name              output path             generator
    ('tables',          None,                   'gen_tables'),
    ('dovecot',         'dovecot-sql.conf',     'gen_dovecot'),
    ('postfix',         'postfix/',             'gen_postfix'),
    ('pam-pgsql',       'pam_pgsql.conf',       'gen_pam_pgsql'),
    ('nss-pgsql',       'nss-pgsql.conf',       'gen_nss_pgsql'),
    ('nss-pgsql-root',  'nss-pgsql-root.conf',  'gen_nss_pgsql_root'),
)

config = ConfigParser()
config.read('./tfhnode.ini')
if 'node' in config:
    for d in config.items('node'):
        options[d[0]] = d[1]

parser = ArgumentParser(description=__doc__)
parser.set_defaults(**options)
parser.add_argument('-v', '--verbose', action='store_true',
    default=None, dest='verbose', help='Increase verbosity')
parser.add_argument('--make-all', action='store_true',
    dest='make-all', help='Generate everything')

for generator in generators:
    name, filename, function = generator
    if filename:
        make_help = 'Generate %s (%s)'%(filename, name)
    else:
        make_help = 'Generate '+name
    parser.add_argument('--make-'+name,
        action='store_true',
        dest='make-'+name,
        help=make_help)
    if filename:
        parser.add_argument('--output-'+name,
            action='store',
            dest='output-'+name,
            default='./output/'+filename,
            help=name+' output path')
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

dbe = create_engine(options['db'])

def gen_tables():
    Base.metadata.create_all(dbe)

def gen_dovecot(output):
    tpl = Template(filename='./templates/dovecot-sql.conf')
    fh = open(output, 'w')
    fh.write(tpl.render(
        host=dbe.url.host, db=dbe.url.database,
        user=dbe.url.username, password=dbe.url.password,
        passwdscheme=options['password-scheme'],
    ))
    fh.close()
    os.chmod(output, 0o600)

def gen_postfix(output):
    header = 'hosts = %s\nuser = %s\npassword = %s\ndbname = %s\n'%(
        dbe.url.host, dbe.url.username, dbe.url.password or '', dbe.url.database)
    files = {
        'domains' : "SELECT '%s' AS output FROM mailboxes LEFT JOIN domains ON domains.id = mailboxes.domainid WHERE domain='%s' LIMIT 1;",
        'boxes' : "SELECT '%d/%u' FROM mailboxes LEFT JOIN domains ON domains.id = mailboxes.domainid WHERE local_part='%u' AND domain='%d' AND redirect IS NULL",
        'aliases' : "SELECT redirect FROM mailboxes LEFT JOIN domains ON domains.id = mailboxes.domainid WHERE (local_part='%u' AND domain='%d' AND redirect IS NOT NULL) OR (local_part IS NULL AND domain='%d' AND redirect IS NOT NULL AND (SELECT COUNT(*) FROM mailboxes LEFT JOIN domains ON domains.id = mailboxes.domainid WHERE local_part='%u' AND domain='%d') = 0)",
    }
    if not os.path.isdir(output):
        os.makedirs(output)
    for f in files.keys():
        filename = '%s/%s.cf' % (output, f)
        fh=open(filename, 'w')
        fh.write(header)
        fh.write('query = '+files[f]+'\n')
        fh.close()
        os.chmod(filename, 0o600)


def gen_pam_pgsql(output):
    tpl = Template(filename='./templates/pam_pgsql.conf')
    fh = open(output, 'w')
    fh.write(tpl.render(
        host=dbe.url.host, db=dbe.url.database,
        user=dbe.url.username, password=dbe.url.password,
    ))
    fh.close()
    os.chmod(output, 0o600)
    
def gen_nss_pgsql(output):
    tpl = Template(filename='./templates/nss-pgsql.conf')
    fh = open(output, 'w')
    fh.write(tpl.render(
        host=dbe.url.host, db=dbe.url.database,
        user='tfh_node_passwd', password='passwdfile',
    ))
    # passwd db need to be readable by every user.
    # tfh_node_passwd should only be able to read needed columns on that table
    fh.close()
    os.chmod(output, 0o644)

def gen_nss_pgsql_root(output):
    tpl = Template(filename='./templates/nss-pgsql-root.conf')
    fh = open(output, 'w')
    fh.write(tpl.render(
        host=dbe.url.host, db=dbe.url.database,
        user=dbe.url.username, password=dbe.url.password,
    ))
    fh.close()
    os.chmod(output, 0o600)

make_all = 'make-all' in options and options['make-all']
made_something = False

for generator in generators:
    name, filename, function = generator
    if not function in locals():
        logging.error(name+': Generator do not exists.')
        exit(1)
    make_that = 'make-'+name in options and options['make-'+name]
    if make_all or make_that:
        made_something = True
        if 'output-'+name in options:
            output = options['output-'+name]
            locals()[function](output)
            logging.info('generated: '+output)
        else:
            locals()[function]()
            logging.info('generated: '+name)

if not made_something:
    parser.print_help()


