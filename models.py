from sqlalchemy import *
from sqlalchemy.orm import relationship, backref
import datetime
from sqlalchemy.ext.declarative import declarative_base

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


