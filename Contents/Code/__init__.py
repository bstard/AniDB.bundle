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

CONNECTION = None
LAST_ACCESS = None

LANGUAGE_MAP = dict()

def Start():
  HTTP.CacheTime = 3600
  LANGUAGE_MAP["English"] = "english_name"
  LANGUAGE_MAP["Romaji"] = "romaji_name"
  LANGUAGE_MAP["Kanji"] = "kanji_name"

def titleKey():
  titlePref = Prefs["title_lang"]
  return LANGUAGE_MAP[titlePref]

def checkConnection():
  global LAST_ACCESS
  global CONNECTION
  
  Log("Checking for idle connection timeout...")
  
  LOCK.acquire()
  try:
    if CONNECTION is not None and LAST_ACCESS is not None and (datetime.now()-IDLE_TIMEOUT) > LAST_ACCESS:
      CONNECTION.stop()
      CONNECTION = None
      Log("Connection timeout reached. Closing connection!")
  except:
    pass
  finally:
    LOCK.release()
   
  if CONNECTION is not None:  
    Thread.CreateTimer(300, checkConnection)


class MotherAgent:

  def connect(self):

    global CONNECTION
    global LAST_ACCESS
        
    try:
      username = Prefs["username"]
      password = Prefs["password"]
      
      if CONNECTION is not None:
        if not CONNECTION.authed():
          CONNECTION.auth(username, password)
          
        Log("Reusing authenticated connection")
        LAST_ACCESS = datetime.now()
        return CONNECTION
      
      CONNECTION = adba.Connection(log=True)
      
      Thread.CreateTimer(300, checkConnection)
      
      if not username or not password:
          Log("Set username and password!")
          return None
      
      CONNECTION.auth(username, password)
      Log("Auth ok!")
        
    except Exception, e :
      Log("Connection exception, msg: " + str(e))
      raise e

    LAST_ACCESS = datetime.now()
    return CONNECTION
    
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
  
  def getAnimeInfo(self, connection, aid, metadata, movie=False, force=False):
    
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
      
      metadata.title = self.getValueWithFallbacks(anime.dataDict, titleKey(), 'english_name', 'romaji_name', 'kanji_name')
      
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
    

  def doHashSearch(self, results, filename, connection):
    filePath = urllib.unquote(filename)
  
    fileInfo = adba.File(connection, filePath=filePath,
         paramsF=["aid"],
         paramsA=["english_name", "romaji_name", "kanji_name", "year"])
    
    try:
      Log("Trying to lookup %s by file on anidb" % filePath)
      fileInfo.load_data()
    except Exception, e :
      Log("Could not load file data, msg: " + str(e))
      
    return fileInfo
    
  def doNameSearch(self, results, name, connection):
    fileInfo = adba.Anime(connection, name=name,
                       paramsA=["english_name", "kanji_name", "romaji_name", 
                                "year", "aid"])
    try:
      Log("Trying to lookup %s by name on anidb" % name)
      fileInfo.load_data()
    except Exception, e :
      Log("Could not load anime data, msg: " + str(e))
      raise e
    
    return fileInfo
    
  def doSearch(self, results, media, lang):
    
    connection = self.connect()

    if connection is None:
      return

    fileInfo = None
    
    if media.filename is not None:
      fileInfo = self.doHashSearch(results, media.filename, connection)
    
    if fileInfo is None or (not fileInfo.dataDict.has_key('aid') and (media.name is not None or media.show is not None)):
      metaName = media.name
      if metaName is None:
        metaName = media.show
        
      if metaName is not None and metaName.startswith('aid:'):
        aid = metaName[4:].strip()
        Log("Will search for metadata for anime id " + aid)
        results.Append(MetadataSearchResult(id=str(aid), name=metaName, year=None, score=100, lang=Locale.Language.English))
        return
        
      fileInfo = self.doNameSearch(results, metaName, connection)

    if not fileInfo.dataDict.has_key('aid'):
      Log("No match found or error occurred!")
      return
    
    aid = fileInfo.dataDict['aid']
        
    name = self.getValueWithFallbacks(fileInfo.dataDict, titleKey(), 'english_name', 'romaji_name', 'kanji_name')
    
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
    
  def update(self, metadata, media, lang, force):
    try:
      LOCK.acquire()
      self.doUpdate(metadata, media, lang, force)
    finally:
      LOCK.release()   
  
  def doUpdate(self, metadata, media, lang, force):
    connection = self.connect()
    if not connection:
      return

    self.getAnimeInfo(connection, metadata.id, metadata, True, force)
  
  
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

  def update(self, metadata, media, lang, force):
    try:
      LOCK.acquire()
      self.doUpdate(metadata, media, lang, force)
    finally:
      LOCK.release()

  def doUpdate(self, metadata, media, lang, force = False):

    connection = self.connect()
    if not connection:
      return

    self.getAnimeInfo(connection, metadata.id, metadata, False, force)

    for s in media.seasons:
      
      for picUrl in metadata.posters.keys():
        metadata.seasons[s].posters[picUrl] = Proxy.Media(HTTP.Request(picUrl).content)
      
      for ep in media.seasons[s].episodes:
  
        episodeKey = self.loadEpisode(connection, metadata, s, ep, force)

        metadata.seasons[s].episodes[ep].title = Dict[episodeKey + "title"]
        
        if str(episodeKey + "rating") in Dict:
          metadata.seasons[s].episodes[ep].rating = Dict[episodeKey + "rating"]
      
        if str(episodeKey + "length") in Dict:
          metadata.seasons[s].episodes[ep].duration = Dict[episodeKey + "length"]
          
        if str(episodeKey + "aired") in Dict:
          metadata.seasons[s].episodes[ep].originally_available_at = Dict[episodeKey + "aired"]
        
  def loadEpisode(self, connection, metadata, season, episode, force):
      
      epno = episode
      if str(season) == "0":
        epno = "S" + str(ep)

      episodeKey = str(season) + "-" + str(episode) + "-"


      Log("Force: " + str(force))
      Log("Has key: " + str(str(episodeKey + "title") in Dict))

      if str(episodeKey + "title") in Dict and not force:
        Log("Metadata for '" + metadata.title + "', season " + season + " episode " + epno + " found in cache")
        return episodeKey
      
      Log("Loading metadata for '" + metadata.title + "', season " + season + " episode " + epno + " from AniDB")

      episode = adba.Episode(connection, aid=metadata.id, epno=episode)

      try:   
        episode.load_data()
      except IndexError, e:
        Log("Episode number is incorrect, msg: " + str(e) + " for episode " + epno)
      except Exception, e :
        Log("Could not load episode info, msg: " + str(e))
        raise e
      
      Dict[episodeKey + "title"] = self.getValueWithFallbacks(episode.dataDict, titleKey(), 
                                                                           'english_name', 'romaji_name', 'kanji_name')
      if episode.dataDict.has_key('rating'):
        Dict[episodeKey + "rating"] = float(episode.dataDict['rating']) / 100
      
      if episode.dataDict.has_key('length'):
        Dict[episodeKey + "length"] = int(episode.dataDict['length']) * 60 * 1000
          
      if episode.dataDict.has_key('aired'):
        try:
          Dict[episodeKey + "aired"] = self.getDate(episode.dataDict['aired'])
        except:
          pass
      
      return episodeKey

