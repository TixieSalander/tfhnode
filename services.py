from models import VHosts, Users
from mako.template import Template
import os
import logging
import subprocess

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
            process = self.__class__.__name__
            try:
                pid = int(open(self.pidfile).read())
                r = subprocess.call(['kill', '-'+signal, str(pid)])
                if r != 0:
                    logging.error('Failed to sent %s to %s!', signal, process)
            except FileNotFoundError:
                logging.warning('Pidfile not found for '+process)
    
    def generate_vhost(self, vhost):
        raise NotImplementedError()
        
def get_ssl_certs(vhost):
    # User-provided SSL cert
    base = '/home/%s/ssl/%s' % (vhost.user.username, vhost.name)
    user_cert, user_key = base+'.crt', base+'.key'
    if os.path.isfile(user_cert) and os.path.isfile(user_key):
        logging.debug('-> found user SSL cert.')
        return (user_cert, user_key)
    
    # System-wide wildcard
    for domain in vhost.domains:
        parts = domain.domain.split('.')
        for i in range(1, len(parts)-1):
            hmm = '.'.join(parts[i:])
            cert = '/etc/ssl/tfhcerts/wildcard.%s.crt' % (hmm)
            key  = '/etc/ssl/tfhkeys/wildcard.%s.key' % (hmm)
            if os.path.isfile(cert) and os.path.isfile(key):
                logging.debug('-> found wildcard SSL cert.')
                return (cert, key)

    # None found, cannot enable SSL
    # TODO: Generate a certificate/key for given vhost
    #       If possible, signed with CACert.
    return None

class NginxService(Service):
    def __init__(self, output, pidfile, server, options):
        self.output_dir = output
        self.output_ext = '.conf'
        self.pidfile = pidfile
        self.reload_signal = 'SIGHUP'
        self.options = options
        self.template = Template(filename=os.path.join(os.path.dirname(__file__), 'templates/nginx.conf'))
        self.server = server

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
                elif self.options['make-http-dirs']:
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

        if vhost.apptype == 0x20: # uwsgi apps
            # FIXME: Make check on vhost.applocation
            tpl = Template(filename=os.path.join(os.path.dirname(__file__), 'templates/uwsgi.ini'))
            filename = self.options['output-emperor']+vhost.user.username+'_'+vhost.name+'.ini'
            logging.debug('-> uwsgi app: '+filename)
            appsocket = '/var/lib/uwsgi/app_%s_%s.sock' %(vhost.user.username, vhost.name)
            fh = open(filename, 'w')
            fh.write(tpl.render(
                vhost=vhost, user=vhost.user,
            ))
            fh.close()
        
        domains = []
        for d in vhost.domains:
            logging.debug('-> domain: %s'%d.domain)
            if not self.options['require-verified-domains'] or d.verified:
                domains.append(d)

        addresses = ['127.0.0.1', '::1']
        if self.server.ipv4:
            addresses.append(self.server.ipv4)
        if self.server.ipv6:
            addresses.append(self.server.ipv6)
        
        ssl_enable = False
        ssl_cert = None
        ssl_key = None
        r = get_ssl_certs(vhost)
        if r:
            ssl_cert, ssl_key = r
            ssl_enable = True

        fh.write(self.template.render(
            listen_addr = addresses,
            user = vhost.user.username,
            name = vhost.name,
            ssl_enable = ssl_enable,
            ssl_port = self.options['ssl-port'],
            ssl_cert = ssl_cert,
            ssl_key = ssl_key,
            pubdir = pubdir,
            hostnames = ' '.join([d.domain for d in domains]),
            autoindex = vhost.autoindex,
            catchall = vhost.catchall,
            rewrites = vhost.rewrites,
            error_pages = vhost.errorpages,
            acl = vhost.acls,
            apptype = vhost.apptype,
            appsocket = appsocket,
            applocation = vhost.applocation,
        ))
        
        if ssl_enable:
            # Add the same vhost without SSL
            fh.write(self.template.render(
                listen_addr = addresses,
                user = vhost.user.username,
                name = vhost.name,
                ssl_enable = False,
                ssl_port = options['ssl-port'],
                ssl_cert = None,
                ssl_key = None,
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
        self.template = Template(filename=os.path.join(os.path.dirname(__file__), './templates/uwsgi.ini'))

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
        self.reload_signal = 'SIGUSR2'
        self.template = Template(filename=os.path.join(os.path.dirname(__file__), './templates/phpfpm.conf'))

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



