from sqlalchemy import *
from sqlalchemy.orm import relationship, backref
import datetime
from sqlalchemy.ext.declarative import declarative_base
import logging
import sys
import os
import socket
from mako.template import Template

Base = declarative_base()
metadata = MetaData()

class Users(Base):
    __tablename__ = 'users'
    id       = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True, nullable=False)
    password = Column(String(128))
    email    = Column(String(512))
    groupid  = Column(ForeignKey('groups.id'), nullable=False, default=0)
    signup_date = Column(DateTime, default=datetime.datetime.now, nullable=False)
    vhosts   = relationship('VHosts', backref='user')
    logins   = relationship('LoginHistory', backref='user')
    domains  = relationship('Domains', backref='user')
    mailboxes= relationship('Mailboxes', backref='user')

class Groups(Base):
    __tablename__ = 'groups'
    id       = Column(Integer, primary_key=True)
    name     = Column(String(64), nullable=False)
    description = Column(String(256))
    perms    = Column(BigInteger, default=0, nullable=False)
    appperms = Column(BigInteger, default=0, nullable=False)
    users    = relationship('Users', backref='group')

class LoginHistory(Base):
    __tablename__ = 'login_history'
    id       = Column(Integer, primary_key=True)
    userid   = Column(ForeignKey('users.id'), nullable=False)
    time     = Column(DateTime, default=datetime.datetime.now, nullable=False)
    remote   = Column(String(64))
    useragent= Column(String(64))

class Servers(Base):
    __tablename__ = 'servers'
    id       = Column(Integer, primary_key=True)
    name     = Column(String(32), unique=True, nullable=False)
    fqdn     = Column(String(256), unique=True, nullable=False)
    ipv4     = Column(String(32))
    ipv6     = Column(String(64))
    opened   = Column(Boolean, nullable=False)
    lastupdate = Column(DateTime, nullable=False, default=datetime.datetime.fromtimestamp(1))
    vhosts   = relationship('VHosts', backref='server')

class Domains(Base):
    __tablename__ = 'domains'
    id       = Column(Integer, primary_key=True)
    userid   = Column(ForeignKey('users.id'), nullable=False)
    domain   = Column(String(256), nullable=False)
    hostedns = Column(Boolean, nullable=False)
    vhostid  = Column(ForeignKey('vhosts.id'))
    public   = Column(Boolean, default=False, nullable=False)
    verified = Column(Boolean, nullable=False, default=False)
    verif_token = Column(String(64))
    entries  = relationship('DomainEntries', backref='domain')
    mailboxes= relationship('Mailboxes', backref='domain')

class DomainEntries(Base):
    __tablename__ = 'domainentries'
    id       = Column(Integer, primary_key=True)
    domainid = Column(ForeignKey('domains.id'), nullable=False)
    sub      = Column(String(256))
    rdatatype= Column(Integer, nullable=False)
    rdata    = Column(Text, nullable=False)


class Mailboxes(Base):
    __tablename__ = 'mailboxes'
    id       = Column(Integer, primary_key=True)
    userid   = Column(ForeignKey('users.id'), nullable=False)
    domainid = Column(ForeignKey('domains.id'), nullable=False)
    local_part = Column(String(64), nullable=True)
    password = Column(String(128))
    redirect = Column(String(512))

class VHosts(Base):
    __tablename__ = 'vhosts'
    
    appTypes = {
        0x00 : 'None',
        0x01 : 'Custom HTTP',
        0x02 : 'Custom FCGI',
        0x04 : 'Custom WSGI',
        0x10 : 'PHP',
        0x20 : 'Python',
        0x40 : 'Node.js',
        0x80 : 'Perl',
    }
    
    id       = Column(Integer, primary_key=True)
    name     = Column(String(32), nullable=False)
    path     = Column(String(256), nullable=True)
    userid   = Column(ForeignKey('users.id'), nullable=False)
    serverid = Column(ForeignKey('servers.id'), nullable=False)
    update   = Column(DateTime, onupdate=datetime.datetime.now)
    catchall = Column(String(256))
    autoindex= Column(Boolean, nullable=False, default=False)
    apptype  = Column(BigInteger, nullable=False, default=0)
    applocation = Column(String(512))
    domains  = relationship('Domains', backref='vhost')
    rewrites = relationship('VHostRewrites', backref='vhost')
    acls     = relationship('VHostACLs', backref='vhost')
    errorpages=relationship('VHostErrorPages', backref='vhost')

class VHostRewrites(Base):
    __tablename__ = 'vhostrewrites'
    id       = Column(Integer, primary_key=True)
    vhostid  = Column(ForeignKey('vhosts.id'), nullable=False)
    regexp   = Column(String(256), nullable=False)
    dest     = Column(String(256), nullable=False)
    redirect_temp = Column(Boolean, nullable=False, default=False)
    redirect_perm = Column(Boolean, nullable=False, default=False)
    last     = Column(Boolean, nullable=False, default=False)

