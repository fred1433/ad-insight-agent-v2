"""
Contient la logique pour télécharger une vidéo depuis une URL,
en utilisant des stratégies de scraping robustes.
"""

import os
import tempfile
import time
import json
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup
# from google.cloud import storage # Vestige de l'ancienne intégration GCS, supprimé

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import config

class MediaDownloader:
    """Télécharge des médias (vidéos, images) en utilisant des stratégies adaptées."""

    def __init__(self):
        self.download_folder = "tmp/media"
        os.makedirs(self.download_folder, exist_ok=True)

    def download_image_locally(self, image_url: str, ad_id: str) -> Optional[str]:
        """
        Télécharge une image depuis son URL et la sauvegarde localement.
        Retourne le chemin du fichier local ou None si échec.
        """
        print(f"Démarrage du téléchargement de l'image pour la pub {ad_id}")
        try:
            response = requests.get(image_url, stream=True, timeout=60)
            response.raise_for_status()

            # Détecter l'extension du fichier à partir de l'URL
            file_extension = os.path.splitext(image_url.split('?')[0])[-1]
            if not file_extension:
                # Fallback sur .jpg si aucune extension n'est trouvée
                file_extension = '.jpg'
            
            local_path = os.path.join(self.download_folder, f"{ad_id}{file_extension}")
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"✅ Image sauvegardée localement : {local_path}")
            return local_path

        except requests.RequestException as e:
            print(f"Erreur lors du téléchargement de l'image : {e}")
            return None

    def download_video_locally(self, video_id: str, ad_id: str) -> Optional[str]:
        """
        Orchestre le téléchargement et la sauvegarde LOCALE d'une vidéo.
        Retourne le chemin du fichier local ou None si échec.
        """
        print(f"Démarrage du téléchargement local pour la pub {ad_id}")
        
        # Tenter d'extraire l'URL directe du .mp4
        mp4_url = self._extract_mp4_url(video_id)
        if not mp4_url:
            print(f"❌ Impossible d'extraire l'URL du MP4 pour la pub {ad_id}.")
            return None

        # Télécharger le contenu de la vidéo
        try:
            print(f"Téléchargement du contenu de la vidéo depuis : {mp4_url[:100]}...")
            response = requests.get(mp4_url, stream=True, timeout=60)
            response.raise_for_status()
            
            # Sauvegarder le fichier localement
            local_path = os.path.join(self.download_folder, f"{ad_id}.mp4")
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"✅ Vidéo sauvegardée localement : {local_path}")
            return local_path
            
        except requests.RequestException as e:
            print(f"Erreur lors du téléchargement du fichier MP4 : {e}")
            return None

    def _extract_mp4_url(self, video_id: str) -> Optional[str]:
        """Tente d'extraire l'URL MP4 avec Selenium, puis avec Requests en fallback."""
        print("ℹ️ Lancement de la stratégie principale (Selenium)...")
        url = self._scrape_with_selenium(video_id)
        if url:
            print("✅ Stratégie principale réussie.")
            return url

        print("⚠️ La stratégie principale a échoué. Lancement de la stratégie de secours (Requests)...")
        fallback_url = self._scrape_with_requests(video_id)
        if fallback_url:
            print("✅ Stratégie de secours réussie.")
            return fallback_url
            
        print(f"❌ Toutes les stratégies ont échoué pour la vidéo {video_id}.")
        return None

    def _scrape_with_selenium(self, video_id: str) -> Optional[str]:
        """Utilise Selenium pour intercepter l'URL de la vidéo."""
        watch_url = f"https://www.facebook.com/watch/?v={video_id}"
        print(f"ℹ️ [Selenium] Navigation vers : {watch_url}")
        
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        
        driver = None
        try:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(watch_url)

            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "video")))
            time.sleep(3)

            try:
                video_element = driver.find_element(By.TAG_NAME, "video")
                driver.execute_script("arguments[0].play();", video_element)
                time.sleep(2) 
            except Exception:
                pass

            logs = driver.get_log('performance')
            mp4_urls = set()
            for entry in logs:
                log = json.loads(entry['message'])['message']
                if 'Network.responseReceived' == log['method']:
                    try:
                        resp_url = log['params']['response']['url']
                        if ".mp4" in resp_url and "fbcdn.net" in resp_url:
                            mp4_urls.add(resp_url)
                    except KeyError:
                        continue
            
            if mp4_urls:
                return self._select_best_quality_url(list(mp4_urls))
            return None
        finally:
            if driver:
                driver.quit()

    def _scrape_with_requests(self, video_id: str) -> Optional[str]:
        """Fallback utilisant requests et une liste robuste de regex."""
        watch_url = f"https://www.facebook.com/watch/?v={video_id}"
        print(f"ℹ️ [Requests] Tentative de secours sur : {watch_url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        try:
            response = requests.get(watch_url, headers=headers, timeout=30)
            response.raise_for_status()

            patterns = [
                r'"playable_url":"([^"]*\.mp4[^"]*)"',
                r'"browser_native_hd_url":"([^"]*\.mp4[^"]*)"',
                r'"browser_native_sd_url":"([^"]*\.mp4[^"]*)"',
                r'"playable_url_quality_hd":"([^"]*\.mp4[^"]*)"',
                r'"src":"([^"]*\.mp4[^"]*)"',
                r'"(https://[^"]*\.mp4[^"]*)"',
                r"'(https://[^']*\.mp4[^']*)'",
                r'src="([^"]*\.mp4[^"]*)"',
                r"src='([^']*\.mp4[^']*)'",
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response.text)
                for match in matches:
                    mp4_url = match.replace('\\/', '/').replace('\\u0026', '&')
                    if mp4_url.startswith('http') and '.mp4' in mp4_url:
                        return mp4_url
            return None
        except requests.RequestException as e:
            print(f"Erreur de requête HTTP : {e}")
            return None

    def _select_best_quality_url(self, urls: list) -> Optional[str]:
        """Sélectionne l'URL de la meilleure qualité."""
        if not urls:
            return None
        # Pour l'instant, la logique de qualité est simplifiée, on prend la première
        return urls[0] 