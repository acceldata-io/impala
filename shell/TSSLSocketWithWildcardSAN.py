#!/usr/bin/env ambari-python-wrap
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import print_function, unicode_literals

import re
import ssl

from thrift.transport import TSSLSocket
from thrift.transport.TTransport import TTransportException

class CertificateError(ValueError):
  """Convenience class to raise errors"""
  pass

class TSSLSocketWithWildcardSAN(TSSLSocket.TSSLSocket):
  """
  This is a subclass of thrift's TSSLSocket which has been extended to add the missing
  functionality of validating wildcard certificates and certificates with SANs
  (subjectAlternativeName).

  The core of the validation logic is based on the python-ssl library:
  See <https://svn.python.org/projects/python/tags/r32/Lib/ssl.py>
  """
  def __init__(self,
      host='localhost',
      port=9090,
      validate=True,
      ca_certs=None,
      unix_socket=None):
    cert_reqs = ssl.CERT_REQUIRED if validate else ssl.CERT_NONE
    # Set client protocol choice to be very permissive, as we rely on servers to enforce
    # good protocol selection. This value is forwarded to the ssl.wrap_socket() API during
    # open(). See https://docs.python.org/2/library/ssl.html#socket-creation for a table
    # that shows a better option is not readily available for sockets that use
    # wrap_socket().
    # THRIFT-3505 changes transport/TSSLSocket.py. The SSL_VERSION is passed to TSSLSocket
    # via a parameter.
    TSSLSocket.TSSLSocket.__init__(self, host=host, port=port, cert_reqs=cert_reqs,
                                   ca_certs=ca_certs, unix_socket=unix_socket,
                                   ssl_version=ssl.PROTOCOL_SSLv23)

  # THRIFT-5595: override TSocket.isOpen because it's broken for TSSLSocket
  def isOpen(self):
    return self.handle is not None

  def _validate_cert(self):
    cert = self.handle.getpeercert()
    self.peercert = cert
    if 'subject' not in cert:
      raise TTransportException(
        type=TTransportException.NOT_OPEN,
        message='No SSL certificate found from %s:%s' % (self.host, self.port))
    try:
      self._match_hostname(cert, self.host)
      self.is_valid = True
      return
    except CertificateError as ce:
      raise TTransportException(
        type=TTransportException.UNKNOWN,
        message='Certificate error with remote host: %s' % (ce))
    raise TTransportException(
      type=TTransportException.UNKNOWN,
      message='Could not validate SSL certificate from '
              'host "%s".  Cert=%s' % (self.host, cert))

  def _match_hostname(self, cert, hostname):
    """Verify that *cert* (in decoded format as returned by
    SSLSocket.getpeercert()) matches the *hostname*.  RFC 2818 and RFC 6125
    rules are followed, but IP addresses are not accepted for *hostname*.

    CertificateError is raised on failure. On success, the function
    returns nothing.
    """
    dnsnames = []
    san = cert.get('subjectAltName', ())
    for key, value in san:
      if key == 'DNS':
        if self._dnsname_match(value, hostname):
          return
        dnsnames.append(value)
    if not dnsnames:
      # The subject is only checked when there is no dNSName entry
      # in subjectAltName
      for sub in cert.get('subject', ()):
        for key, value in sub:
          # XXX according to RFC 2818, the most specific Common Name
          # must be used.
          if key == 'commonName':
            if self._dnsname_match(value, hostname):
              return
            dnsnames.append(value)
    if len(dnsnames) > 1:
      raise CertificateError("hostname %r "
        "doesn't match either of %s"
        % (hostname, ', '.join(map(repr, dnsnames))))
    elif len(dnsnames) == 1:
      raise CertificateError("hostname %r "
        "doesn't match %r"
        % (hostname, dnsnames[0]))
    else:
      raise CertificateError("no appropriate commonName or "
        "subjectAltName fields were found")

  def _dnsname_match(self, dn, hostname, max_wildcards=1):
    """Matching according to RFC 6125, section 6.4.3
    http://tools.ietf.org/html/rfc6125#section-6.4.3
    """
    pats = []
    if not dn:
      return False

    # Ported from python3-syntax:
    # leftmost, *remainder = dn.split(r'.')
    parts = dn.split(r'.')
    leftmost = parts[0]
    remainder = parts[1:]

    wildcards = leftmost.count('*')
    if wildcards > max_wildcards:
      # Issue #17980: avoid denials of service by refusing more
      # than one wildcard per fragment.  A survey of established
      # policy among SSL implementations showed it to be a
      # reasonable choice.
      raise CertificateError(
        "too many wildcards in certificate DNS name: " + repr(dn))

    # speed up common case w/o wildcards
    if not wildcards:
      return dn.lower() == hostname.lower()

    # RFC 6125, section 6.4.3, subitem 1.
    # The client SHOULD NOT attempt to match a presented identifier in which
    # the wildcard character comprises a label other than the left-most label.
    if leftmost == '*':
      # When '*' is a fragment by itself, it matches a non-empty dotless
      # fragment.
      pats.append('[^.]+')
    elif leftmost.startswith('xn--') or hostname.startswith('xn--'):
      # RFC 6125, section 6.4.3, subitem 3.
      # The client SHOULD NOT attempt to match a presented identifier
      # where the wildcard character is embedded within an A-label or
      # U-label of an internationalized domain name.
      pats.append(re.escape(leftmost))
    else:
      # Otherwise, '*' matches any dotless string, e.g. www*
      pats.append(re.escape(leftmost).replace(r'\*', '[^.]*'))

    # add the remaining fragments, ignore any wildcards
    for frag in remainder:
      pats.append(re.escape(frag))

    pat = re.compile(r'\A' + r'\.'.join(pats) + r'\Z', re.IGNORECASE)
    return pat.match(hostname)
