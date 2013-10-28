from sqlalchemy import *
from sqlalchemy.orm import relationship, backref, sessionmaker, scoped_session
import datetime
from sqlalchemy.ext.declarative import declarative_base
import inspect
import re
import crypt

class MyBase(object):
    natural_key = 'none'

    def get_natural_key(self):
        if hasattr(self, self.natural_key):
            return getattr(self, self.natural_key)
        # Without natural key, we use ID, still better than None
        return '#'+str(self.id)

    @property
    def display_name(self):
        return re.sub("([a-z])([A-Z])","\g<1> \g<2>", self.__class__.__name__)
    
    @property
    def short_name(self):
        return self.__class__.__name__.lower()

    def __str__(self):
        return self.get_natural_key()

DBSession = scoped_session(sessionmaker())
Base = declarative_base(cls=MyBase)
metadata = MetaData()

class User(Base):
    __tablename__ = 'users'
    id       = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True, nullable=False)
    password = Column(String(128))
    email    = Column(String(512))
    signup_date = Column(DateTime, default=datetime.datetime.now, nullable=False)
    
    vhosts   = relationship('VHost', backref='user')
    logins   = relationship('LoginHistory', backref='user')
    domains  = relationship('Domain', backref='user')
    mailboxes= relationship('Mailbox', backref='user')

    natural_key = 'username'
    
    def check_password(self, cleartext):
        return self.password == crypt.crypt(cleartext, self.password)

    def set_password(self, cleartext):
        self.password = crypt.crypt(cleartext)

usergroup_association = Table('usergroups', Base.metadata,
    Column('userid', Integer, ForeignKey('users.id')),
    Column('groupid', Integer, ForeignKey('groups.id')),
)

class Group(Base):
    __tablename__ = 'groups'
    id       = Column(Integer, primary_key=True)
    name     = Column(String(64), nullable=False)
    description = Column(String(256))
    perms    = Column(BigInteger, default=0, nullable=False)
    appperms = Column(BigInteger, default=0, nullable=False)
    
    users    = relationship('User', secondary=usergroup_association, backref='groups')

    natural_key = 'name'

class LoginHistory(Base):
    __tablename__ = 'login_history'
    id       = Column(Integer, primary_key=True)
    userid   = Column(ForeignKey('users.id'), nullable=False)
    time     = Column(DateTime, default=datetime.datetime.now, nullable=False)
    remote   = Column(String(64))
    useragent= Column(String(64))

class Domain(Base):
    __tablename__ = 'domains'
    short_name = 'domain'
    display_name = 'Domains'
    id       = Column(Integer, primary_key=True)
    userid   = Column(ForeignKey('users.id'), nullable=False)
    domain   = Column(String(256), nullable=False)
    hostedns = Column(Boolean, nullable=False)
    vhostid  = Column(ForeignKey('vhosts.id'))
    public   = Column(Boolean, default=False, nullable=False)
    verified = Column(Boolean, nullable=False, default=False)
    verif_token = Column(String(64))
    
    entries  = relationship('DomainEntry', backref='domain')
    mailboxes= relationship('Mailbox', backref='domain')

    natural_key = 'domain'

class DomainEntry(Base):
    __tablename__ = 'domainentries'
    short_name = 'domainentry'
    display_name = 'Domain Entries'
    id       = Column(Integer, primary_key=True)
    domainid = Column(ForeignKey('domains.id'), nullable=False)
    sub      = Column(String(256))
    rdatatype= Column(Integer, nullable=False)
    rdata    = Column(Text, nullable=False)

    panel_parent = Domain

class Mailbox(Base):
    __tablename__ = 'mailboxes'
    short_name = 'mailbox'
    display_name = 'Mailboxes'
    id       = Column(Integer, primary_key=True)
    userid   = Column(ForeignKey('users.id'), nullable=False)
    domainid = Column(ForeignKey('domains.id'), nullable=False)
    local_part = Column(String(64), nullable=True)
    password = Column(String(128))
    redirect = Column(String(512))
    
    @property
    def address(self):
        return self.local_part+'@'+self.domain.domain

    @address.setter
    def address(self, value):
        l, h = value.rsplit('@', 1)
        self.local_part = l
        # TODO: search for domain h
    
    natural_key = 'address'

class VHost(Base):
    __tablename__ = 'vhosts'
    short_name = 'vhost'
    display_name = 'VHosts'
    
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
    userid   = Column(ForeignKey('users.id'), nullable=False)
    update   = Column(DateTime, onupdate=datetime.datetime.now)
    catchall = Column(String(256))
    autoindex= Column(Boolean, nullable=False, default=False)
    apptype  = Column(BigInteger, nullable=False, default=0)
    applocation = Column(String(512))
    
    natural_key = 'name'
    
    domains  = relationship('Domain', backref='vhost')
    rewrites = relationship('VHostRewrite', backref='vhost')
    acls     = relationship('VHostACL', backref='vhost')
    errorpages=relationship('VHostErrorPage', backref='vhost')

class VHostRewrite(Base):
    display_name = 'URL Rewriting Rules'
    short_name = 'rewrite'
    __tablename__ = 'vhostrewrites'
    id       = Column(Integer, primary_key=True)
    vhostid  = Column(ForeignKey('vhosts.id'), nullable=False)
    regexp   = Column(String(256), nullable=False)
    dest     = Column(String(256), nullable=False)
    redirect_temp = Column(Boolean, nullable=False, default=False)
    redirect_perm = Column(Boolean, nullable=False, default=False)
    last     = Column(Boolean, nullable=False, default=False)
    

class VHostACL(Base):
    display_name = 'Access Control Lists'
    short_name = 'acl'
    __tablename__ = 'vhostacls'
    id       = Column(Integer, primary_key=True)
    title    = Column(String(256), nullable=False)
    vhostid  = Column(ForeignKey('vhosts.id'), nullable=False)
    regexp   = Column(String(256), nullable=False)
    passwd   = Column(String(256), nullable=False)
    

class VHostErrorPage(Base):
    display_name = 'Custom Error Pages'
    short_name = 'ep'
    __tablename__ = 'vhosterrorpages'
    id       = Column(Integer, primary_key=True)
    vhostid  = Column(ForeignKey('vhosts.id'), nullable=False)
    code     = Column(Integer, nullable=False)
    path     = Column(String(256), nullable=False)

