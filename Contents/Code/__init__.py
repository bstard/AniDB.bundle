import adba
import sys
import os
import getopt
import urllib
import threading
from datetime import datetime, timedelta

ANIDB_PIC_URL_BASE = "http://img7.anidb.net/pics/anime/"

IDLE_TIMEOUT = timedelta(seconds = 60 * 5)

LOCK = threading.RLock()

def Start():
  HTTP.CacheTime = 0

class MotherAgent:

  lastAccess = None
  connection = None

  def connect(self):
    
    now = datetime.now()
    
    if self.connection:
      if self.lastAccess and (now-IDLE_TIMEOUT) <= self.lastAccess:
        Log("Reusing authenticated connection")
        self.lastAccess = datetime.now()
        return self.connection 
    
      try:
          self.connection.stop()
          self.connection = None
      except:
          pass
    
    self.connection = adba.Connection(log=True)

    try:
        username = Prefs["username"]
        password = Prefs["password"]
        
        if not username or not password:
            Log("Set username and password!")
            return None
        
        self.connection.auth(username, password)
        Log("Auth ok!")
        
    except Exception, e :
        Log("Auth exception msg: " + str(e))
        raise e

    self.lastAccess = datetime.now()
    
    return self.connection
    
  def decodeString(self, string = None):
    if string == None:
      return string
    
    bracketStart = string.find('[')
    bracketEnd = string.find(']') 
    if bracketStart > -1 and bracketEnd > bracketStart:
      string = string[:bracketStart] + string[bracketEnd+1:]
      string = self.decodeString(string)
      
    lt = string.find('<')
    gt = string.find('>') 
    if lt > -1 and gt > lt:
      string = string[:lt] + string[gt+1:]
      string = self.decodeString(string)
    
    return string

  def getDescription(self, connection, aid, part):
    
    animeDesc = adba.AnimeDesc(connection, aid=aid, part=part)

    animeDesc.load_data()

    if not animeDesc.dataDict.has_key('description'):
      Log("No description found for anime aid " + aid)
      return None

    desc = self.decodeString(animeDesc.dataDict['description'])
    
    currentPart = int(animeDesc.dataDict['current_part'])
    maxParts = int(animeDesc.dataDict['max_parts'])
    
    if (maxParts-currentPart) > 1:
      desc = desc + self.getDescription(connection, aid, part+1)
    
    return desc

  def getValueWithFallbacks(self, dictionary, *names):
    for name in names:
      if dictionary.has_key(name) and len(dictionary[name]) > 0:
        return dictionary[name]
      
    return None
  
  def getDate(self, timestampString):
    return datetime.fromtimestamp(int(timestampString))
  
  def getAnimeInfo(self, connection, aid, metadata, movie=False):
    
    Log("Loading metadata for anime aid " + aid)
    
    anime = adba.Anime(connection, aid=metadata.id,
                       paramsA=["epno", "english_name", "kanji_name", "romaji_name", 
                                "year", "picname", "url", "rating", "episodes", 
                                "highest_episode_number", "air_date"])
    try:   
      anime.load_data()
    except Exception, e :
      Log("Could not load anime info, msg: " + str(e))
      raise e
    
    try:
      if movie and anime.dataDict.has_key('year'):
        year = str(anime.dataDict['year'])
        if year.find('-') > -1:
          year = year[:year.find('-')]
        try:
          metadata.year = int(year)
        except:
          pass
        
      if anime.dataDict.has_key('rating'):
        metadata.rating = float(anime.dataDict['rating']) / 100
      
      metadata.title = self.getValueWithFallbacks(anime.dataDict, 'english_name', 'romaji_name', 'kanji_name')
      if movie:
          metadata.original_title = self.getValueWithFallbacks(anime.dataDict, 'romaji_name', 'kanji_name')
      metadata.originally_available_at = self.getDate(anime.dataDict['air_date'])
        
      if anime.dataDict.has_key('picname'):
        picUrl = ANIDB_PIC_URL_BASE + anime.dataDict['picname']
        metadata.posters[picUrl] = Proxy.Media(HTTP.Request(picUrl).content)

    except Exception, e:
      Log("Could not set anime metadata, msg: " + str(e))
      raise e

    try:
      metadata.summary = self.getDescription(connection, metadata.id, 0)
    except Exception, e:
      Log("Could not load description, msg: " + str(e))
      raise e
    

  def doSearch(self, results, media, lang):
    
    connection = self.connect()

    if not connection:
      return

    filePath = urllib.unquote(media.filename)

    fileInfo = adba.File(connection, filePath=filePath,
         paramsF=["aid"],
         paramsA=["english_name", "romaji_name", "kanji_name", "year"])
    
    try:
      Log("Trying to lookup %s by file on anidb" % filePath)
      fileInfo.load_data()
    except Exception, e :
      Log("Could not load file data, msg: " + str(e))
    
    if not fileInfo.dataDict.has_key('aid') and media.name != None:
      fileInfo = adba.Anime(connection, name=media.name,
                         paramsA=["english_name", "kanji_name", "romaji_name", 
                                  "year", "aid"])
      try:
        Log("Trying to lookup %s by name on anidb" % media.name)
        fileInfo.load_data()
      except Exception, e :
        Log("Could not load anime data, msg: " + str(e))
        raise e
      
    if not fileInfo.dataDict.has_key('aid'):
      Log("No match found or error occurred!")
      return
    
    aid = fileInfo.dataDict['aid']
        
    name = self.getValueWithFallbacks(fileInfo.dataDict, 'english_name', 'romaji_name', 'kanji_name')
    
    year = str(fileInfo.dataDict['year'])
    if year.find('-') > -1:
      year = year[:year.find('-')]
    
    Log("Appending metadata search result for anime " + name)
    
    results.Append(MetadataSearchResult(id=str(aid), name=name, year=int(year), score=100, lang=Locale.Language.English))

    
