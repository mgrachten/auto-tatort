#!/usr/bin/python
import sys, codecs, locale
import feedparser
import datetime
import urlparse
from urllib import urlopen, urlretrieve
import json
import re
from HTMLParser import HTMLParser

#Wrap sysout so we don't run into problems when printing unicode characters to the console.
#This would otherwise be a problem when we are invoked on Debian using cron: 
#Console will have encoding NONE and fail to print some titles with umlauts etc
#might also fix printing on Windows consoles
#see https://wiki.python.org/moin/PrintFails
sys.stdout = codecs.getwriter(locale.getpreferredencoding())(sys.stdout);

RSS_URL = "http://www.ardmediathek.de/tv/Tatort/Sendung?documentId=602916&bcastId=602916&rss=true"

#0=256x144 (61k audio)
#1=512x288 (125k audio)
#2=640x360 (189k audio)
#3=960x544 (189k audio)
QUALITY = 3

#set to False if you don't want subtitles
SUBTITLES = True

TARGET_DIR = "/data/tatort/"


feed = feedparser.parse( RSS_URL )

items = feed.entries

today = datetime.date.today()

unescape = HTMLParser().unescape

def xml2srt(in_fn, out_fn):
   """
   Convert xml subtitle file `in_fn` to srt format and write to `out_fn`.

   Note 1: the (apparently constant) offset of 10 hours is ignored

   Note 2: the .srt file is UTF8 encoded. This may not be detected
   correctly by all media players. For example `mplayer` needs the
   option "-subcp utf8" in order to display the subtitles correctly

   """

   encoding = 'utf8'

   lines = open(in_fn).readlines()

   subtitle_pat = re.compile(('.*<p id="subtitle[0-9]+" '
                              'begin="(?P<begin>[0-9]+:[0-9]+:[0-9]+.[0-9]+)" '
                              'end="(?P<end>[0-9]+:[0-9]+:[0-9]+.[0-9]+)" '
                              'tts:textAlign="center" '
                              'style="s[0-9]">(?P<text>.*)</p>.*'))

   tag_pat = re.compile('<[^>]+>')

   with open(out_fn, 'w') as f:

      i = 1
      for l in lines:

         m = subtitle_pat.search(l)

         if m is not None:

            d = m.groupdict()
            begin = '0' + d['begin'].replace('.', ',')[1:]
            end = '0' + d['end'].replace('.', ',')[1:]
            text = tag_pat.sub('', d['text'].replace('<br />','\n'))
            f.write(u'{0}\n{1} --> {2}\n{3}\n\n'
                    .format(i, begin, end, unescape(text)).encode(encoding))
            i += 1

for item in items:

   year = item["date_parsed"][0];
   month = item["date_parsed"][1];
   day = item["date_parsed"][2];
   feedDate = datetime.date(item["date_parsed"][0], item["date_parsed"][1], item["date_parsed"][2])

   if feedDate == today:
      title = item["title"]
      link = item["link"]
      parsed = urlparse.urlparse(link)
      docId = urlparse.parse_qs(parsed.query)['documentId']
      docUrl = 'http://www.ardmediathek.de/play/media/' + docId[0] + '?devicetype=pc&features=flash'

      response = urlopen(docUrl)
      html = response.read()

      if 'http://www.ardmediathek.de/-/stoerung' == response.geturl():
        print "Could not get item with title '" + title + "'. Got redirected to '" + response.geturl() + "'. This is probably because the item is still in the RSS feed, but not available anymore."
        continue

      try:
        media = json.loads(html)
      except ValueError as e:
        print e
        print "Could not get item with title '" + title + "'. Original item link is '" + link + "' and parsed docId[0] is '" + docId[0] + "', but html response from '" + docUrl + "' was '" + html + "'"
        continue

      if '_mediaArray' not in media or len(media["_mediaArray"]) == 0:
        print "Skipping " + title + " because it does not have any mediafiles"
        continue
      mediaLinks = media["_mediaArray"][1]["_mediaStreamArray"]

      for mediaLink in mediaLinks:
         if QUALITY == mediaLink["_quality"]:
            mediaURL = mediaLink["_stream"]
            fileName = "".join([x if x.isalnum() or x in "- " else "" for x in title])
            urlretrieve(mediaURL, TARGET_DIR + fileName + ".mp4")
            print "Downloaded '" + title + "'"

            #download subtitles
            try:
              if SUBTITLES and '_subtitleUrl' in media and len(media["_subtitleUrl"]) > 0:
                offset = 0
                if '_subtitleOffset' in media:
                 offset = media["_subtitleOffset"]

                subtitleURL = 'http://www.ardmediathek.de/' + media["_subtitleUrl"]
                subtitleXML = TARGET_DIR + fileName + "_subtitleOffset_" + str(offset) + ".xml"
                subtitleSRT = TARGET_DIR + fileName + ".srt"

                urlretrieve(subtitleURL, subtitleXML)

                # convert xml subtitles to srt format
                xml2srt(subtitleXML, subtitleSRT)

            except Exception as e:
              #print and resume with download
              print e
              print subtitleURL
