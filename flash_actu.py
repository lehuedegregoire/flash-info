#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, json
from datetime import datetime
from dateutil import tz
import feedparser
from gtts import gTTS
import requests
import xml.sax.saxutils as sx

RSS_URLS = [
    "https://www.francetvinfo.fr/titres.rss",
    "https://www.france24.com/fr/rss",
    "https://www.lemonde.fr/rss/une.xml"
]

TARGET_WORDS_MAX = 320
OUT_DIR = "sorties"
VOICE_LANG = "fr"

def now_paris():
    return datetime.now(tz=tz.gettz("Europe/Paris"))

def clean_html(s: str) -> str:
    s = s or ""
    s = re.sub(r"<.*?>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def fetch_items(max_per_feed=5):
    items = []
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:max_per_feed]:
                title = clean_html(e.get("title",""))
                summary = clean_html(e.get("summary","") or e.get("description",""))
                if title:
                    items.append((title, summary[:240]))
        except Exception as ex:
            print(f"[WARN] Flux en erreur {url}: {ex}", file=sys.stderr)
    return items

def build_prompt(items, date_str):
    bullets = "\n".join([f"- {t}: {s}" for t, s in items])
    return f"""
À partir des brèves ci-dessous, écris un flash d’actualité (~280 mots, ~2 minutes à l’oral).
Contraintes :
- Ton neutre et factuel, phrases courtes, chiffres clairs.
- Commence par : "Bonjour, voici l’essentiel de l’actualité du {date_str}."
- 5 à 7 points thématiques max.
- Utilise uniquement les infos présentes.
- Termine par "Bonne journée."

Brèves :
{bullets}
"""

def call_openai_chat(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY manquante")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Tu es un journaliste factuel et concis."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 900,
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

def clamp_length(text: str) -> str:
    words = text.split()
    if len(words) > TARGET_WORDS_MAX:
        words = words[:TARGET_WORDS_MAX]
        text = " ".join(words).rstrip(",;:.") + "…"
    return text

def fallback_script(date_str, items):
    lines = [f"Bonjour, voici l’essentiel de l’actualité du {date_str}."]
    for t, _ in items[:6]:
        lines.append(f"• {t}.")
    lines.append("Bonne journée.")
    return "\n".join(lines)

def script_to_mp3(script_text: str, mp3_path: str):
    tts = gTTS(text=script_text, lang=VOICE_LANG, slow=False)
    tts.save(mp3_path)

def update_podcast_feed(mp3_path: str, title: str, site_base_url: str, feed_path: str):
    os.makedirs(os.path.dirname(feed_path), exist_ok=True)
    item_url = site_base_url + "/" + mp3_path.replace("\\", "/")
    pubdate = now_paris().strftime("%a, %d %b %Y %H:%M:%S %z")
    items_xml = []
    if os.path.exists(feed_path):
        with open(feed_path, "r", encoding="utf-8") as f:
            existing = f.read()
        items_xml = re.findall(r"(<item>.*?</item>)", existing, flags=re.S)
    new_item = f"""
    <item>
      <title>{sx.escape(title)}</title>
      <description>{sx.escape(title)}</description>
      <pubDate>{pubdate}</pubDate>
      <enclosure url="{sx.escape(item_url)}" length="0" type="audio/mpeg"/>
      <guid isPermaLink="false">{sx.escape(os.path.basename(mp3_path))}</guid>
    </item>""".strip()
    items_xml.insert(0, new_item)
    channel = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Flash Actu Perso</title>
    <link>{sx.escape(site_base_url)}</link>
    <description>Résumé quotidien ~2 minutes</description>
    <language>fr</language>
    {''.join(items_xml[:50])}
  </channel>
</rss>"""
    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(channel)

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    today = now_paris()
    date_str = today.strftime("%-d %B %Y")
    ymd = today.strftime("%Y-%m-%d")

    items = fetch_items()
    if not items:
        print("[ERREUR] Aucun article trouvé — vérifier les flux RSS.", file=sys.stderr)
        sys.exit(1)

    prompt = build_prompt(items, date_str)
    try:
        script = call_openai_chat(prompt)
        script = clamp_length(script)
        print("[INFO] Script IA généré.")
    except Exception as e:
        print(f"[WARN] IA indisponible ({e}). Fallback titres.")
        script = fallback_script(date_str, items)

    mp3_name = f"flash_{ymd}.mp3"
    mp3_path = os.path.join(OUT_DIR, mp3_name)
    script_to_mp3(script, mp3_path)

    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "").strip()
    repo_env = os.environ.get("GITHUB_REPOSITORY", "")
    repo = repo_env.split("/")[-1].strip() if repo_env else ""
    base_url = f"https://{owner}.github.io/{repo}" if owner and repo else "."

    feed_path = os.path.join(OUT_DIR, "feed.xml")
    update_podcast_feed(mp3_path, f"Flash du {date_str}", base_url, feed_path)

    with open(os.path.join(OUT_DIR, f"flash_{ymd}.txt"), "w", encoding="utf-8") as f:
        f.write(script)

    print("[OK] Audio :", mp3_path)
    print("[OK] Flux  :", feed_path)

if __name__ == "__main__":
    main()