class VHostACLs(Base):
    __tablename__ = 'vhostacls'
    id       = Column(Integer, primary_key=True)
    title    = Column(String(256), nullable=False)
    vhostid  = Column(ForeignKey('vhosts.id'), nullable=False)
    regexp   = Column(String(256), nullable=False)
    passwd   = Column(String(256), nullable=False)

class VHostErrorPages(Base):
    __tablename__ = 'vhosterrorpages'
    id       = Column(Integer, primary_key=True)
    vhostid  = Column(ForeignKey('vhosts.id'), nullable=False)
    code     = Column(Integer, nullable=False)
    path     = Column(String(256), nullable=False)


class Service(object):
    def clear(self):
        if hasattr(self, 'output_dir'):
            for f in os.listdir(self.output_dir):
                if f.endswith(self.output_ext):
                    os.remove(self.output_dir+'/'+f)
        elif hasattr(self, 'output_file'):
            if os.path.isfile(self.output_file):
                os.remove(self.output_file)
            
    def reload(self):
        if hasattr(self, 'pidfile'):
            if hasattr(self, 'reload_signal'):
                signal = self.reload_signal
            else:
                signal = 'SIGHUP'
        try:
            pid = int(open(pidfile).read())
            r = subprocess.call(['kill', '-'+signal, str(pid)])
            if r != 0:
                logging.error('Failed to sent %s to %s!', signal, process)
        except FileNotFoundError:
            logging.warning('Pidfile not found for '+process)
    
    def generate_vhost(self, vhost):
        raise NotImplementedError()
        

class NginxService(Service):
    def __init__(self, output, pidfile):
        self.output_dir = output
        self.output_ext = '.conf'
        self.pidfile = pidfile
        self.template = Template(filename='./templates/nginx.conf')

    def generate_vhost(self, vhost):
        filename = self.output_dir + '%s_%s.conf'%(
            vhost.user.username, vhost.name)
        fh = open(filename, 'w')
        if len(vhost.domains) < 1:
            logging.warning('vhost#%d/nginx: no domain associated.'%(vhost.id))
            return
            
        if not vhost.path:
            # Before vhost.path...
            # TODO: Remove backward compatibility stuff and upgrade server
            # TODO: vhost.path is not used. Is it useless?
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
                    logging.warning('vhost#%d/nginx: invalid path.')
                    return
                if not os.path.isdir(pubdir):
                    logging.warning('vhost#%d/nginx: path does not exists.')
                    return
                if getpwuid(stat(pubdir).st_uid).pw_name != vhost.user.username:
                    logging.warning('vhost#%d/nginx: path does not belong to user.')
                    return
        
        appsocket = None
        if vhost.apptype == 0x20: # uwsgi
            # TODO: Do that in templates, as for PHP
            appsocket = '/var/lib/uwsgi/app_%s_%s.sock'%(
                vhost.user.username, vhost.name)

        for d in vhost.domains:
            logging.debug('-> domain: %s'%d.domain)
        
        addresses = ['127.0.0.1', '::1']
        if server.ipv4:
            addresses.append(server.ipv4)
        if server.ipv6:
            addresses.append(server.ipv6)
        
        fh.write(self.template.render(
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
        fh.close()
    
class UwsgiService(Service):
    def __init__(self, output):
        self.output_dir = output
        self.output_ext = '.ini'
        self.template = Template(filename='./templates/uwsgi.ini')

    def generate_vhost(self, vhost):
        # FIXME: Make check on vhost.applocation
        filename = self.output_dir + '/%s_%s.ini'%(
            vhost.user.username, vhost.name)
        fh = open(filename, 'w')
        fh.write(self.template.render(vhost=vhost, user=vhost.user))
        fh.close()

    def remove_vhost(self, vhost):
        filename = self.output_dir + '/%s_%s.ini'%(
            vhost.user.username, vhost.name)
        if os.path.isfile(filename):
            os.remove(filename)
        
class PhpfpmService(Service):
    def __init__(self, output, pidfile):
        self.output_dir = output
        self.output_ext = '.conf'
        self.pidfile = pidfile
        self.template = Template(filename='./templates/phpfpm.conf')

    def generate_vhost(self, vhost):
        filename = self.output_dir + '%s.conf'%(vhost.user.username)
        # Never need to be changed, only created/deleted
        if not os.path.isfile(filename):
            return
        fh = open(filename, 'w')
        fh.write(tplPhp.render(user=user.username))
        fh.close()

    def remove_vhost(self, vhost):
        filename = self.output_dir + '%s.conf'%(vhost.user.username)
        if os.path.isfile(filename):
            os.remove(filename)


