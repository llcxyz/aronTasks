# coding:utf-8
import odoorpc
import urlparse
import logging
log = logging.getLogger(__name__)

class wsCluster:
    _cache = {}

    def __init__(self, url=None, host='127.0.0.1', port=8069, protocol='jsonrpc'):
        self.host = host
        self.port = port
        self.protocol = protocol
        self.login = None
        self.password = None
        self.dbname = False

        if url:
            self.parse_url(url)

    def parse_url(self, url):
        pr = urlparse.urlparse(url)
        if pr.scheme == 'https':
            self.protocol = 'jsonrpc+ssl'
        r = pr.netloc.split(":")
        if len(r) >= 2:
            if r[0].find("@") != -1:
                vl = r[0].split("@")
                self.host = vl[1]
                self.login, self.password = vl[0].split("|")
            self.port = int(r[1])
        else:
            self.host = r[0]
            self.port = 80

        # print 'host=%s, port=%s, protocl=%s, login=%s,password=%s'%(self.host,self.port,self.protocol,self.login,self.password)

    def db(self, db, login=None, password=None):
        self.dbname = db
        if login:
            self.login = login
        if password:
            self.password = password
        # print 'login=', self.login, self.password
        if not self.login and not self.password:
            raise AttributeError(u"Login&Password Required!")

        indent = "%s:%s" % (self.dbname, self.login)
        if indent in self._cache:
            log.info(u"使用缓存实例:%s " % indent)
            return self._cache[indent]
        else:
            odoo = odoorpc.ODOO(host=self.host, protocol=self.protocol, port=self.port)
            odoo.login(self.dbname, self.login, self.password)
            odoo.dbname = self.dbname
            self._cache[indent] = odoo
            return odoo

if __name__ == "__main__":
    # vcluster = wsCluster(host='127.0.0.1', port=8069)
    db = cluster.db("wsum")
    #
    users = db.env['res.users']
    # ids = users.search([])
    # for idx in ids:
    #     print users.read(idx, ['name'])


