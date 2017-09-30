# -*- coding: utf-8 -*-
"""
/***************************************************************************
Name                 : Qt API for Catalog Planet Labs 
Description          : API for Planet Labs
Date                 : May, 2015
copyright            : (C) 2015 by Luiz Motta
email                : motta.luiz@gmail.com

 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import json, datetime


from PyQt4.QtCore import ( Qt, QObject, QByteArray, QUrl, pyqtSignal, pyqtSlot )
from PyQt4.QtNetwork import ( QNetworkAccessManager, QNetworkRequest, QNetworkReply )
from PyQt4.QtGui import( QPixmap )

class AccessSite(QObject):

  # Signals
  finished = pyqtSignal( dict)
  send_data = pyqtSignal(QByteArray)
  status_download = pyqtSignal(int, int)
  status_erros = pyqtSignal(list)
  
  ErrorCodeAttribute = { 
     10: 'Canceled request',
    400: 'Bad request syntax',
    401: 'Unauthorized',
    402: 'Payment required',
    403: 'Forbidden',
    404: 'Not found',
    500: 'Internal error',
    501: 'Not implemented',
    502: 'Bad Gateway'  
  }

  def __init__(self):
    super( AccessSite, self ).__init__()
    self.networkAccess = QNetworkAccessManager( self )
    self.totalReady = self.reply = self.triedAuthentication = self.isKilled = None
    # Input by self.run
    self.key = self.responseAllFinished = None

  def run(self, url, key='', responseAllFinished=False, json_request=None):
    ( self.key, self.responseAllFinished ) = ( key, responseAllFinished )
    self._connect()
    self.totalReady = 0
    self.isKilled = False
    request = QNetworkRequest( url )
    if json_request is None:
      reply = self.networkAccess.get( request )
    else:
      request.setHeader( QNetworkRequest.ContentTypeHeader, "application/json" )
      data = QByteArray( json.dumps( json_request ) )
      reply = self.networkAccess.post( request, data )
    if reply is None:
      response = { 'isOk': False, 'message': "Network error", 'errorCode': -1 }
      self._connect( False )
      self.finished.emit( response )
      return

    self.triedAuthentication = False
    self.reply = reply
    self._connectReply()
  
  def kill(self):
    self.isKilled = True
  
  def isRunning(self):
    return ( not self.reply is None and self.reply.isRunning() )  

  def _connect(self, isConnect=True):
    ss = [
      { 'signal': self.networkAccess.finished, 'slot': self.replyFinished },
      { 'signal': self.networkAccess.authenticationRequired, 'slot': self.authenticationRequired }
    ]
    if isConnect:
      for item in ss:
        item['signal'].connect( item['slot'] )  
    else:
      for item in ss:
        item['signal'].disconnect( item['slot'] )

  def _connectReply(self, isConnect=True):
    ss = [
      { 'signal': self.reply.readyRead, 'slot': self.readyRead },
      { 'signal': self.reply.downloadProgress, 'slot': self.downloadProgress },
      { 'signal': self.reply.sslErrors, 'slot': self.sslErrors }
    ]
    if isConnect:
      for item in ss:
        item['signal'].connect( item['slot'] )  
    else:
      for item in ss:
        item['signal'].disconnect( item['slot'] )

  def _clearConnect(self):
    self._connect( False ) # self.reply.close() -> emit signal self.networkAccess.finished
    self._connectReply( False )
    self.reply.close()
    self.reply.deleteLater();
    del self.reply
    self.reply = None

  def _redirectionReply(self, url):
    self._clearConnect()
    self._connect()
    if url.isRelative():
      url = url.resolved( url )

    request = QNetworkRequest( url )
    reply = self.networkAccess.get( request )
    if reply is None:
      response = { 'isOk': False, 'message': "Netwok error", 'errorCode': -1 }
      self._connect( False )
      self.finished.emit( response )
      return

    self.reply = reply
    self._connectReply()
    
  def _errorCodeAttribute(self, code):
    msg = 'Error network' if not code in self.ErrorCodeAttribute.keys() else AccessSite.ErrorCodeAttribute[ code ]
    response = { 'isOk': False, 'message': msg, 'errorCode': code }
    self._clearConnect()
    self.finished.emit( response )

  @pyqtSlot('QNetworkReply')
  def replyFinished(self, reply) :
    if self.isKilled:
      self._errorCodeAttribute(10)

    if reply.error() != QNetworkReply.NoError :
      response = { 'isOk': False, 'message': reply.errorString(), 'errorCode': reply.error() }
      self._clearConnect()
      self.finished.emit( response )
      return

    urlRedir = reply.attribute( QNetworkRequest.RedirectionTargetAttribute )
    if not urlRedir is None and urlRedir != reply.url():
      self._redirectionReply( urlRedir )
      return

    codeAttribute = reply.attribute( QNetworkRequest.HttpStatusCodeAttribute )
    if codeAttribute != 200:
      self._errorCodeAttribute( codeAttribute )
      return

    statusRequest = {
      'contentTypeHeader': reply.header( QNetworkRequest.ContentTypeHeader ),
      'lastModifiedHeader': reply.header( QNetworkRequest.LastModifiedHeader ),
      'contentLengthHeader': reply.header( QNetworkRequest.ContentLengthHeader ),
      'statusCodeAttribute': reply.attribute( QNetworkRequest.HttpStatusCodeAttribute ),
      'reasonPhraseAttribute': reply.attribute( QNetworkRequest.HttpReasonPhraseAttribute )
    }
    response = { 'isOk': True, 'statusRequest': statusRequest }
    if self.responseAllFinished:
      response[ 'data' ] = reply.readAll()
    else:
      response[ 'totalReady' ] = self.totalReady

    self._clearConnect()
    self.finished.emit( response )

  @pyqtSlot('QNetworkReply', 'QAuthenticator')
  def authenticationRequired (self, reply, authenticator):
    if not self.triedAuthentication: 
      authenticator.setUser( self.key )
      authenticator.setPassword ('')
      self.triedAuthentication = True
    else:
      self._errorCodeAttribute( 401 )

  @pyqtSlot()
  def readyRead(self):
    if self.isKilled:
      self._errorCodeAttribute(10)
      return

    if self.responseAllFinished:
      return

    urlRedir = self.reply.attribute( QNetworkRequest.RedirectionTargetAttribute )
    if not urlRedir is None and urlRedir != self.reply.url():
      self._redirectionReply( urlRedir )
      return

    codeAttribute = self.reply.attribute( QNetworkRequest.HttpStatusCodeAttribute )
    if codeAttribute != 200:
      self._errorCodeAttribute( codeAttribute )
      return

    data = self.reply.readAll()
    if data is None:
      return
    self.totalReady += len ( data )
    self.send_data.emit( data )

  @pyqtSlot(int, int)
  def downloadProgress(self, bytesReceived, bytesTotal):
    if self.isKilled:
      self._errorCodeAttribute(10)
    else:
      self.status_download.emit( bytesReceived, bytesTotal )

  @pyqtSlot( list )
  def sslErrors(self, errors):
    lstErros = map( lambda e: e.errorString(), errors )
    self.status_erros.emit( lstErros )
    self.reply.ignoreSslErrors()


class API_PlanetLabs(QObject):

  ErrorCodeLimitOK = (201, 207)
  validKey = None
  urlRoot = "https://api.planet.com"
  urlQuickSearch = "https://api.planet.com/data/v1/quick-search"
  urlThumbnail = "https://api.planet.com/data/v1/item-types/{item_type}/items/{item_id}/thumb"
  urlTMS = "https://tiles.planet.com/data/v1/{item_type}/{item_id}/{{z}}/{{x}}/{{y}}.png"
  urlAssets = "https://api.planet.com/data/v1/item-types/{item_type}/items/{item_id}/assets" 


  def __init__(self):
    super( API_PlanetLabs, self ).__init__()
    self.access = AccessSite()
    self.currentUrl = None

  def _clearResponse(self, response):
    if response.has_key('data'):
      response['data'].clear()
      del response[ 'data' ]
    del response[ 'statusRequest' ]

  def kill(self):
    self.access.kill()

  def isRunning(self):
    return self.access.isRunning()

  def isHostLive(self, setFinished):
    @pyqtSlot(dict)
    def finished( response):
      self.access.finished.disconnect( finished )
      if response['isOk']:
        response[ 'isHostLive' ] = True
        self._clearResponse( response )
      else:
        if response['errorCode'] == QNetworkReply.HostNotFoundError:
          response[ 'isHostLive' ] = False
          response[ 'message' ] += "\nURL = %s" % API_PlanetLabs.urlRoot
        else:
          response[ 'isHostLive' ] = True

      setFinished( response )

    self.currentUrl = API_PlanetLabs.urlRoot
    url = QUrl( self.currentUrl )
    self.access.finished.connect( finished )
    self.access.run( url, '', True ) # Send all data in finished

  def setKey(self, key, setFinished):
    @pyqtSlot(dict)
    def finished( response):
      self.access.finished.disconnect( finished )
      if response['isOk']:
        API_PlanetLabs.validKey = key
        self._clearResponse( response )

      setFinished( response )

    self.currentUrl = API_PlanetLabs.urlRoot
    url = QUrl( self.currentUrl )
    self.access.finished.connect( finished )
    self.access.run( url, key, True ) # Send all data in finished

  def getUrlScenes(self, json_request, setFinished):
    @pyqtSlot(dict)
    def finished( response):
      self.access.finished.disconnect( finished )
      if response[ 'isOk' ]:
        data = json.loads( str( response['data'] ) )
        response[ 'url_scenes' ] = data['_links']['_self']
        response['total'] = len( data['features'] )
        
        data.clear()
        self._clearResponse( response )

      setFinished( response )

    self.currentUrl = API_PlanetLabs.urlQuickSearch
    url = QUrl( self.currentUrl )
    self.access.finished.connect( finished )
    self.access.run( url, API_PlanetLabs.validKey, True, json_request )

  def getScenes(self, url, setFinished):
    @pyqtSlot(dict)
    def finished( response):
      self.access.finished.disconnect( finished )
      if response[ 'isOk' ]:
        data = json.loads( str( response[ 'data' ] ) )
        response[ 'url' ] = data[ '_links' ][ '_next' ]
        response[ 'scenes' ] = data[ 'features' ]
        self._clearResponse( response )

      setFinished( response )

    self.currentUrl = url
    url = QUrl.fromEncoded( url )
    self.access.finished.connect( finished )
    self.access.run( url, API_PlanetLabs.validKey, True )

  def getAssetsStatus(self, item_type, item_id, setFinished):
    @pyqtSlot(dict)
    def finished( response):
      def setStatus(asset):
        def getDateTimeFormat(d):
          dt = datetime.datetime.strptime( d, "%Y-%m-%dT%H:%M:%S.%f")
          return dt.strftime( formatDateTime )

        key = "a_{0}".format( asset )
        response['assets_status'][ key ] = {}
        r = response['assets_status'][ key ]
        if not data.has_key( asset ):
          r['status'] = "*None*"
          return
        if data[ asset ].has_key('status'):
          r['status'] = data[ asset ]['status']
        if data[ asset ].has_key('_permissions'):
          permissions = ",".join( data[ asset ]['_permissions'])
          r['permissions'] = permissions
        if data[ asset ].has_key('expires_at'):
          r['expires_at'] = getDateTimeFormat( data[ asset ]['expires_at'] )
        if data[ asset ].has_key('_links'):
          if data[ asset ]['_links'].has_key('activate'):
            r['activate'] = data[ asset ]['_links']['activate']
        if data[ asset ].has_key('location'):
          r['location'] = data[ asset ]['location']

      self.access.finished.disconnect( finished )
      if response[ 'isOk' ]:
        formatDateTime = '%Y-%m-%d %H:%M:%S'
        date_time = datetime.datetime.now().strftime( formatDateTime )
        response['assets_status'] = {
          'date_calculate': date_time,
          'url': self.currentUrl
        }
        data = json.loads( str( response[ 'data' ] ) )
        setStatus('analytic')
        setStatus('udm') 
        self._clearResponse( response )

      setFinished( response )

    url = API_PlanetLabs.urlAssets.format(item_type=item_type, item_id=item_id)
    self.currentUrl = url
    url = QUrl.fromEncoded( url )

    self.access.finished.connect( finished )
    self.access.run( url, API_PlanetLabs.validKey, True )

  def getThumbnail(self, item_id, item_type, setFinished):
    @pyqtSlot(dict)
    def finished( response ):
      self.access.finished.disconnect( finished )
      if response['isOk']:
        pixmap = QPixmap()
        pixmap.loadFromData( response[ 'data' ] )
        response[ 'pixmap' ] = pixmap
        self._clearResponse( response )

      setFinished( response )

    url = API_PlanetLabs.urlThumbnail.format( item_type=item_type, item_id=item_id )
    self.currentUrl = url
    url = QUrl( url )
    self.access.finished.connect( finished )
    self.access.run( url, API_PlanetLabs.validKey, True )

  def activeAsset(self, url, setFinished):
    @pyqtSlot(dict)
    def finished( response ):
      self.access.finished.disconnect( finished )
      if response['isOk']:
        self._clearResponse( response )
      setFinished( response ) # response[ 'totalReady' ]
      
    url = QUrl.fromEncoded( url )
    url = QUrl( url )
    self.access.finished.connect( finished )
    self.access.run( url, API_PlanetLabs.validKey, True )
    
  def saveImage(self, url, setFinished, setSave, setProgress):
    @pyqtSlot(dict)
    def finished( response ):
      self.access.finished.disconnect( finished )
      if response['isOk']:
        self._clearResponse( response )
      setFinished( response ) # response[ 'totalReady' ]
      
    url = QUrl.fromEncoded( url )
    self.access.finished.connect( finished )
    self.access.send_data.connect( setSave )
    self.access.status_download.connect( setProgress )
    self.access.run( url, API_PlanetLabs.validKey, False )

  @staticmethod
  def getUrlFilterScenesOrtho(filters):
    items = []
    for item in filters.iteritems():
      skey = str( item[0] )
      svalue = str( item[1] )
      items.append( ( skey, svalue ) )

    url = QUrl( API_PlanetLabs.urlScenesOrtho) # urlScenesRapideye
    url.setQueryItems( items )

    return url.toEncoded()

  @staticmethod
  def getValue(jsonMetadataFeature, keys):
    dicMetadata = jsonMetadataFeature
    if not isinstance( jsonMetadataFeature, dict):
      dicMetadata = json.loads( jsonMetadataFeature )
    msgError = None
    e_keys = map( lambda item: "'%s'" % item, keys )
    try:
      value = reduce( lambda d, k: d[ k ], [ dicMetadata ] + keys )
    except KeyError as e:
      msgError = "Catalog Planet: Have invalid key: %s" % ' -> '.join( e_keys)
    except TypeError as e:
      msgError = "Catalog Planet: The last key is invalid: %s" % ' -> '.join( e_keys)

    if msgError is None and isinstance( value, dict):
      msgError = "Catalog Planet: Missing key: %s" % ' -> '.join( e_keys)

    return ( True, value ) if msgError is None else ( False, msgError ) 

  @staticmethod
  def getTextTreeMetadata( jsonMetadataFeature ):
    def fill_item(strLevel, value):
      if not isinstance( value, ( dict, list ) ):
        items[-1] += ": %s" % value
        return

      if isinstance( value, dict ):
        for key, val in sorted( value.iteritems() ):
          items.append( "%s%s" % ( strLevel, key ) )
          strLevel += signalLevel
          fill_item( strLevel, val )
          strLevel = strLevel[ : -1 * len( signalLevel ) ]
      return

      if isinstance( value, list ):
        for val in value:
          if not isinstance( value, ( dict, list ) ):
            items[-1] += ": %s" % value
          else:
            text = '[dict]' if isinstance( value, dict ) else '[list]'
            items.append( "%s%s" % ( strLevel, text ) )
            strLevel += signalLevel
            fill_item( strLevel, val )
            strLevel = strLevel[ : -1 * len( signalLevel ) ]

    signalLevel = "- "
    items = []
    fill_item( '', json.loads( jsonMetadataFeature ) )
    
    return '\n'.join( items )

  @staticmethod
  def getHtmlTreeMetadata(value, html):
    if isinstance( value, dict ):
      html += "<ul>"
      for key, val in sorted( value.iteritems() ):
        if not isinstance( val, dict ):
          html += "<li>%s: %s</li> " % ( key, val )
        else:
          html += "<li>%s</li> " % key
        html = API_PlanetLabs.getHtmlTreeMetadata( val, html )
      html += "</ul>"
      return html
    return html

  @staticmethod
  def getTextValuesMetadata( dicMetadataFeature ):
    def fill_item(value):
      def addValue(_value):
        _text = "'%s' = %s" % (", ".join( keys ),  _value )
        items.append( _text )

      if not isinstance( value, ( dict, list ) ):
        addValue( value )
        return

      if isinstance( value, dict ):
        for key, val in sorted( value.iteritems() ):
          keys.append( '"%s"' % key )
          fill_item( val )
          del keys[ -1 ]
      return

      if isinstance( value, list ):
        for val in value:
          if not isinstance( val, ( dict, list ) ):
            addValue( val )
          else:
            text = "[dict]" if isinstance( val, dict ) else "[list]"
            keys.append( '"%s"' % text )
            fill_item( val )
            del keys[ -1 ]

    keys = []
    items = []
    fill_item( dicMetadataFeature )
    
    return '\n'.join( items )

  @staticmethod
  def getQTreeWidgetMetadata( jsonMetadataFeature, parent=None ):
    def createTreeWidget():
      tw = QTreeWidget(parent)
      tw.setColumnCount( 2 )
      tw.header().hide()
      tw.clear()
      return tw
 
    def fill_item(item, value):
      item.setExpanded( True )
      if not isinstance( value, ( dict, list ) ):
        item.setData( 1, Qt.DisplayRole, value )
        return

      if isinstance( value, dict ):
        for key, val in sorted( value.iteritems() ):
          child = QTreeWidgetItem()
          child.setText( 0, unicode(key) )
          item.addChild( child )
          fill_item( child, val )
      return

      if isinstance( value, list ):
        for val in value:
          if not isinstance( val, ( dict, list ) ):
            item.setData( 1, Qt.DisplayRole, val )
          else:
            child = QTreeWidgetItem()
            item.addChild( child )
            text = '[dict]' if isinstance( value, dict ) else '[list]'
            child.setText( 0, text )
            fill_item( child , val )

          child.setExpanded(True)

    tw = createTreeWidget()
    fill_item( tw.invisibleRootItem(), json.loads( jsonMetadataFeature ) )
    tw.resizeColumnToContents( 0 )
    tw.resizeColumnToContents( 1 )
    
    return tw