class AniDBAgentMovies(Agent.Movies, MotherAgent):
  
  name = 'AniDB'
  primary_provider = True
  languages = [Locale.Language.English]
  accepts_from = ['com.plexapp.agents.localmedia', 'com.plexapp.agents.opensubtitles']

  def search(self, results, media, lang):
    try:
      LOCK.acquire()
      self.doSearch(results, media, lang)
    finally:
      LOCK.release()
    
  def update(self, metadata, media, lang):
    try:
      LOCK.acquire()
      self.doUpdate(metadata, media, lang)
    finally:
      LOCK.release()   
  
  def doUpdate(self, metadata, media, lang):
    connection = self.connect()
    if not connection:
      return
    self.getAnimeInfo(connection, metadata.id, metadata, movie=True)
  
  
class AniDBAgentTV(Agent.TV_Shows, MotherAgent):
  
  name = 'AniDB'
  primary_provider = True
  languages = [Locale.Language.English]
  accepts_from = ['com.plexapp.agents.localmedia', 'com.plexapp.agents.opensubtitles']

  def search(self, results, media, lang):
    try:
      LOCK.acquire()
      self.doSearch(results, media, lang)
    finally:
      LOCK.release()

  def update(self, metadata, media, lang):
    try:
      LOCK.acquire()
      self.doUpdate(metadata, media, lang)
    finally:
      LOCK.release()

  def doUpdate(self, metadata, media, lang):

    connection = self.connect()
    if not connection:
      return

    self.getAnimeInfo(connection, metadata.id, metadata)

    for s in media.seasons:
      
      for picUrl in metadata.posters.keys():
        metadata.seasons[s].posters[picUrl] = Proxy.Media(HTTP.Request(picUrl).content)
      
      for ep in media.seasons[s].episodes:
        
        Log("Loading metadata for '" + metadata.title + "', episode " + ep)
        
        episode = adba.Episode(connection, aid=metadata.id, epno=ep)
  
        try:   
          episode.load_data()
        except IndexError, e:
          Log("Episode number is incorrect, msg: " + str(e) + " for episode " + ep)
        except Exception, e :
          Log("Could not load episode info, msg: " + str(e))
          raise e
          
        metadata.seasons[s].episodes[ep].title = self.getValueWithFallbacks(episode.dataDict, 
                                                                           'name', 'romaji', 'kanji')
        if episode.dataDict.has_key('rating'):
          metadata.seasons[s].episodes[ep].rating = float(episode.dataDict['rating']) / 100
      
        if episode.dataDict.has_key('length'):
          metadata.seasons[s].episodes[ep].duration = int(episode.dataDict['length']) * 60 * 1000
          
        if episode.dataDict.has_key('aired'):
          try:
            metadata.seasons[s].episodes[ep].originally_available_at = self.getDate(episode.dataDict['aired'])
          except:
            pass
