import feedparser, os, re
from datetime import datetime
from dateutil import tz
import openai
from gtts import gTTS
import xml.sax.saxutils as sx

# Clé API OpenAI (dans les secrets GitHub)
openai.api_key = os.environ["OPENAI_API_KEY"]

RSS_URLS = [
    "https://www.francetvinfo.fr/titres.rss",
    "https://www.france24.com/fr/rss",
    "https://www.lemonde.fr/rss/une.xml"
]

def now_paris():
    return datetime.now(tz=tz.gettz("Europe/Paris"))

def fetch_items():
    items = []
    for url in RSS_URLS:
        feed = feedparser.parse(url)
        for e in feed.entries[:5]:
            title = re.sub(r"<.*?>", "", e.get("title",""))
            summary = re.sub(r"<.*?>", "", e.get("summary","") or "")
            items.append(f"- {title}: {summary}")
    return items

def make_script(items, date_str):
    prompt = f"""
Tu es journaliste. Voici des brèves d'actualité :

{chr(10).join(items)}

Écris un flash d’actualité en français (~280 mots, environ 2 minutes à l’oral).
Contraintes :
- Ton neutre et factuel.
- Commence par "Bonjour, voici l’essentiel de l’actualité du {date_str}."
- 5 à 7 points clairs.
- Termine par "Bonne journée."
"""
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message["content"]

def update_feed(mp3_path, date_str):
    os.makedirs("sorties", exist_ok=True)
    feed_path = "sorties/feed.xml"
    item_url = f"https://{os.environ['GITHUB_REPOSITORY_OWNER']}.github.io/{os.environ['GITHUB_REPOSITORY'].split('/')[-1]}/{mp3_path}"
    pubdate = now_paris().strftime("%a, %d %b %Y %H:%M:%S %z")

    items_xml = []
    if os.path.exists(feed_path):
        with open(feed_path, "r", encoding="utf-8") as f:
            items_xml = re.findall(r"(<item>.*?</item>)", f.read(), flags=re.S)

    new_item = f"""
    <item>
      <title>Flash du {date_str}</title>
      <description>Résumé quotidien</description>
      <pubDate>{pubdate}</pubDate>
      <enclosure url="{sx.escape(item_url)}" length="0" type="audio/mpeg"/>
      <guid isPermaLink="false">{mp3_path}</guid>
    </item>""".strip()

    items_xml.insert(0, new_item)
    channel = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
 <channel>
  <title>Flash Actu Perso</title>
  <link>{item_url}</link>
  <description>Résumé quotidien ~2 minutes</description>
  <language>fr</language>
  {''.join(items_xml[:30])}
 </channel>
</rss>"""
    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(channel)

def main():
    today = now_paris()
    date_str = today.strftime("%-d %B %Y")
    items = fetch_items()
    script = make_script(items, date_str)
    mp3_name = f"sorties/flash_{today.strftime('%Y-%m-%d')}.mp3"

    tts = gTTS(script, lang="fr")
    tts.save(mp3_name)

    update_feed(mp3_name, date_str)

if __name__ == "__main__":
    main()
