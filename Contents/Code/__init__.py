# coding=UTF-8
import adba
import sys
import os
import getopt
from datetime import datetime

ANIDB_PIC_URL_BASE = "http://img7.anidb.net/pics/anime/"


def Start():
  HTTP.CacheTime = 0

class MotherAgent:
  
  def connect(self):
    connection = adba.Connection(log=True)

    try:
        username = Prefs["username"]
        password = Prefs["password"]
        connection.auth(username, password)
    except Exception, e :
        Log("Auth exception msg: " + str(e))

    return connection
    
  def disconnect(self, connection):
    connection.stop()

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
  
  def getAnimeInfo(self, connection, aid, metadata):
    
    Log("Loading metadata for anime aid " + aid)
    
    anime = adba.Anime(connection, aid=metadata.id,
                       paramsA=["epno", "english_name", "kanji_name", "romaji_name", 
                                "year", "picname", "url", "rating", "episodes", 
                                "highest_episode_number", "air_date"])
    try:   
      anime.load_data()
    except Exception, e :
      Log("Could not load anime info, msg: " + str(e))
    
    try:
      if anime.dataDict.has_key('year'):
        year = anime.dataDict['year']
        if year.find('-') > -1:
          year = year[:year.find('-')]
        try:
          metadata.year = int(year)
        except:
          pass
        
      if anime.dataDict.has_key('rating'):
        metadata.rating = float(anime.dataDict['rating']) / 100
      
      metadata.title = self.getValueWithFallbacks(anime.dataDict, 'english_name', 'romaji_name', 'kanji_name')
      metadata.original_title = self.getValueWithFallbacks(anime.dataDict, 'romaji_name', 'kanji_name')
      metadata.originally_available_at = self.getDate(anime.dataDict['air_date'])
        
      if anime.dataDict.has_key('picname'):
        picUrl = ANIDB_PIC_URL_BASE + anime.dataDict['picname']
        metadata.posters[picUrl] = Proxy.Media(HTTP.Request(picUrl).content)

    except Exception, e:
      Log("Could not set anime metadata, msg: " + str(e))

    try:
      metadata.summary = self.getDescription(connection, metadata.id, 0)
    except:
      Log("Could not load description, msg: " + str(e))
    

  def doSearch(self, results, media, lang):
    
    connection = self.connect()

    filePath = String.Unquote(media.filename)
    fileInfo = adba.File(connection, filePath = filePath,
         paramsF=["aid"],
         paramsA=["epno", "english_name", "romaji_name", "year"])
    
    try:
        Log("Trying to lookup %s on anidb" % filePath)
        fileInfo.load_data()
    except Exception, e :
        Log("Could not load file data, msg: " + str(e))
    
    self.disconnect(connection)

    if not fileInfo.dataDict.has_key('aid'):
      return
      
    aid = fileInfo.dataDict['aid']
        
    name = self.getValueWithFallbacks(fileInfo.dataDict, 'english_name', 'romaji_name')
    
    year = fileInfo.dataDict['year']
    if year.find('-') > -1:
      year = year[:year.find('-')]
    
    Log("Appending metadata search result for anime " + name)
    
    results.Append(MetadataSearchResult(id=str(aid), name=name, year=year, score=100, lang=Locale.Language.English))

    
class AniDBAgentMovies(Agent.Movies, MotherAgent):
  
  name = 'AniDB'
  primary_provider = True
  languages = [Locale.Language.English]
  accepts_from = ['com.plexapp.agents.localmedia']

  def search(self, results, media, lang):
    self.doSearch(results, media, lang)
    
  def update(self, metadata, media, lang):

    connection = self.connect()
    self.getAnimeInfo(connection, metadata.id, metadata)
    self.disconnect(connection)    
  
  
class AniDBAgentTV(Agent.TV_Shows, MotherAgent):
  
  name = 'AniDB'
  primary_provider = True
  languages = [Locale.Language.English]
  accepts_from = ['com.plexapp.agents.localmedia']

  def search(self, results, media, lang):
    self.doSearch(results, media, lang)

  def update(self, metadata, media, lang):

    connection = self.connect()

    self.getAnimeInfo(connection, metadata.id, metadata)

    for s in media.seasons:
      
      for picUrl in metadata.posters.keys():
        metadata.seasons[s].posters[picUrl] = Proxy.Media(HTTP.Request(picUrl).content)
      
      for e in media.seasons[s].episodes:
        
        Log("Loading metadata for '" + metadata.title + "', episode " + e)
        
        episode = adba.Episode(connection, aid=metadata.id, epno=e)
  
        try:   
          episode.load_data()
        except Exception, e :
          Log("Could not load episode info, msg: " + str(e))
          
        metadata.seasons[s].episodes[e].title = self.getValueWithFallbacks(episode.dataDict, 
                                                                           'name', 'romaji', 'kanji')
        
        if episode.dataDict.has_key('rating'):
          metadata.seasons[s].episodes[e].rating = float(episode.dataDict['rating']) / 100
      
        if episode.dataDict.has_key('length'):
          metadata.seasons[s].episodes[e].duration = int(episode.dataDict['length']) * 60 * 1000
          
        if episode.dataDict.has_key('aired'):
          try:
            metadata.seasons[s].episodes[e].originally_available_at = self.getDate(episode.dataDict['aired'])
          except:
            pass

    self.disconnect(connection)    
